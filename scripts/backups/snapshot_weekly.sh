#!/bin/bash
# Create Hetzner Cloud VM snapshot
# SiteFlow Backup System

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.env"

STARTED_AT=$(date -Iseconds)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_DIR}/snapshot_weekly.log"
}

log "=== Starting weekly VM snapshot ==="

# Check for required credentials
if [[ -z "${HETZNER_API_TOKEN:-}" ]]; then
    log "WARNING: HETZNER_API_TOKEN not set"
    log "To enable VM snapshots:"
    log "  1. Create an API token at https://console.hetzner.cloud/"
    log "  2. Add HETZNER_API_TOKEN=your-token to config.env"
    log "  3. Add HETZNER_SERVER_ID=your-server-id to config.env"

    "${SCRIPT_DIR}/emit_result.sh" "system" "snapshot" "warn" "$STARTED_AT" "$(date -Iseconds)" "null" "null" "hetzner" "HETZNER_API_TOKEN not configured"
    exit 0
fi

if [[ -z "${HETZNER_SERVER_ID:-}" ]]; then
    log "ERROR: HETZNER_SERVER_ID not set"
    "${SCRIPT_DIR}/emit_result.sh" "system" "snapshot" "fail" "$STARTED_AT" "$(date -Iseconds)" "null" "null" "hetzner" "HETZNER_SERVER_ID not configured"
    exit 1
fi

HETZNER_API="https://api.hetzner.cloud/v1"
SNAPSHOT_DESC="siteflow-backup-$(date +%Y%m%d)"

# Create snapshot
log "Creating snapshot for server ${HETZNER_SERVER_ID}..."

RESPONSE=$(curl -s -X POST "${HETZNER_API}/servers/${HETZNER_SERVER_ID}/actions/create_image" \
    -H "Authorization: Bearer ${HETZNER_API_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"description\": \"${SNAPSHOT_DESC}\", \"type\": \"snapshot\"}")

ACTION_ID=$(echo "$RESPONSE" | jq -r '.action.id // empty')
IMAGE_ID=$(echo "$RESPONSE" | jq -r '.image.id // empty')
ERROR=$(echo "$RESPONSE" | jq -r '.error.message // empty')

if [[ -n "$ERROR" ]]; then
    log "ERROR: Failed to create snapshot: $ERROR"
    "${SCRIPT_DIR}/emit_result.sh" "system" "snapshot" "fail" "$STARTED_AT" "$(date -Iseconds)" "null" "null" "hetzner" "$ERROR"
    exit 1
fi

log "Snapshot creation started: Image ID $IMAGE_ID, Action ID $ACTION_ID"

# Wait for completion (max 30 minutes)
MAX_WAIT=1800
WAITED=0
while [[ $WAITED -lt $MAX_WAIT ]]; do
    STATUS_RESPONSE=$(curl -s "${HETZNER_API}/actions/${ACTION_ID}" \
        -H "Authorization: Bearer ${HETZNER_API_TOKEN}")

    ACTION_STATUS=$(echo "$STATUS_RESPONSE" | jq -r '.action.status')

    if [[ "$ACTION_STATUS" == "success" ]]; then
        log "Snapshot created successfully"
        break
    elif [[ "$ACTION_STATUS" == "error" ]]; then
        ERROR=$(echo "$STATUS_RESPONSE" | jq -r '.action.error.message // "Unknown error"')
        log "ERROR: Snapshot creation failed: $ERROR"
        "${SCRIPT_DIR}/emit_result.sh" "system" "snapshot" "fail" "$STARTED_AT" "$(date -Iseconds)" "null" "$IMAGE_ID" "hetzner" "$ERROR"
        exit 1
    fi

    sleep 30
    WAITED=$((WAITED + 30))
    log "  Waiting for snapshot... ($WAITED/${MAX_WAIT}s)"
done

if [[ $WAITED -ge $MAX_WAIT ]]; then
    log "WARNING: Snapshot creation timed out (may still complete)"
fi

# Prune old snapshots
log "Pruning old snapshots (keeping ${SNAPSHOT_KEEP_COUNT})..."

SNAPSHOTS=$(curl -s "${HETZNER_API}/images?type=snapshot&sort=created:desc" \
    -H "Authorization: Bearer ${HETZNER_API_TOKEN}" | jq -r '.images[] | select(.description | startswith("siteflow-backup-")) | .id')

COUNT=0
for SNAP_ID in $SNAPSHOTS; do
    COUNT=$((COUNT + 1))
    if [[ $COUNT -gt ${SNAPSHOT_KEEP_COUNT} ]]; then
        log "  Deleting old snapshot: $SNAP_ID"
        curl -s -X DELETE "${HETZNER_API}/images/${SNAP_ID}" \
            -H "Authorization: Bearer ${HETZNER_API_TOKEN}" > /dev/null
    fi
done

ENDED_AT=$(date -Iseconds)

"${SCRIPT_DIR}/emit_result.sh" "system" "snapshot" "ok" "$STARTED_AT" "$ENDED_AT" "null" "$IMAGE_ID" "hetzner" "null"

log "=== Weekly snapshot complete ==="
