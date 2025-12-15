#!/bin/bash
# Verify restic repository integrity
# SiteFlow Backup System

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.env"

STARTED_AT=$(date -Iseconds)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_DIR}/verify_backups.log"
}

log "=== Starting backup verification ==="
log "Repository: ${RESTIC_REPO}"
log "Data subset: ${VERIFY_DATA_SUBSET}"

# Run restic check with data verification
ERROR_MSG="null"
STATUS="ok"

if restic -r "${RESTIC_REPO}" --password-file "${RESTIC_PASSWORD_FILE}" \
    check --read-data-subset="${VERIFY_DATA_SUBSET}" \
    2>&1 | tee -a "${LOG_DIR}/verify_backups.log"; then
    log "Verification passed"
else
    STATUS="fail"
    ERROR_MSG="Restic check failed"
    log "ERROR: Verification failed"
fi

# Get repository stats
log "Repository statistics:"
restic -r "${RESTIC_REPO}" --password-file "${RESTIC_PASSWORD_FILE}" stats \
    2>&1 | tee -a "${LOG_DIR}/verify_backups.log" || true

ENDED_AT=$(date -Iseconds)

# Emit result
"${SCRIPT_DIR}/emit_result.sh" "system" "verify" "$STATUS" "$STARTED_AT" "$ENDED_AT" "null" "null" "${RESTIC_REPO}" "$ERROR_MSG"

log "=== Verification complete (status: $STATUS) ==="
