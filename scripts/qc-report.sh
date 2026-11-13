#!/bin/bash
# Publish one platform's QC result: task comment with screenshots, Telegram text + HTML side-by-side + album.
# Usage: qc-report.sh <ios|android> <job status>   (cwd = workspace; uses ctx/, shots/, runner/)
set -uo pipefail
P="$1"; STATUS="$2"; R=runner/scripts
if [ ! -s ctx/qc-report.md ]; then
  { echo "## Kết quả: CHƯA TEST ĐƯỢC"; echo
    if [ -s ctx/build-errors.txt ]; then echo "Build $P lỗi:"; cat ctx/build-errors.txt; else echo "Bước $P dừng trước khi QC xong ($STATUS)."; fi
  } > ctx/qc-report.md
fi
{ printf '# QC %s\n\n' "$P"; cat ctx/qc-report.md; } > ctx/qc.tmp && mv ctx/qc.tmp ctx/qc-report.md
python3 -I $R/tg-report.py ctx/qc-report.md ctx/context.md "$KEY · test $P · task #$ISSUE"
python3 -I $R/html-report.py "$KEY · test $P · task #$ISSUE" ctx/qc-report.md ctx/pairs.json ctx/figma shots "ctx/report-$P.html"
python3 -I $R/tg-doc.py "ctx/report-$P.html" ctx/context.md "$KEY · $P · báo cáo so sánh (mở file HTML)" || true
for f in shots/*.png; do [ -e "$f" ] && mv "$f" "shots/$P-$(basename "$f")"; done
if ls shots/*.png >/dev/null 2>&1; then
  { echo; echo "### Ảnh app $P (staging)"; python3 -I $R/task-images.py "$ISSUE" shots/*.png; } >> ctx/qc-report.md
  python3 -I $R/tg-photos.py ctx/context.md "$KEY · $P · Figma (ảnh đầu) và app staging" ctx/figma/*.png shots/*.png || true
fi
gh api -X POST "repos/$TASKS_REPO/issues/$ISSUE/comments" -F body=@ctx/qc-report.md >/dev/null
echo "qc report sent ($P)"
