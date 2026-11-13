#!/bin/bash
# Create a task in the private task repo and start the ticket runner on it.
# Usage: scripts/task.sh <branch> [account 1-3] [model] [notes...]
#   The Jira key is taken from the branch name; the issue title is "<KEY> <Jira summary>".
# Reads ~/.config/cutcut/uniscore-runner-secrets.env (TASKS_REPO, JIRA_*). Needs gh logged in.
set -euo pipefail
BRANCH="${1:?branch required}"; ACCOUNT="${2:-1}"; MODEL="${3:-opus}"; shift $(( $# < 3 ? $# : 3 )); NOTES="$*"
RUNNER="${RUNNER_REPO:-unity-chat-choi/percy-dancing-in-the-dark}"
set -a; . "${RUNNER_ENV:-$HOME/.config/cutcut/uniscore-runner-secrets.env}"; set +a
KEY=$(grep -oE '(US|UTD|UOB)-[0-9]+' <<<"$BRANCH" | head -1)
[ -n "$KEY" ] || { echo "No Jira key in branch name" >&2; exit 2; }

SUMMARY=$(python3 -I - "$KEY" <<'PY'
import base64, json, os, sys, urllib.request
k = sys.argv[1]
auth = base64.b64encode(f"{os.environ['JIRA_EMAIL']}:{os.environ['JIRA_API_TOKEN']}".encode()).decode()
req = urllib.request.Request(f"{os.environ['JIRA_URL'].rstrip('/')}/rest/api/3/issue/{k}?fields=summary",
                             headers={"Authorization": "Basic " + auth, "Accept": "application/json"})
print(json.load(urllib.request.urlopen(req))["fields"]["summary"])
PY
)
BODY=$(printf 'branch: %s\njira: %s/browse/%s\n\n## Ghi chú\n%s\n' "$BRANCH" "${JIRA_URL%/}" "$KEY" "${NOTES:-Làm tiếp phần WIP trên nhánh theo ticket Jira, so với Figma, chạy verify/jest, viết báo cáo.}")
URL=$(gh issue create -R "$TASKS_REPO" --title "$KEY $SUMMARY" --body "$BODY" --label todo)
N=${URL##*/}
gh workflow run ticket.yml -R "$RUNNER" -f issue="$N" -f account="$ACCOUNT" -f model="$MODEL" >/dev/null
echo "task #$N started: $URL"
