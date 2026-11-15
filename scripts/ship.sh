#!/bin/bash
# Mac side of "QC passed on both platforms" (task label `ship`, set by shift.sh):
#   1. fast-forward the dev branch to the runner's commits (runner/<branch>, same GitLab project)
#   2. open the RN MR (target app-develop, reviewer, test screenshots)
#   3. send the Kotlin port (~/.claude/bin/port.sh, needs the migration SSO login on this Mac)
#   4. queue the Jira done-comment for port-watch (queue-port.sh): comment + REVIEW CODE once the Kotlin MR exists
# Each step is idempotent; a step that cannot run yet (SSO expired, push rejected) leaves `ship` for the next run.
# Run by trigger.sh every 5 min. Logs to ~/.claude/logs/ship.log (local only).
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
R="$(cd "$(dirname "$0")" && pwd)"
set -a; . "${RUNNER_ENV:-$HOME/.config/cutcut/uniscore-runner-secrets.env}"; set +a
APP="${APP_REPO:-$HOME/uniscore-mobile}"; REVIEWER="${MR_REVIEWER:?set MR_REVIEWER in the secrets env}"
LOG="$HOME/.claude/logs/ship.log"; mkdir -p "$(dirname "$LOG")"; exec >>"$LOG" 2>&1
notify() { osascript -e "display notification $(python3 -I -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$1") with title \"Ship\"" 2>/dev/null || true; echo "$1"; }
label() { gh api -X "$1" "repos/$TASKS_REPO/issues/$2/labels${3:+/$3}" ${4:+-f "labels[]=$4"} >/dev/null 2>&1 || true; }
ENC() { python3 -I -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1],safe=""))' "$1"; }

for N in $(gh api "repos/$TASKS_REPO/issues?labels=ship&state=open&per_page=20" --jq '.[].number' 2>/dev/null); do
  echo "== $(date '+%F %T') task #$N"
  BODY=$(gh api "repos/$TASKS_REPO/issues/$N" --jq .body)
  TITLE=$(gh api "repos/$TASKS_REPO/issues/$N" --jq .title)
  BR=$(grep -m1 -oE '^branch:[[:space:]]*\S+' <<<"$BODY" | sed -E 's/^branch:[[:space:]]*//')
  KEY=$(grep -m1 -oE '(US|UTD|UOB)-[0-9]+' <<<"$TITLE")
  [ -n "$BR" ] && [ -n "$KEY" ] || { notify "Task #$N: thiếu branch/key, bỏ qua"; continue; }

  # 1. Runner commits -> dev branch (fast-forward only: never overwrite someone's newer push).
  if git -C "$APP" fetch -q origin "runner/$BR" 2>/dev/null; then
    git -C "$APP" push -q origin "FETCH_HEAD:refs/heads/$BR" || { notify "$KEY: push bị từ chối (nhánh có commit mới hơn), cần xem tay"; continue; }
  fi

  # 2. RN MR (reuse an open one).
  MR=$(glab api --hostname gitlab.com "projects/$(ENC "$GITLAB_PROJECT")/merge_requests?state=opened&source_branch=$(ENC "$BR")" 2>/dev/null \
       | python3 -I -c 'import json,sys; d=json.load(sys.stdin); print(d[0]["iid"] if d else "")')
  if [ -z "$MR" ]; then
    SHOTS=$(mktemp -d); IMGMD=""
    for f in $(gh api "repos/$TASKS_REPO/contents/shots/issue-$N" --jq '.[].name' 2>/dev/null | grep -E 'light|dark' | head -4); do
      gh api "repos/$TASKS_REPO/contents/shots/issue-$N/$f" -H "Accept: application/vnd.github.raw" > "$SHOTS/$f"
      IMGMD="$IMGMD $(curl -s -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -F "file=@$SHOTS/$f" "https://gitlab.com/api/v4/projects/$(ENC "$GITLAB_PROJECT")/uploads" | python3 -I -c 'import json,sys;print(json.load(sys.stdin).get("markdown",""))')"
    done
    DESC=$(printf '## What & why\n- **%s**: %s\n- Jira: %s/browse/%s\n\n## Test\n- Runner QC passed on iOS + Android (light, dark, RTL); full report in the task.\n\n## Screenshots\n%s\n' \
      "$KEY" "${TITLE#*$KEY}" "${JIRA_URL%/}" "$KEY" "$IMGMD")
    MR=$(glab mr create -R "$GITLAB_PROJECT" --source-branch "$BR" --target-branch app-develop --title "$KEY ${TITLE#*$KEY}" \
         --description "$DESC" --reviewer "$REVIEWER" --remove-source-branch --yes 2>&1 | grep -oE 'merge_requests/[0-9]+' | grep -oE '[0-9]+$')
    rm -rf "$SHOTS"
    [ -n "$MR" ] || { notify "$KEY: không mở được MR RN"; continue; }
    notify "$KEY: đã mở MR RN !$MR"
  fi

  # 3. Kotlin port (skip if this branch already has a running/done request).
  if ! "$HOME/.claude/bin/port.sh" status "$BR" 2>/dev/null | grep -E "^[0-9]+ \S+ $BR " | grep -qvE "^[0-9]+ (cancelled|failed|rejected) "; then
    "$HOME/.claude/bin/port.sh" send "$BR" >/dev/null 2>&1 || { notify "$KEY: chưa gửi được port (SSO hết hạn: chạy lại login trong port.sh)"; continue; }
    notify "$KEY: đã gửi port Kotlin"
  fi

  # 4. Jira done-comment + REVIEW CODE when the Kotlin MR exists (port-watch).
  bash "$R/queue-port.sh" "$N" "$MR" 2>&1 | tail -1
  label DELETE "$N" ship; label POST "$N" "" shipped
done
