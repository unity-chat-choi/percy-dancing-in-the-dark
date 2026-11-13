#!/bin/bash
# Runs inside android-emulator-runner (emulator booted): install the staging APK, then Claude QC.
set -uo pipefail
adb install -r "$APK" >/dev/null && echo "apk installed"
AAPT=$(ls "$ANDROID_HOME"/build-tools/*/aapt2 2>/dev/null | sort -V | tail -1)
export APP_ID=$("$AAPT" dump packagename "$APK" 2>/dev/null || echo com.unity.uniscore.stag)
npm i -g --silent @anthropic-ai/claude-code >/dev/null 2>&1
cd app
prompt="$(cat ../runner/prompts/qc.md; echo; sed "s/\$APP_ID/$APP_ID/g" ../runner/prompts/qc-android.md)"$'\n\n'"Ticket: $KEY."
timeout 5400 claude -p "$prompt" --model "$MODEL" --dangerously-skip-permissions \
  --add-dir ../ctx --add-dir ../shots --output-format json \
  --disallowedTools Edit Write "Bash(git *)" "Bash(curl*)" WebFetch WebSearch \
  > ../ctx/qc.json 2>/dev/null || echo "claude exited non-zero"
echo "shots: $(ls ../shots | wc -l)"
