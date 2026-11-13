#!/bin/bash
# Store one platform's QC result in the private task repo (qc/issue-N/<platform>/): report, pairs.json, screenshots.
# The `report` job merges iOS + Android into one comment, one Telegram message and one HTML.
# Usage: qc-report.sh <ios|android> <job status>   (cwd = workspace; uses ctx/, shots/, runner/)
set -uo pipefail
P="$1"; STATUS="$2"
if [ ! -s ctx/qc-report.md ]; then
  { echo "## Kết quả: CHƯA TEST ĐƯỢC"; echo
    if [ -s ctx/build-errors.txt ]; then echo "Build $P lỗi:"; cat ctx/build-errors.txt; else echo "Bước $P dừng trước khi QC xong ($STATUS)."; fi
  } > ctx/qc-report.md
fi
[ -s ctx/pairs.json ] || echo '[]' > ctx/pairs.json
python3 -I runner/scripts/task-files.py put "$ISSUE" "$P" ctx/qc-report.md ctx/pairs.json shots/*.png
echo "qc stored ($P)"
