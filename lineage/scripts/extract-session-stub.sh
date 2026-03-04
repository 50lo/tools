#!/usr/bin/env bash
set -euo pipefail

json_escape() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/\\n}"
  value="${value//$'\r'/\\r}"
  value="${value//$'\t'/\\t}"
  printf '%s' "$value"
}

repo_root="${LINEAGE_REPO_ROOT:-$(pwd)}"
commit="${LINEAGE_COMMIT:-unknown}"
event="${LINEAGE_EVENT:-unknown}"
timestamp_ms="$(( $(date +%s) * 1000 ))"
timestamp_agent="$(( timestamp_ms + 25 ))"
short_commit="${commit:0:12}"

repo_root_json="$(json_escape "$repo_root")"
commit_json="$(json_escape "$commit")"
event_json="$(json_escape "$event")"
short_commit_json="$(json_escape "$short_commit")"

cat <<EOF
{
  "session-id": "stub-${short_commit_json}",
  "source": "lineage-stub",
  "repo-root": "${repo_root_json}",
  "commit": "${commit_json}",
  "event": "${event_json}",
  "messages": [
    {
      "message-type": "user",
      "timestamp": ${timestamp_ms},
      "message": "Implement sorting functionality in transactions table on the account page."
    },
    {
      "message-type": "agent",
      "timestamp": ${timestamp_agent},
      "message": "<thinking>I need to find where transactions table is implemented in frontend code.</thinking>"
    }
  ]
}
EOF
