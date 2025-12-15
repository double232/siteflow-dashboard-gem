#!/bin/bash
# Restore site data from backup
# SiteFlow Backup System
#
# Usage:
#   restore.sh --site SITE --timestamp TIMESTAMP [--restore-db] [--restore-uploads] [--dry-run] [--i-understand-risk]
#
# Examples:
#   restore.sh --site myblog --timestamp latest --restore-uploads --dry-run
#   restore.sh --site myblog --timestamp 2024-01-15T10:00:00 --restore-db --restore-uploads --i-understand-risk

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.env"

# Parse arguments
SITE=""
TIMESTAMP=""
RESTORE_DB=false
RESTORE_UPLOADS=false
DRY_RUN=false
CONFIRMED=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --site)
            SITE="$2"
            shift 2
            ;;
        --timestamp)
            TIMESTAMP="$2"
            shift 2
            ;;
        --restore-db)
            RESTORE_DB=true
            shift
            ;;
        --restore-uploads)
            RESTORE_UPLOADS=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --i-understand-risk)
            CONFIRMED=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate arguments
if [[ -z "$SITE" ]]; then
    echo "ERROR: --site is required"
    echo "Usage: restore.sh --site SITE --timestamp TIMESTAMP [--restore-db] [--restore-uploads] [--dry-run] [--i-understand-risk]"
    exit 1
fi

if [[ -z "$TIMESTAMP" ]]; then
    echo "ERROR: --timestamp is required (use 'latest' or ISO8601 format)"
    exit 1
fi

if [[ "$RESTORE_DB" == false ]] && [[ "$RESTORE_UPLOADS" == false ]]; then
    echo "ERROR: Specify at least one of --restore-db or --restore-uploads"
    exit 1
fi

if [[ "$DRY_RUN" == false ]] && [[ "$CONFIRMED" == false ]]; then
    echo "ERROR: This is a destructive operation!"
    echo "Add --dry-run to preview, or --i-understand-risk to proceed"
    exit 1
fi

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "=== SiteFlow Restore ==="
log "Site: $SITE"
log "Timestamp: $TIMESTAMP"
log "Restore DB: $RESTORE_DB"
log "Restore Uploads: $RESTORE_UPLOADS"
log "Dry Run: $DRY_RUN"

# Find snapshots
find_snapshot() {
    local TAG=$1

    if [[ "$TIMESTAMP" == "latest" ]]; then
        restic -r "${RESTIC_REPO}" --password-file "${RESTIC_PASSWORD_FILE}" \
            snapshots --tag "$TAG" --tag "$SITE" --json --latest 1 \
            | jq -r '.[0].short_id // empty'
    else
        # Find snapshot closest to timestamp
        restic -r "${RESTIC_REPO}" --password-file "${RESTIC_PASSWORD_FILE}" \
            snapshots --tag "$TAG" --tag "$SITE" --json \
            | jq -r --arg ts "$TIMESTAMP" \
                'map(select(.time | startswith($ts[:10]))) | sort_by(.time) | reverse | .[0].short_id // empty'
    fi
}

