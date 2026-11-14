#!/bin/bash
# Warm QC worker for one platform during a work-hours shift (GitHub-hosted, max 6h per job).
# Builds the staging Debug app once, keeps the simulator/emulator + Metro up, then takes tasks labelled
# "<platform>-todo" from the private task repo until 15 min before the shift ends.
# JS-only branches: Metro serves the new code (no rebuild). Native changes: incremental rebuild.
# Usage: shift.sh <ios|android>   Env: MINUTES, secrets (see shift.yml). Public log: counts only.
set -uo pipefail
P="$1"; O=$([ "$P" = ios ] && echo android || echo ios)
W="$PWD"; R="$W/runner/scripts"; START=$(date +%s); END=$(( START + ${MINUTES:-120} * 60 - 15 * 60 ))
RELAY_AT=$(( START + ${MINUTES:-120} * 60 - 20 * 60 )); RELAYED=0   # 20 min before the end: start the next shift
AUTH="Authorization: Basic $(printf 'oauth2:%s' "$GITLAB_TOKEN" | base64 | tr -d '\n')"
REPO_URL="https://gitlab.com/$GITLAB_PROJECT.git"
gl() { git -c http.extraHeader="$AUTH" "$@"; }
log() { echo "[$(date +%H:%M)] $*"; }

# Simulator architecture follows the Mac: Apple Silicon → arm64, Intel → x86_64.
if [ "$(uname -m)" = arm64 ]; then SIM_ARCH=arm64; SIM_EXCLUDE=x86_64; else SIM_ARCH=x86_64; SIM_EXCLUDE=arm64; fi

