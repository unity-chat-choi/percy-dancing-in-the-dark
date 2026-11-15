#!/bin/bash
# QC hit its time cap (no final result event): resume the same Claude session for 5 min, only to write
# verdict.json / pairs.json / qc-report.md from what it already checked, so a cut run still reports.
# Usage (cwd = app/): qc-wrapup.sh <model>   Env: CLAUDE_CODE_OAUTH_TOKEN
[ -s ../ctx/qc.json ] && exit 0
SID=$(cat ../ctx/qc-session 2>/dev/null); [ -n "$SID" ] || exit 0
echo "QC time cap reached: wrap-up"
perl -e 'alarm shift; exec @ARGV' 300 claude -p "Time is up: stop testing now, no more device or maestro commands. Using only what you already checked and the screenshots in ../shots, write ../ctx/verdict.json (a mode you did not reach is false; then result is BLOCKED and blocker lists what is left), ../ctx/pairs.json and ../ctx/qc-report.md. Save any scenario that already ran successfully to ../ctx/scenarios-new/." \
  --resume "$SID" --model "${1:-sonnet}" --dangerously-skip-permissions --add-dir ../ctx --add-dir ../shots --output-format json \
  --disallowedTools Edit Write "Bash(git *)" "Bash(curl*)" "Bash(maestro*)" "Bash(xcrun*)" "Bash(adb*)" WebFetch WebSearch \
  > ../ctx/qc-wrapup.json 2>/dev/null || echo "wrap-up exited non-zero"
