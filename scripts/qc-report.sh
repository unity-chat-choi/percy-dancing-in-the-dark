#!/bin/bash
# Store one platform's QC result in the private task repo (qc/issue-N/<platform>/) and decide if that platform is DONE.
# Done = verdict PASS or FAIL with light, dark and RTL all covered. Otherwise the platform goes back to the queue
# (max 3 attempts), then the task is marked blocked and Percy is told what blocks it. Writes ctx/qc-status: done|retry|blocked.
# Usage: qc-report.sh <ios|android> <job status>   (cwd = workspace; uses ctx/, shots/, runner/)
set -uo pipefail
P="$1"; STATUS="$2"; R=runner/scripts
if [ ! -s ctx/qc-report.md ]; then
  { echo "## Kết quả: CHƯA TEST ĐƯỢC"; echo
    if [ -s ctx/build-errors.txt ]; then echo "Build $P lỗi:"; cat ctx/build-errors.txt
    else echo "Bước $P dừng trước khi QC xong ($STATUS)."
      [ -s ctx/qc.json ] && python3 -I -c 'import json,sys
d=json.load(open(sys.argv[1]))
print("Claude:", "lỗi" if d.get("is_error") else "xong", "· turns", d.get("num_turns"))
print((d.get("result") or "")[:1500])' ctx/qc.json || echo "Claude không trả kết quả."
    fi
  } > ctx/qc-report.md
fi
[ -s ctx/pairs.json ] || echo '[]' > ctx/pairs.json
[ -s ctx/verdict.json ] || echo '{"result":"BLOCKED","modes":{},"blocker":"no verdict"}' > ctx/verdict.json
python3 -I $R/task-files.py put "$ISSUE" "$P" ctx/qc-report.md ctx/pairs.json ctx/verdict.json ctx/test-data.json shots/*.png

read -r DONE BLOCKER < <(python3 -I -c 'import json,sys
v=json.load(open(sys.argv[1])); m=v.get("modes") or {}
ok = v.get("result") in ("PASS","FAIL") and all(m.get(k) for k in ("light","dark","rtl"))
miss = [k for k in ("light","dark","rtl") if not m.get(k)]
print(1 if ok else 0, (v.get("blocker") or ("thiếu " + ", ".join(miss)) or "").replace("\n"," ")[:300])' ctx/verdict.json)
LABELS=$(gh api "repos/$TASKS_REPO/issues/$ISSUE" --jq '[.labels[].name] | join(",")')
TRIES=$(grep -oE "(^|,)$P-try-[0-9]+" <<<"$LABELS" | grep -oE '[0-9]+$' | sort -n | tail -1); TRIES=${TRIES:-0}
gh api -X DELETE "repos/$TASKS_REPO/issues/$ISSUE/labels/$P-running" >/dev/null 2>&1
if [ "$DONE" = 1 ]; then
  gh api -X POST "repos/$TASKS_REPO/issues/$ISSUE/labels" -f "labels[]=$P-done" >/dev/null; echo done > ctx/qc-status
elif [ "$TRIES" -lt 2 ]; then  # attempts 1 and 2 failed → queue again
  [ "$TRIES" -gt 0 ] && gh api -X DELETE "repos/$TASKS_REPO/issues/$ISSUE/labels/$P-try-$TRIES" >/dev/null 2>&1
  for l in "$P-todo" "$P-try-$((TRIES + 1))"; do gh api -X POST "repos/$TASKS_REPO/issues/$ISSUE/labels" -f "labels[]=$l" >/dev/null; done
  echo retry > ctx/qc-status
else
  gh api -X POST "repos/$TASKS_REPO/issues/$ISSUE/labels" -f "labels[]=blocked" >/dev/null; echo blocked > ctx/qc-status
  python3 -I - "$KEY" "$P" "$ISSUE" "$BLOCKER" <<'PYA'
import json, os, sys, urllib.request
key, p, n, why = sys.argv[1:5]
msg = {"chat_id": os.environ["TG_NOTIFY_CHAT_ID"], "disable_web_page_preview": True,
       "text": f"⛔ {key} · task #{n}: QC {p} kẹt sau 3 lần thử, cần anh xem.\nVướng: {why}\nhttps://github.com/{os.environ['TASKS_REPO']}/issues/{n}"}
urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{os.environ['TG_TICKET_BOT_TOKEN']}/sendMessage",
                       data=json.dumps(msg).encode(), headers={"Content-Type": "application/json"}), timeout=20)
PYA
fi
echo "qc $P: $(cat ctx/qc-status)"
