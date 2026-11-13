#!/bin/bash
# After the RN MR is open and the Kotlin port is triggered: queue the Jira "done" comment.
# Downloads the task's app screenshots (dark + light first, max 4) and adds an entry to ~/.claude/port-queue.json.
# ~/.claude/bin/port-watch.sh (launchd, every 15 min) then waits for the uniscore-kotlin MR with the same branch,
# posts the team comment (images, MR RN, MR Android, cc Mason) and moves the ticket to REVIEW CODE.
# Usage: scripts/queue-port.sh <task number> <RN MR iid> [extra Jira keys sharing the branch...]
set -euo pipefail
N="${1:?task number}"; RNMR="${2:?RN MR iid}"; shift 2; EXTRA="$*"
set -a; . "${RUNNER_ENV:-$HOME/.config/cutcut/uniscore-runner-secrets.env}"; set +a
BODY=$(gh api "repos/$TASKS_REPO/issues/$N" --jq .body)
BRANCH=$(grep -m1 -oE '^branch:[[:space:]]*\S+' <<<"$BODY" | sed -E 's/^branch:[[:space:]]*//')
KEY=$(grep -m1 -oE '(US|UTD|UOB)-[0-9]+' <<<"$BRANCH")
DIR="$HOME/.cache/port-shots/issue-$N"; mkdir -p "$DIR"
NAMES=$(gh api "repos/$TASKS_REPO/contents/shots/issue-$N" --jq '.[].name' 2>/dev/null | grep -vE '^[A-Za-z0-9]{20,}_' || true)
# Team format shows dark | light side by side: take dark+light of the first screens, RTL only if nothing else.
PICK=$( { grep -E 'dark' <<<"$NAMES" | head -2; grep -E 'light' <<<"$NAMES" | head -2; } | head -4)
[ -n "$PICK" ] || PICK=$(head -4 <<<"$NAMES")
IMGS=()
for f in $PICK; do
  gh api "repos/$TASKS_REPO/contents/shots/issue-$N/$f" -H "Accept: application/vnd.github.raw" > "$DIR/$f"
  IMGS+=("$DIR/$f")
done
python3 -I - "$HOME/.claude/port-queue.json" "$BRANCH" "$RNMR" "$KEY $EXTRA" "${IMGS[@]:-}" <<'PY'
import json, os, sys
q_path, branch, rn_mr, keys, imgs = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4].split(), [i for i in sys.argv[5:] if i]
q = json.load(open(q_path)) if os.path.exists(q_path) else []
if any(e["branch"] == branch and not e.get("done") for e in q):
    sys.exit(f"already queued: {branch}")
q.append({"branch": branch, "rn_mr": int(rn_mr), "tickets": [{"key": k, "images": imgs} for k in keys]})
json.dump(q, open(q_path, "w"), indent=1)
print(f"queued {branch}: MR RN !{rn_mr}, tickets {keys}, {len(imgs)} images")
PY
