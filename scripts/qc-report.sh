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
# QC found bugs in this ticket (or bugs that block it): open a fix round on the runner branch, then QC again (max 2 rounds).
python3 -I - "$ISSUE" "$P" "${RUNNER_REPO:-unity-chat-choi/percy-dancing-in-the-dark}" <<'PYB' || true
import json, os, sys, urllib.request
n, p, runner = sys.argv[1:4]
v = json.load(open("ctx/verdict.json"))
fix = [b for b in v.get("bugs") or [] if b.get("scope") in ("ticket", "blocking")]
other = [b for b in v.get("bugs") or [] if b.get("scope") == "other"]
H = {"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json", "Content-Type": "application/json"}
api = lambda path, data=None, method=None: json.load(urllib.request.urlopen(urllib.request.Request(
    f"https://api.github.com{path}", data=json.dumps(data).encode() if data is not None else None, headers=H, method=method), timeout=30) or [None])
def tg(text):
    m = {"chat_id": os.environ["TG_NOTIFY_CHAT_ID"], "text": text[:3900], "disable_web_page_preview": True}
    urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{os.environ['TG_TICKET_BOT_TOKEN']}/sendMessage",
                           data=json.dumps(m).encode(), headers={"Content-Type": "application/json"}), timeout=20)
repo = os.environ["TASKS_REPO"]
issue = api(f"/repos/{repo}/issues/{n}")
labels = [l["name"] for l in issue["labels"]]
key = os.environ.get("KEY", "")
if other:
    tg(f"🐞 QC {p} thấy bug NGOÀI ticket ({key}, task #{n}) — cần ticket Jira riêng nếu muốn sửa:\n" + "\n".join(f"• {b['title']} ({b.get('where','')})" for b in other))
if v.get("result") != "FAIL" or not fix:
    sys.exit(0)
rounds = sum(1 for l in labels if l.startswith("fix-round-"))
if rounds >= 2:
    tg(f"⛔ {key} · task #{n}: đã sửa 2 vòng mà QC {p} vẫn còn bug, cần anh xem.\n" + "\n".join(f"• {b['title']}" for b in fix)); sys.exit(0)
mark = f"fix-round-{rounds + 1}"
if mark in labels:
    sys.exit(0)  # the other platform already opened this round
api(f"/repos/{repo}/issues/{n}/labels", {"labels": [mark]}, "POST")
body = (issue.get("body") or "") + f"\n\n## Bug QC cần sửa (vòng {rounds + 1}, từ {p})\n" + "\n".join(
    f"- [{b['scope']}] {b['title']} — {b.get('where','')}: {b.get('detail','')}" for b in fix)
api(f"/repos/{repo}/issues/{n}", {"body": body}, "PATCH")
for q in ("ios", "android"):  # both platforms test again after the fix
    for l in (f"{q}-done", f"{q}-todo"):
        try: api(f"/repos/{repo}/issues/{n}/labels/{l}", method="DELETE")
        except Exception: pass
api(f"/repos/{runner}/actions/workflows/ticket.yml/dispatches", {"ref": "main", "inputs": {"issue": str(n)}}, "POST")
tg(f"🔧 {key} · task #{n}: QC {p} thấy {len(fix)} bug của ticket → runner đang sửa (vòng {rounds + 1}), xong sẽ QC lại cả iOS + Android.\n" + "\n".join(f"• {b['title']}" for b in fix))
open("ctx/qc-status", "w").write("fixing")
PYB
echo "qc $P: $(cat ctx/qc-status)"