# Restore database
if [[ "$RESTORE_DB" == true ]]; then
    log ""
    log "=== Restoring Database ==="

    SNAPSHOT_ID=$(find_snapshot "db")
    if [[ -z "$SNAPSHOT_ID" ]]; then
        log "ERROR: No database snapshot found for $SITE"
        exit 1
    fi
    log "Using snapshot: $SNAPSHOT_ID"

    # Find database container
    DB_CONTAINER=$(docker ps --format '{{.Names}}' | grep -E "^${SITE}[-_](db|mysql|mariadb)" | head -1 || true)
    if [[ -z "$DB_CONTAINER" ]]; then
        log "ERROR: No database container found for $SITE"
        log "Expected pattern: ${SITE}-db or ${SITE}_db"
        exit 1
    fi
    log "Target container: $DB_CONTAINER"

    if [[ "$DRY_RUN" == true ]]; then
        log "[DRY RUN] Would restore database from snapshot $SNAPSHOT_ID to container $DB_CONTAINER"
        restic -r "${RESTIC_REPO}" --password-file "${RESTIC_PASSWORD_FILE}" \
            ls "$SNAPSHOT_ID"
    else
        # Create temp directory for restore
        TEMP_DIR=$(mktemp -d)
        trap "rm -rf ${TEMP_DIR}" EXIT

        log "Extracting snapshot..."
        restic -r "${RESTIC_REPO}" --password-file "${RESTIC_PASSWORD_FILE}" \
            restore "$SNAPSHOT_ID" --target "$TEMP_DIR"

        # Find the SQL file
        SQL_FILE=$(find "$TEMP_DIR" -name "*.sql" | head -1)
        if [[ -z "$SQL_FILE" ]]; then
            log "ERROR: No SQL file found in snapshot"
            exit 1
        fi
        log "Found SQL file: $SQL_FILE"

        # Get credentials
        DB_USER=$(docker exec "$DB_CONTAINER" printenv MYSQL_USER 2>/dev/null || echo "root")
        DB_PASS=$(docker exec "$DB_CONTAINER" printenv MYSQL_PASSWORD 2>/dev/null || \
                  docker exec "$DB_CONTAINER" printenv MYSQL_ROOT_PASSWORD 2>/dev/null)

        log "Restoring database..."
        cat "$SQL_FILE" | docker exec -i "$DB_CONTAINER" mysql -u"$DB_USER" -p"$DB_PASS"

        log "Database restored successfully"
    fi
fi

# Restore uploads
if [[ "$RESTORE_UPLOADS" == true ]]; then
    log ""
    log "=== Restoring Uploads ==="

    SNAPSHOT_ID=$(find_snapshot "uploads")
    if [[ -z "$SNAPSHOT_ID" ]]; then
        log "ERROR: No uploads snapshot found for $SITE"
        exit 1
    fi
    log "Using snapshot: $SNAPSHOT_ID"

    # Find uploads directory
    UPLOADS_PATH=""
    SITE_DIR="${SITES_ROOT}/${SITE}"

    for CANDIDATE in \
        "${SITE_DIR}/wp-content/uploads" \
        "${SITE_DIR}/wordpress/wp-content/uploads" \
        "${SITE_DIR}/html/wp-content/uploads" \
        "${SITE_DIR}/uploads" \
        "${SITE_DIR}/public/uploads"; do
        if [[ -d "$CANDIDATE" ]] || [[ -d "$(dirname "$CANDIDATE")" ]]; then
            UPLOADS_PATH="$CANDIDATE"
            break
        fi
    done

    if [[ -z "$UPLOADS_PATH" ]]; then
        log "ERROR: Cannot determine uploads path for $SITE"
        log "Site directory: $SITE_DIR"
        exit 1
    fi
    log "Target path: $UPLOADS_PATH"

    if [[ "$DRY_RUN" == true ]]; then
        log "[DRY RUN] Would restore uploads from snapshot $SNAPSHOT_ID to $UPLOADS_PATH"
        restic -r "${RESTIC_REPO}" --password-file "${RESTIC_PASSWORD_FILE}" \
            ls "$SNAPSHOT_ID" | head -20
        log "... (truncated)"
    else
        # Backup current uploads
        if [[ -d "$UPLOADS_PATH" ]]; then
            BACKUP_PATH="${UPLOADS_PATH}.bak.$(date +%Y%m%d%H%M%S)"
            log "Backing up current uploads to $BACKUP_PATH"
            mv "$UPLOADS_PATH" "$BACKUP_PATH"
        fi

        log "Restoring uploads..."
        restic -r "${RESTIC_REPO}" --password-file "${RESTIC_PASSWORD_FILE}" \
            restore "$SNAPSHOT_ID" --target "/" --include "$UPLOADS_PATH"

        # Fix ownership (www-data for web containers)
        log "Fixing ownership..."
        chown -R 33:33 "$UPLOADS_PATH" 2>/dev/null || \
        chown -R www-data:www-data "$UPLOADS_PATH" 2>/dev/null || true

        log "Uploads restored successfully"
    fi
fi

log ""
log "=== Restore complete ==="
