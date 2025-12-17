#!/bin/bash
# Backup databases from Docker containers
# Supports MariaDB/MySQL containers

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.env"

STARTED_AT=$(date -Iseconds)
TEMP_DIR=$(mktemp -d)
trap "rm -rf ${TEMP_DIR}" EXIT

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_DIR}/backup_db.log"
}

# Verify NAS mount is present before proceeding
check_nas_mount() {
    if ! mountpoint -q "${NAS_MOUNT}"; then
        log "FATAL: NAS not mounted at ${NAS_MOUNT}"
        "${SCRIPT_DIR}/emit_result.sh" "system" "db" "fail" "$STARTED_AT" "$(date -Iseconds)" "0" "null" "${RESTIC_REPO}" "NAS not mounted at ${NAS_MOUNT}"
        exit 1
    fi

    # Also verify restic repo is accessible
    if [[ ! -d "${RESTIC_REPO}" ]]; then
        log "FATAL: Restic repository not found at ${RESTIC_REPO}"
        "${SCRIPT_DIR}/emit_result.sh" "system" "db" "fail" "$STARTED_AT" "$(date -Iseconds)" "0" "null" "${RESTIC_REPO}" "Restic repository not found"
        exit 1
    fi

    if [[ ! -f "${RESTIC_PASSWORD_FILE}" ]]; then
        log "FATAL: Restic password file not found at ${RESTIC_PASSWORD_FILE}"
        "${SCRIPT_DIR}/emit_result.sh" "system" "db" "fail" "$STARTED_AT" "$(date -Iseconds)" "0" "null" "${RESTIC_REPO}" "Restic password file not found"
        exit 1
    fi
}

log "=== Starting database backup ==="

# Check NAS mount before proceeding
check_nas_mount

# Find all database containers
DB_CONTAINERS=$(docker ps --format '{{.Names}}' | grep -E '(mysql|mariadb|db)' || true)

if [[ -z "$DB_CONTAINERS" ]]; then
    log "No database containers found"
    "${SCRIPT_DIR}/emit_result.sh" "system" "db" "warn" "$STARTED_AT" "$(date -Iseconds)" "0" "null" "${RESTIC_REPO}" "No database containers found"
    exit 0
fi

TOTAL_BYTES=0
BACKUP_IDS=()
ERRORS=()

for CONTAINER in $DB_CONTAINERS; do
    log "Processing container: $CONTAINER"

    # Determine site name from container name (e.g., site-db -> site)
    SITE_NAME=$(echo "$CONTAINER" | sed -E 's/[-_](db|mysql|mariadb).*$//')

    # Get database credentials from container environment
    DB_USER=$(docker exec "$CONTAINER" printenv MYSQL_USER 2>/dev/null || echo "root")
    DB_PASS=$(docker exec "$CONTAINER" printenv MYSQL_PASSWORD 2>/dev/null || \
              docker exec "$CONTAINER" printenv MYSQL_ROOT_PASSWORD 2>/dev/null || echo "")

    if [[ -z "$DB_PASS" ]]; then
        log "  WARNING: Could not find database password for $CONTAINER"
        ERRORS+=("$CONTAINER: No password found")

        # Emit per-site failure
        "${SCRIPT_DIR}/emit_result.sh" "$SITE_NAME" "db" "fail" "$STARTED_AT" "$(date -Iseconds)" "0" "null" "${RESTIC_REPO}" "No database password found"
        continue
    fi

    # Create dump
    DUMP_FILE="${TEMP_DIR}/${SITE_NAME}-$(date +%Y%m%d%H%M%S).sql"

    log "  Creating dump..."
    if docker exec "$CONTAINER" mysqldump -u"$DB_USER" -p"$DB_PASS" \
        --single-transaction --quick --lock-tables=false \
        --all-databases > "$DUMP_FILE" 2>/dev/null; then

        DUMP_SIZE=$(stat -c%s "$DUMP_FILE")
        TOTAL_BYTES=$((TOTAL_BYTES + DUMP_SIZE))
        log "  Dump created: $(numfmt --to=iec $DUMP_SIZE)"

        # Backup with restic
        log "  Running restic backup..."
        RESTIC_OUTPUT=$(restic -r "${RESTIC_REPO}" --password-file "${RESTIC_PASSWORD_FILE}" \
            backup "$DUMP_FILE" \
            --tag "db" --tag "$SITE_NAME" \
            --json 2>&1 | tail -1)

        SNAPSHOT_ID=$(echo "$RESTIC_OUTPUT" | jq -r '.snapshot_short_id // empty' 2>/dev/null || echo "")
        if [[ -n "$SNAPSHOT_ID" ]]; then
            BACKUP_IDS+=("$SNAPSHOT_ID")
            log "  Snapshot created: $SNAPSHOT_ID"

            # Emit per-site result so dashboard can track individual site backups
            "${SCRIPT_DIR}/emit_result.sh" "$SITE_NAME" "db" "ok" "$STARTED_AT" "$(date -Iseconds)" "$DUMP_SIZE" "$SNAPSHOT_ID" "${RESTIC_REPO}" "null"
        else
            log "  WARNING: Could not parse snapshot ID"
            ERRORS+=("$CONTAINER: Restic backup may have failed")

            # Emit per-site failure
            "${SCRIPT_DIR}/emit_result.sh" "$SITE_NAME" "db" "warn" "$STARTED_AT" "$(date -Iseconds)" "$DUMP_SIZE" "null" "${RESTIC_REPO}" "Restic backup may have failed"
        fi

        rm -f "$DUMP_FILE"
    else
        log "  ERROR: mysqldump failed for $CONTAINER"
        ERRORS+=("$CONTAINER: mysqldump failed")

        # Emit per-site failure
        "${SCRIPT_DIR}/emit_result.sh" "$SITE_NAME" "db" "fail" "$STARTED_AT" "$(date -Iseconds)" "0" "null" "${RESTIC_REPO}" "mysqldump failed"
    fi
done

# Apply retention policy
log "Applying retention policy..."
restic -r "${RESTIC_REPO}" --password-file "${RESTIC_PASSWORD_FILE}" \
    forget --tag "db" \
    --keep-daily "${KEEP_DAILY}" \
    --keep-weekly "${KEEP_WEEKLY}" \
    --keep-monthly "${KEEP_MONTHLY}" \
    --prune 2>&1 | tee -a "${LOG_DIR}/backup_db.log" || true

ENDED_AT=$(date -Iseconds)

# Determine status
if [[ ${#ERRORS[@]} -eq 0 ]]; then
    STATUS="ok"
    ERROR_MSG="null"
else
    if [[ ${#BACKUP_IDS[@]} -gt 0 ]]; then
        STATUS="warn"
    else
        STATUS="fail"
    fi
    ERROR_MSG="${ERRORS[*]}"
fi

# Emit result
BACKUP_ID_STR=$(IFS=','; echo "${BACKUP_IDS[*]:-null}")
"${SCRIPT_DIR}/emit_result.sh" "system" "db" "$STATUS" "$STARTED_AT" "$ENDED_AT" "$TOTAL_BYTES" "$BACKUP_ID_STR" "${RESTIC_REPO}" "$ERROR_MSG"

log "=== Database backup complete (status: $STATUS) ==="
