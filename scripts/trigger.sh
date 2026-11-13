#!/bin/bash
# Mac-side scheduler (launchd, every 5 min): GitHub cron is unreliable, workflow_dispatch is not.
# 09:00 → shift (350 min) + daily · 15:00 → shift (175 min) · every run → daily poll (buttons, ❤).
# Weekdays only for shifts/daily. Marks in ~/.cache/percy-trigger so each slot fires once per day.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
R="${RUNNER_REPO:-unity-chat-choi/percy-dancing-in-the-dark}"; M="$HOME/.cache/percy-trigger"; mkdir -p "$M"
D=$(TZ=Asia/Ho_Chi_Minh date +%F); H=$(TZ=Asia/Ho_Chi_Minh date +%H%M); DOW=$(TZ=Asia/Ho_Chi_Minh date +%u)
once() { [ -e "$M/$D-$1" ] && return 1; touch "$M/$D-$1"; }
shift_running() { [ "$(gh api "repos/$R/actions/workflows/shift.yml/runs?status=in_progress" --jq .total_count 2>/dev/null)" != 0 ]; }
if [ "$DOW" -le 5 ]; then
  if [ "$H" -ge 0900 ] && [ "$H" -lt 1500 ] && once shift1; then shift_running || gh workflow run shift.yml -R "$R" -f minutes=$(( (15*60 - 10#${H:0:2}*60 - 10#${H:2:2}) - 5 )) ; fi
  if [ "$H" -ge 1500 ] && [ "$H" -lt 1745 ] && once shift2; then shift_running || gh workflow run shift.yml -R "$R" -f minutes=$(( (18*60 - 10#${H:0:2}*60 - 10#${H:2:2}) - 5 )) ; fi
  if [ "$H" -ge 0900 ] && [ "$H" -lt 1100 ] && once daily; then gh workflow run daily.yml -R "$R" -f dryrun=false; fi
fi
gh workflow run daily.yml -R "$R" -f poll=true -f dryrun=false >/dev/null 2>&1
# Backup for the 15-min scan cron (GitHub cron is unreliable): one dispatch per quarter hour.
Q="$M/scan-$(date +%Y%m%d%H)-$(( 10#$(date +%M) / 15 ))"; [ -e "$Q" ] || { touch "$Q"; gh workflow run scan.yml -R "$R" >/dev/null 2>&1; }
find "$M" -type f -mtime +7 -delete
