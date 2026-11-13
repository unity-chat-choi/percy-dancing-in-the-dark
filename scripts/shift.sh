#!/bin/bash
# Warm QC worker for one platform during a work-hours shift (GitHub-hosted, max 6h per job).
# Builds the staging Debug app once, keeps the simulator/emulator + Metro up, then takes tasks labelled
# "<platform>-todo" from the private task repo until 15 min before the shift ends.
# JS-only branches: Metro serves the new code (no rebuild). Native changes: incremental rebuild.
# Usage: shift.sh <ios|android>   Env: MINUTES, secrets (see shift.yml). Public log: counts only.
set -uo pipefail
P="$1"; O=$([ "$P" = ios ] && echo android || echo ios)
W="$PWD"; R="$W/runner/scripts"; END=$(( $(date +%s) + ${MINUTES:-120} * 60 - 15 * 60 ))
AUTH="Authorization: Basic $(printf 'oauth2:%s' "$GITLAB_TOKEN" | base64 | tr -d '\n')"
REPO_URL="https://gitlab.com/$GITLAB_PROJECT.git"
gl() { git -c http.extraHeader="$AUTH" "$@"; }
log() { echo "[$(date +%H:%M)] $*"; }

build_app() {  # full or incremental build + install
  if [ "$P" = ios ]; then
    (cd ios && bundle exec pod install >/tmp/pod.log 2>&1) || { log "pod install failed"; return 1; }
    xcodebuild -workspace ios/uniscore.xcworkspace -scheme uniscoreStag -configuration DebugStag -sdk iphonesimulator \
      -destination 'generic/platform=iOS Simulator' -derivedDataPath "$W/build" ARCHS=arm64 ONLY_ACTIVE_ARCH=YES \
      EXCLUDED_ARCHS=x86_64 CODE_SIGNING_ALLOWED=NO COMPILER_INDEX_STORE_ENABLE=NO -quiet >/tmp/build.log 2>&1 \
      || { log "ios build failed"; return 1; }
    APP=$(ls -d "$W"/build/Build/Products/DebugStag-iphonesimulator/*.app | grep -v Extension | head -1)
    xcrun simctl install booted "$APP"
    APP_ID=$(/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$APP/Info.plist")
  else
    (cd android && ENVFILE=.env.staging ./gradlew :app:assembleStagingDebug -PreactNativeArchitectures=x86_64 \
      --build-cache -q >/tmp/build.log 2>&1) || { log "android build failed"; return 1; }
    adb install -r "$(ls android/app/build/outputs/apk/staging/debug/*.apk | head -1)" >/dev/null
    APP_ID=com.unity.uniscore.stag
    adb reverse tcp:8081 tcp:8081 >/dev/null
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

label() { gh api -X "$1" "repos/$TASKS_REPO/issues/$2/labels${3:+/$3}" ${4:+-f "labels[]=$4"} >/dev/null 2>&1; }

# --- warm up
gl clone -q --depth 200 --branch app-develop "$REPO_URL" app && cd app
yarn install --frozen-lockfile --ignore-engines --network-timeout 600000 >/dev/null 2>&1 || yarn install --ignore-engines >/dev/null 2>&1
if [ "$P" = ios ]; then
  sudo xcode-select -s "$(ls -d /Applications/Xcode_*.app | grep -v -i beta | sort -V | tail -1)" >/dev/null
  udid=$(xcrun simctl list devices available -j | python3 -c "import json,sys;d=json.load(sys.stdin)['devices'];print(next(x['udid'] for r in sorted(d,reverse=True) if 'iOS' in r for x in d[r] if x['name'].startswith('iPhone') and x['name'].endswith('Pro')))")
  xcrun simctl boot "$udid" && xcrun simctl bootstatus "$udid" -b >/dev/null
  (cd ios && bundle install --quiet >/dev/null 2>&1)
fi
(npx react-native start --port 8081 >/tmp/metro.log 2>&1 &)
build_app || exit 1
curl -Ls "https://get.maestro.mobile.dev" | bash >/dev/null 2>&1; export PATH="$HOME/.maestro/bin:$PATH"
npm i -g --silent @anthropic-ai/claude-code >/dev/null 2>&1
BASE=$(git rev-parse HEAD); DONE=0
log "warm, taking tasks"

# --- task loop
while [ "$(date +%s)" -lt "$END" ]; do
  N=$(gh api "repos/$TASKS_REPO/issues?labels=$P-todo&state=open&sort=created&direction=asc" --jq '.[0].number // empty' 2>/dev/null)
  [ -z "$N" ] && { sleep 30; continue; }
  label POST "$N" "" "$P-running"; label DELETE "$N" "$P-todo"
  export ISSUE="$N"; cd "$W"; rm -rf ctx shots; mkdir -p ctx/figma shots
  gh api "repos/$TASKS_REPO/issues/$N" --jq .body > ctx/task.md
  BRANCH=$(grep -m1 -oE '^branch:[[:space:]]*\S+' ctx/task.md | sed -E 's/^branch:[[:space:]]*//')
  KEY=$(grep -m1 -oE '(US|UTD|UOB)-[0-9]+' <<<"$BRANCH"); export KEY
  echo "::add-mask::$BRANCH"; echo "::add-mask::$KEY"; echo "::add-mask::${BRANCH##*/}"
  log "task #$N"
  cd app
  REF="$BRANCH"; gl ls-remote --exit-code --heads "$REPO_URL" "runner/$BRANCH" >/dev/null 2>&1 && REF="runner/$BRANCH"
  gl fetch -q --depth 50 origin "$REF" && git checkout -q -f FETCH_HEAD && git clean -qfd
  if git diff --name-only "$BASE" HEAD 2>/dev/null | grep -qE '^(ios/|android/|package\.json|yarn\.lock|patches/)'; then
    log "native change: rebuilding"
    yarn install --ignore-engines >/dev/null 2>&1
    build_app || { echo "Build $P lỗi (rebuild trong ca)." > "$W/ctx/build-errors.txt"; }
    BASE=$(git rev-parse HEAD)
  fi
  reset_device
  cd "$W"
  python3 -I "$R/ticket-context.py" "$KEY" ctx/context.md >/dev/null && python3 -I "$R/figma-render.py" ctx/context.md ctx/figma >/dev/null
  ACC=$(python3 -I "$R/pick-account.py" "${ACCOUNT:-auto}" 2>/dev/null)
  TOKEN_VAR="CLAUDE_CODE_OAUTH_TOKEN_${ACC:-1}"
  if [ -n "$ACC" ] && [ ! -s ctx/build-errors.txt ]; then
    prompt="$(cat runner/prompts/qc.md; echo; sed "s/\$APP_ID/$APP_ID/g" "runner/prompts/qc-$P.md")"$'\n\n'"Ticket: $KEY. The app is a Debug build served by Metro on port 8081; after switching mode just relaunch it."
    # Claude gets only its own token: GitLab/Jira/Figma/GitHub secrets are not in its environment.
    (cd app && timeout 5400 env -i HOME="$HOME" PATH="$PATH" LANG=en_US.UTF-8 ANDROID_HOME="${ANDROID_HOME:-}" \
      CLAUDE_CODE_OAUTH_TOKEN="${!TOKEN_VAR}" claude -p "$prompt" --model "${MODEL:-sonnet}" --dangerously-skip-permissions \
      --add-dir ../ctx --add-dir ../shots --output-format json \
      --disallowedTools Edit Write "Bash(git *)" "Bash(curl*)" WebFetch WebSearch > ../ctx/qc.json 2>/dev/null) || true
  fi
  bash "$R/qc-report.sh" "$P" "shift"
  label DELETE "$N" "$P-running"; label POST "$N" "" "$P-done"
  # Whoever finishes last (or alone) sends the merged report.
  LABELS=$(gh api "repos/$TASKS_REPO/issues/$N" --jq '[.labels[].name] | join(",")')
  if ! grep -qE "(^|,)($O-todo|$O-running|reported)(,|$)" <<<"$LABELS"; then
    label POST "$N" "" "reported"
    mkdir -p qc; for p in ios android; do python3 -I "$R/task-files.py" get "$N" "$p" "qc/$p" >/dev/null; done
    python3 -I "$R/merge-report.py" "$KEY · QC iOS + Android · task #$N" ctx/figma qc "$N" out >/dev/null
    gh api -X POST "repos/$TASKS_REPO/issues/$N/comments" -F body=@out/comment.md >/dev/null
    python3 -I "$R/tg-report.py" out/telegram.md ctx/context.md "$KEY · QC iOS + Android · task #$N" >/dev/null
    python3 -I "$R/tg-doc.py" out/report.html ctx/context.md "$KEY · so sánh Figma | iOS | Android (mở file HTML)" >/dev/null
    rm -rf qc out
  fi
  DONE=$((DONE + 1)); log "task done ($DONE this shift)"
done
log "shift over: $DONE tasks"
