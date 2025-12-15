#!/bin/bash
# Backup WordPress uploads directories from all sites

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.env"

STARTED_AT=$(date -Iseconds)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_DIR}/backup_uploads.log"
}

log "=== Starting uploads backup ==="

TOTAL_BYTES=0
BACKUP_IDS=()
ERRORS=()
SITES_BACKED_UP=0

# Find all sites with wp-content/uploads
for SITE_DIR in "${SITES_ROOT}"/*/; do
    SITE_NAME=$(basename "$SITE_DIR")

    # Skip non-directories and special folders
    [[ ! -d "$SITE_DIR" ]] && continue
    [[ "$SITE_NAME" == "gateway" ]] && continue
    [[ "$SITE_NAME" == "siteflow-dashboard" ]] && continue

    # Look for wp-content/uploads in various locations
    UPLOADS_PATH=""
    for CANDIDATE in \
        "${SITE_DIR}wp-content/uploads" \
        "${SITE_DIR}wordpress/wp-content/uploads" \
        "${SITE_DIR}html/wp-content/uploads" \
        "${SITE_DIR}public/wp-content/uploads" \
        "${SITE_DIR}app/wp-content/uploads"; do

        if [[ -d "$CANDIDATE" ]]; then
            UPLOADS_PATH="$CANDIDATE"
            break
        fi
    done

    # Also check for general uploads directories (non-WordPress)
    if [[ -z "$UPLOADS_PATH" ]]; then
        for CANDIDATE in \
            "${SITE_DIR}uploads" \
            "${SITE_DIR}public/uploads" \
            "${SITE_DIR}storage/uploads"; do

            if [[ -d "$CANDIDATE" ]]; then
                UPLOADS_PATH="$CANDIDATE"
                break
            fi
        done
    fi

    if [[ -z "$UPLOADS_PATH" ]]; then
        log "  $SITE_NAME: No uploads directory found, skipping"
        continue
    fi

    log "Processing: $SITE_NAME -> $UPLOADS_PATH"

    # Get size before backup
    DIR_SIZE=$(du -sb "$UPLOADS_PATH" 2>/dev/null | cut -f1 || echo "0")
    TOTAL_BYTES=$((TOTAL_BYTES + DIR_SIZE))

    # Backup with restic
    log "  Running restic backup..."
    RESTIC_OUTPUT=$(restic -r "${RESTIC_REPO}" --password-file "${RESTIC_PASSWORD_FILE}" \
        backup "$UPLOADS_PATH" \
        --tag "uploads" --tag "$SITE_NAME" \
        --json 2>&1 | tail -1)

    SNAPSHOT_ID=$(echo "$RESTIC_OUTPUT" | jq -r '.snapshot_short_id // empty' 2>/dev/null || echo "")
    if [[ -n "$SNAPSHOT_ID" ]]; then
        BACKUP_IDS+=("$SNAPSHOT_ID")
        log "  Snapshot created: $SNAPSHOT_ID ($(numfmt --to=iec $DIR_SIZE))"
        SITES_BACKED_UP=$((SITES_BACKED_UP + 1))

        # Also emit per-site result
        "${SCRIPT_DIR}/emit_result.sh" "$SITE_NAME" "uploads" "ok" "$STARTED_AT" "$(date -Iseconds)" "$DIR_SIZE" "$SNAPSHOT_ID" "${RESTIC_REPO}" "null"
    else
        log "  WARNING: Could not parse snapshot ID for $SITE_NAME"
        ERRORS+=("$SITE_NAME: Restic backup may have failed")
    fi
done

# Apply retention policy
log "Applying retention policy..."
restic -r "${RESTIC_REPO}" --password-file "${RESTIC_PASSWORD_FILE}" \
    forget --tag "uploads" \
    --keep-daily "${KEEP_DAILY}" \
    --keep-weekly "${KEEP_WEEKLY}" \
    --keep-monthly "${KEEP_MONTHLY}" \
    --prune 2>&1 | tee -a "${LOG_DIR}/backup_uploads.log" || true

ENDED_AT=$(date -Iseconds)

# Determine status
if [[ ${#ERRORS[@]} -eq 0 ]] && [[ $SITES_BACKED_UP -gt 0 ]]; then
    STATUS="ok"
    ERROR_MSG="null"
elif [[ $SITES_BACKED_UP -gt 0 ]]; then
    STATUS="warn"
    ERROR_MSG="${ERRORS[*]}"
else
    STATUS="fail"
    ERROR_MSG="No sites backed up. ${ERRORS[*]:-No uploads directories found.}"
fi

# Emit overall result
BACKUP_ID_STR=$(IFS=','; echo "${BACKUP_IDS[*]:-null}")
"${SCRIPT_DIR}/emit_result.sh" "system" "uploads" "$STATUS" "$STARTED_AT" "$ENDED_AT" "$TOTAL_BYTES" "$BACKUP_ID_STR" "${RESTIC_REPO}" "$ERROR_MSG"

log "=== Uploads backup complete: $SITES_BACKED_UP sites (status: $STATUS) ==="
