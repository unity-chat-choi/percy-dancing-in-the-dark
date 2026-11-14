#!/bin/bash
# Runs inside android-emulator-runner (emulator booted): install the staging APK, then Claude QC.
set -uo pipefail
adb install -r "$APK" >/dev/null && echo "apk installed $(date -u +%H:%M:%S)"
AAPT=$(ls "$ANDROID_HOME"/build-tools/*/aapt2 2>/dev/null | sort -V | tail -1)
export APP_ID=$("$AAPT" dump packagename "$APK" 2>/dev/null || echo com.unity.uniscore.stag)
[ "${QC:-true}" = false ] && exit 0  # speed test: stop once the app is installed
npm i -g --silent @anthropic-ai/claude-code >/dev/null 2>&1
date +%s > ctx/qc-start
cd app
prompt="$(cat ../runner/prompts/qc.md; echo; sed "s/\$APP_ID/$APP_ID/g" ../runner/prompts/qc-android.md)"$'\n\n'"Ticket: $KEY."
perl -e 'alarm shift; exec @ARGV' 2700 claude -p "$prompt" --model "$MODEL" --dangerously-skip-permissions \
  --add-dir ../ctx --add-dir ../shots --output-format json \
  --disallowedTools Edit Write "Bash(git *)" "Bash(curl*)" WebFetch WebSearch \
  > ../ctx/qc.json 2>/dev/null || echo "claude exited non-zero"
echo "shots: $(ls ../shots | wc -l)"
