#!/bin/bash
# Emit backup run result to SiteFlow API
# Usage: emit_result.sh <site> <job_type> <status> <started_at> <ended_at> [bytes_written] [backup_id] [repo] [error]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.env"

SITE="${1:-system}"
JOB_TYPE="${2:-unknown}"
STATUS="${3:-fail}"
STARTED_AT="${4:-$(date -Iseconds)}"
ENDED_AT="${5:-$(date -Iseconds)}"
BYTES_WRITTEN="${6:-null}"
BACKUP_ID="${7:-null}"
REPO="${8:-null}"
ERROR="${9:-null}"

# Generate run ID
RUN_ID="$(date +%Y%m%d%H%M%S)-${JOB_TYPE}-$$"

# Build JSON payload
if [[ "$BYTES_WRITTEN" == "null" ]]; then
    BYTES_JSON="null"
else
    BYTES_JSON="$BYTES_WRITTEN"
fi

if [[ "$BACKUP_ID" == "null" ]]; then
    BACKUP_ID_JSON="null"
else
    BACKUP_ID_JSON="\"$BACKUP_ID\""
fi

if [[ "$REPO" == "null" ]]; then
    REPO_JSON="null"
else
    REPO_JSON="\"$REPO\""
fi

if [[ "$ERROR" == "null" ]]; then
    ERROR_JSON="null"
else
    # Escape quotes and newlines in error message
    ESCAPED_ERROR=$(echo "$ERROR" | jq -Rs '.')
    ERROR_JSON="$ESCAPED_ERROR"
fi

JSON_PAYLOAD=$(cat <<EOF
{
  "site": "$SITE",
  "job_type": "$JOB_TYPE",
  "status": "$STATUS",
  "started_at": "$STARTED_AT",
  "ended_at": "$ENDED_AT",
  "bytes_written": $BYTES_JSON,
  "backup_id": $BACKUP_ID_JSON,
  "repo": $REPO_JSON,
  "error": $ERROR_JSON
}
EOF
)

# Save to local file
mkdir -p "${RUN_DIR}"
echo "$JSON_PAYLOAD" > "${RUN_DIR}/${RUN_ID}.json"

# POST to SiteFlow API with retry
MAX_RETRIES=3
RETRY_DELAY=5

for ((i=1; i<=MAX_RETRIES; i++)); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$JSON_PAYLOAD" \
        "${SITEFLOW_API}" 2>/dev/null || echo "000")

    if [[ "$HTTP_CODE" == "200" ]] || [[ "$HTTP_CODE" == "201" ]]; then
        echo "Result posted successfully (HTTP $HTTP_CODE)"
        exit 0
    fi

    if [[ $i -lt $MAX_RETRIES ]]; then
        echo "POST failed (HTTP $HTTP_CODE), retrying in ${RETRY_DELAY}s... (attempt $i/$MAX_RETRIES)"
        sleep $RETRY_DELAY
        RETRY_DELAY=$((RETRY_DELAY * 2))
    fi
done

echo "WARNING: Failed to POST result to SiteFlow API after $MAX_RETRIES attempts"
echo "Result saved locally: ${RUN_DIR}/${RUN_ID}.json"
exit 1