build_app() {  # full or incremental build + install
  if [ "$P" = ios ]; then
    # Cold Intel runners hit flaky CocoaPods CDN downloads: retry with a spec repo update.
    (cd ios && { bundle exec pod install >/tmp/pod.log 2>&1 || { sleep 30; bundle exec pod install --repo-update >/tmp/pod.log 2>&1; } \
      || { sleep 60; bundle exec pod install --repo-update >/tmp/pod.log 2>&1; }; }) || { log "pod install failed"; return 1; }
    xcodebuild -workspace ios/uniscore.xcworkspace -scheme uniscoreStag -configuration ReleaseStag -sdk iphonesimulator \
      -destination 'generic/platform=iOS Simulator' -derivedDataPath "$W/build" ARCHS=$SIM_ARCH ONLY_ACTIVE_ARCH=YES \
      EXCLUDED_ARCHS=$SIM_EXCLUDE CODE_SIGNING_ALLOWED=NO COMPILER_INDEX_STORE_ENABLE=NO DEBUG_INFORMATION_FORMAT=dwarf -quiet >/tmp/build.log 2>&1 \
      || { log "ios build failed"; return 1; }
    APP=$(ls -d "$W"/build/Build/Products/ReleaseStag-iphonesimulator/*.app | grep -v Extension | head -1)
    xcrun simctl install booted "$APP"
    APP_ID=$(/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$APP/Info.plist")
  else
    (cd android && ENVFILE=.env.staging ./gradlew :app:assembleStagingRelease \
      --build-cache -q >/tmp/build.log 2>&1) || { log "android build failed"; return 1; }
    adb install -r "$(ls android/app/build/outputs/apk/staging/release/*.apk | head -1)" >/dev/null
    APP_ID=com.unity.uniscore.stag
  fi
  export APP_ID; log "app built + installed ($P)"
}

reset_device() {  # back to light / LTR / English between tasks
  if [ "$P" = ios ]; then
    xcrun simctl ui booted appearance light; xcrun simctl spawn booted defaults write -g AppleLanguages -array en
    xcrun simctl terminate booted "$APP_ID" 2>/dev/null; xcrun simctl launch booted "$APP_ID" >/dev/null 2>&1
  else
    adb shell cmd uimode night no; adb shell settings put global debug.force_rtl 0
    adb shell am force-stop "$APP_ID"; adb shell monkey -p "$APP_ID" 1 >/dev/null 2>&1
  fi
}

step() { python3 -I "$R/progress.py" "$1" "$P" "${@:2}"; }

label() { gh api -X "$1" "repos/$TASKS_REPO/issues/$2/labels${3:+/$3}" ${4:+-f "labels[]=$4"} >/dev/null 2>&1; }

send_report() {  # <issue> <reported|reported-partial>: merged report of whatever platforms have results
  local n="$1" mark="$2" key
  cd "$W"; rm -rf qc out; mkdir -p qc ctx/figma
  key=$(gh api "repos/$TASKS_REPO/issues/$n" --jq .title | grep -oE '(US|UTD|UOB)-[0-9]+' | head -1)
  echo "::add-mask::$key"
  [ -s ctx/context.md ] && [ "${KEY:-}" = "$key" ] || { python3 -I "$R/ticket-context.py" "$key" ctx/context.md >/dev/null; rm -f ctx/figma/*; python3 -I "$R/figma-render.py" ctx/context.md ctx/figma >/dev/null; }
  for p in ios android; do python3 -I "$R/task-files.py" get "$n" "$p" "qc/$p" >/dev/null; done
  local tag=""; [ "$mark" = reported-partial ] && tag=" (một phần: $O chưa test, hết ca)"
  ls ctx/figma/*.png >/dev/null 2>&1 && python3 -I "$R/task-files.py" put "$n" figma ctx/figma/*.png
  python3 -I "$R/merge-report.py" "$key · QC iOS + Android · task #$n$tag" ctx/figma qc "$n" out >/dev/null
  gh api -X POST "repos/$TASKS_REPO/issues/$n/comments" -F body=@out/comment.md >/dev/null
  python3 -I "$R/tg-report.py" out/telegram.md ctx/context.md "$key · QC · task #$n$tag" >/dev/null
  python3 -I "$R/tg-doc.py" out/report.html ctx/context.md "$key · so sánh Figma | iOS | Android (mở file HTML)" >/dev/null
  label DELETE "$n" "reported-partial"; label POST "$n" "" "$mark"
  rm -rf qc out
}

# --- warm up
# app/ may already hold cached node_modules (and ios/Pods): init in place instead of cloning into it.
mkdir -p app && cd app && git init -q 2>/dev/null; git remote add origin "$REPO_URL" 2>/dev/null
gl fetch -q --depth 200 origin app-develop && git checkout -q -f FETCH_HEAD
yarn install --frozen-lockfile --ignore-engines --network-timeout 600000 >/dev/null 2>&1 || yarn install --ignore-engines >/dev/null 2>&1
if [ "$P" = ios ]; then
  sudo xcode-select -s "$(ls -d /Applications/Xcode_*.app | grep -v -i beta | sort -V | tail -1)" >/dev/null
  udid=$(xcrun simctl list devices available -j | python3 -c "import json,sys;d=json.load(sys.stdin)['devices'];print(next(x['udid'] for r in sorted(d,reverse=True) if 'iOS' in r for x in d[r] if x['name'].startswith('iPhone') and x['name'].endswith('Pro')))")
  xcrun simctl boot "$udid" && xcrun simctl bootstatus "$udid" -b >/dev/null
  (cd ios && bundle install --quiet >/dev/null 2>&1)
fi
alert() {  # private Telegram group (General): build broken on app-develop, etc.
  python3 -I - "$1" <<'PYA'
import json, os, sys, urllib.request
msg = {"chat_id": os.environ["TG_NOTIFY_CHAT_ID"], "text": sys.argv[1][:3900], "disable_web_page_preview": True}
urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{os.environ['TG_TICKET_BOT_TOKEN']}/sendMessage",
                       data=json.dumps(msg).encode(), headers={"Content-Type": "application/json"}), timeout=20)
PYA
}
if ! build_app; then
  # One alert per shift and platform (worker 1 only): app-develop itself does not build.
  if [ "${WORKER:-1}" = 1 ]; then
    errs=$( { grep -E ' error: |^e: |error:|What went wrong' -A2 /tmp/build.log | head -25; } 2>/dev/null )
    alert "⚠️ app-develop build lỗi trên máy $P lúc khởi động ca ($(git log -1 --format='%h %an: %s' 2>/dev/null)).
$errs"
  fi
  exit 1
fi
curl -Ls "https://get.maestro.mobile.dev" | bash >/dev/null 2>&1; export PATH="$HOME/.maestro/bin:$PATH"
npm i -g --silent @anthropic-ai/claude-code >/dev/null 2>&1
BASE=$(git rev-parse HEAD); DONE=0
CLAIM_SHA=$(gh api "repos/$TASKS_REPO/commits/HEAD" --jq .sha)
log "warm, taking tasks (worker ${WORKER:-1}, $(uname -m), warm-up $(( ($(date +%s) - START) / 60 )) min)"

relay() {  # one worker (ios 1) starts the next shift while this one finishes, only if work is left
  [ "$RELAYED" = 1 ] || [ "$P" != ios ] || [ "${WORKER:-1}" != 1 ] || [ "$(date +%s)" -lt "$RELAY_AT" ] && return
  RELAYED=1
  [ -n "$(gh api "repos/$TASKS_REPO/issues?state=open&per_page=100" --jq '.[] | select([.labels[].name] | (index("ios-todo") or index("android-todo") or index("ios-running") or index("android-running") or index("running"))) | .number' 2>/dev/null)" ] || return
  gh workflow run shift.yml -R "$GITHUB_REPOSITORY" -f minutes=350 -f ios_workers="${IOS_WORKERS:-3}" -f android_workers="${ANDROID_WORKERS:-3}" >/dev/null 2>&1 \
    && log "relay: next shift started" || log "relay failed"
}

# --- task loop
while [ "$(date +%s)" -lt "$END" ]; do
  relay
  N=""
  for c in $(gh api "repos/$TASKS_REPO/issues?labels=$P-todo&state=open&sort=created&direction=asc" --jq '.[].number' 2>/dev/null); do
    # Creating a ref is atomic: only one worker gets it, the others move on to the next task.
    if gh api -X POST "repos/$TASKS_REPO/git/refs" -f ref="refs/claims/$c-$P" -f sha="$CLAIM_SHA" >/dev/null 2>&1; then N=$c; break; fi
  done
  # The job is killed at 360 min: never start a task that cannot finish, leave it to the next shift.
  HARD=$(( START + ${MINUTES:-120} * 60 + 3 * 60 )); LEFT=$(( HARD - $(date +%s) ))
  if [ "$LEFT" -lt 3600 ]; then
    [ -n "$N" ] && gh api -X DELETE "repos/$TASKS_REPO/git/refs/claims/$N-$P" >/dev/null 2>&1
    log "under 60 min left: leaving the rest to the next shift"; RELAY_AT=0; relay; break
  fi
  if [ -z "$N" ]; then
    # Nothing to take: leave after 20 idle minutes, unless a fix round may still send work back to this platform.
    IDLE=$(( ${IDLE:-0} + 30 ))
    if [ "$IDLE" -ge 1200 ] && [ -z "$(gh api "repos/$TASKS_REPO/issues?state=open&per_page=100" --jq '.[] | select([.labels[].name] | (index("running") or index("ios-running") or index("android-running") or index("ios-todo") or index("android-todo"))) | .number' 2>/dev/null)" ]; then
      log "idle 20 min, queue empty: leaving the shift"; break
    fi
    sleep 30; continue
  fi
  IDLE=0
  label POST "$N" "" "$P-running"; label DELETE "$N" "$P-todo"
  step "$N" "Nhận task (máy $P ${WORKER:-1})"
  export ISSUE="$N"; cd "$W"; rm -rf ctx shots; mkdir -p ctx/figma shots
  # Pick up the newest prompts and helper scripts for every task (not this running file: bash reads it as it goes).
  ( cd runner && git fetch -q origin main && git checkout -q FETCH_HEAD -- prompts $(git ls-tree --name-only FETCH_HEAD scripts/ | grep -v '^scripts/shift.sh$') ) 2>/dev/null || true
  gh api "repos/$TASKS_REPO/issues/$N" --jq .body > ctx/task.md
  BRANCH=$(grep -m1 -oE '^branch:[[:space:]]*\S+' ctx/task.md | sed -E 's/^branch:[[:space:]]*//')
  KEY=$(grep -m1 -oE '(US|UTD|UOB)-[0-9]+' <<<"$BRANCH"); export KEY
  echo "::add-mask::$BRANCH"; echo "::add-mask::$KEY"; echo "::add-mask::${BRANCH##*/}"
  log "task #$N"
  cd app
  REF="$BRANCH"; gl ls-remote --exit-code --heads "$REPO_URL" "runner/$BRANCH" >/dev/null 2>&1 && REF="runner/$BRANCH"
  step "$N" "Lấy code nhánh $([ "$REF" = "$BRANCH" ] && echo của dev || echo runner)"
  gl fetch -q --depth 50 origin "$REF" && git checkout -q -f FETCH_HEAD && git clean -qfd
  if [ "$(git rev-parse HEAD)" != "$BASE" ]; then  # Release build bundles the JS, so any change needs an (incremental) rebuild
    log "rebuilding for this branch"; step "$N" "Build bản Release cho nhánh này"
    yarn install --ignore-engines >/dev/null 2>&1
    build_app || { echo "Build $P lỗi (rebuild trong ca)." > "$W/ctx/build-errors.txt"; }
    BASE=$(git rev-parse HEAD)
  fi
  reset_device
  cd "$W"
  step "$N" "Đọc Jira, Confluence, Figma"
  KEYS=$(grep -oE '(US|UTD|UOB)-[0-9]+' ctx/task.md | sort -u | tr '\n' ' '); for k in $KEYS; do echo "::add-mask::$k"; done
  for k in $KEYS; do python3 -I "$R/ticket-context.py" "$k" "ctx/c-$k.md" >/dev/null; done; cat ctx/c-*.md > ctx/context.md
  python3 -I "$R/figma-render.py" ctx/context.md ctx/figma >/dev/null
  ACC=$(python3 -I "$R/pick-account.py" "${ACCOUNT:-auto}" 2>/dev/null)
  TOKEN_VAR="CLAUDE_CODE_OAUTH_TOKEN_${ACC:-1}"
  if [ -n "$ACC" ] && [ ! -s ctx/build-errors.txt ]; then
    prompt="$(cat runner/prompts/qc.md; echo; sed "s/\$APP_ID/$APP_ID/g" "runner/prompts/qc-$P.md")"$'\n\n'"Ticket(s): $KEYS. The app is a staging Release build (JS bundled); after switching mode relaunch it."
    python3 -I "$R/lessons.py" get ctx/lessons.md >/dev/null
    # same data as the other platform, when it went first
    python3 -I "$R/task-files.py" get "$N" "$O" ctx/peer >/dev/null 2>&1; [ -s ctx/peer/test-data.json ] && cp ctx/peer/test-data.json ctx/peer-test-data.json
    step "$N" "Claude bắt đầu QC"
    # Mirror Claude's own progress lines (../ctx/progress.txt) every 45s while it works.
    ( last=""; while sleep 45; do l=$(tail -1 ctx/progress.txt 2>/dev/null); [ -n "$l" ] && [ "$l" != "$last" ] && { step "$N" "QC: $l"; last="$l"; }; done ) & MIRROR=$!
    # Claude gets only its own token: GitLab/Jira/Figma/GitHub secrets are not in its environment.
    LEFT=$(( HARD - $(date +%s) )); QC_BUDGET=$(( LEFT - 600 < 9000 ? LEFT - 600 : 9000 )); [ "$QC_BUDGET" -lt 60 ] && QC_BUDGET=60  # alarm 0 = none; recheck after the build
    (cd app && perl -e 'alarm shift; exec @ARGV' "$QC_BUDGET" env -i HOME="$HOME" PATH="$PATH" LANG=en_US.UTF-8 ANDROID_HOME="${ANDROID_HOME:-}" \
      CLAUDE_CODE_OAUTH_TOKEN="${!TOKEN_VAR}" claude -p "$prompt" --model "${MODEL:-sonnet}" --dangerously-skip-permissions \
      --add-dir ../ctx --add-dir ../shots --output-format json \
      --disallowedTools Edit Write "Bash(git *)" "Bash(curl*)" WebFetch WebSearch > ../ctx/qc.json 2>/dev/null) || true
  fi
  kill "${MIRROR:-0}" 2>/dev/null; MIRROR=""
  # Account limit hit (or no account free): not the app's fault, so put the task back without using a try.
  if [ -z "$ACC" ] || grep -qiE "hit your (session|usage) limit|usage limit reached|rate_limit" ctx/qc.json 2>/dev/null; then
    label POST "$N" "" "$P-todo"; label DELETE "$N" "$P-running"
    gh api -X DELETE "repos/$TASKS_REPO/git/refs/claims/$N-$P" >/dev/null 2>&1
    step "$N" "Hết lượt Claude, xếp hàng lại (không tính lần thử)"; log "claude limit: requeued"; sleep 600; continue
  fi
  python3 -I "$R/lessons.py" add ctx/lessons-new.md 2>/dev/null || true
  step "$N" "Lưu kết quả QC"
  bash "$R/qc-report.sh" "$P" "shift"   # labels: <P>-done, or back to <P>-todo (retry), or blocked
  case "$(cat ctx/qc-status 2>/dev/null)" in
    done) step "$N" "Xong $P (đủ light/dark/RTL)";;
    retry) step "$N" "Chưa xong $P, xếp hàng thử lại";;
    fixing) step "$N" "QC thấy bug → runner đang sửa, sẽ QC lại";;
    *) step "$N" "Kẹt $P sau 3 lần, đã báo anh";;
  esac
  gh api -X DELETE "repos/$TASKS_REPO/git/refs/claims/$N-$P" >/dev/null 2>&1  # free the claim for a later re-test
  # Whoever finishes last (or alone) sends the merged report.
  LABELS=$(gh api "repos/$TASKS_REPO/issues/$N" --jq '[.labels[].name] | join(",")')
  if grep -qE "(^|,)$P-done(,|$)" <<<"$LABELS" && grep -qE "(^|,)$O-done(,|$)" <<<"$LABELS" && ! grep -qE "(^|,)reported(,|$)" <<<"$LABELS"; then
    send_report "$N" reported
  fi
  DONE=$((DONE + 1)); log "task done ($DONE this shift)"
done
# Shift over: tasks this platform finished while the other is still queued get a partial report now;
# the other platform sends the full one when it gets to them (label reported-partial -> reported).
for n in $(gh api "repos/$TASKS_REPO/issues?labels=$P-done&state=open&per_page=50" --jq '.[] | select([.labels[].name] | (index("reported") or index("reported-partial")) | not) | .number' 2>/dev/null); do
  send_report "$n" reported-partial
done
log "shift over: $DONE tasks"
