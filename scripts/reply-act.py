"""Act on Claude's decision about one Jira comment (prompts/reply.md → ctx/claude.json).

  none       Telegram note only
  reply      Jira reply (author tagged) + Telegram "đã rep"
  fix        Jira acknowledgement + note on the ticket's runner task + start ticket.yml; Telegram
  ask_percy  Telegram with the comment link and a draft; nothing on Jira
Usage: reply-act.py <ctx dir>   Env: KEY, COMMENT_ID, OWN, JIRA_*, TG_*, TASKS_*, DISPATCH_TOKEN, GITHUB_REPOSITORY
Public repo: prints the action only.
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan  # noqa: E402  (Jira/Telegram helpers, env handling)

ctx, key, cid, own = sys.argv[1], os.environ["KEY"], os.environ["COMMENT_ID"], os.environ.get("OWN") == "1"
try:
    res = json.load(open(os.path.join(ctx, "claude.json"))).get("result", "")
    d = json.loads(re.search(r"\{.*\}", res, re.S).group(0))
except (OSError, ValueError, AttributeError):
    d = {"action": "ask_percy", "reply": "", "why": "Runner không đọc được quyết định của Claude"}
act = d.get("action", "ask_percy")
if act == "fix" and scan.work_hours():  # daytime: fixes are done on Percy's Mac, not on the runner
    act, d["why"] = "ask_percy", "Giờ làm: sửa trên máy. " + d.get("why", "")
if act == "fix" and not own:
    act, d["why"] = "ask_percy", "Yêu cầu sửa trên ticket không phải của anh: " + d.get("why", "")
if act in ("reply", "fix") and not d.get("reply", "").strip():
    act = "ask_percy"

f = scan.get(f"{scan.JIRA}/rest/api/3/issue/{key}?fields=summary,status,issuetype,customfield_10001")["fields"]
c = scan.get(f"{scan.JIRA}/rest/api/3/issue/{key}/comment/{cid}")
who, text = c["author"], re.sub(r"\s+", " ", scan.adf_text(c["body"])).strip()
clink = f'<a href="{scan.JIRA}/browse/{key}?focusedCommentId={cid}">{key}</a>'
head = f'{clink} · <b>{scan.esc(who["displayName"])}</b>: <i>{scan.esc(text[:200])}</i>'


DRY = os.environ.get("DRY") == "1"


def jira_reply(msg):
    if DRY:
        return "thử, chưa đăng"
    body = {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [
        {"type": "mention", "attrs": {"id": who["accountId"], "text": "@" + who["displayName"]}},
        {"type": "text", "text": " " + msg.strip()}]}]}
    r = scan.post(f"{scan.JIRA}/rest/api/3/issue/{key}/comment", {**scan.AUTH}, {"body": body})
    return f'<a href="{scan.JIRA}/browse/{key}?focusedCommentId={r.get("id", cid)}">xem</a>'


def patch(url, headers, payload):
    req = scan.urllib.request.Request(url, data=json.dumps(payload).encode(), method="PATCH",
                                      headers={**headers, "Content-Type": "application/json"})
    scan.urllib.request.urlopen(req, timeout=30).read()


def start_fix(note):
    """Append the request to the ticket's runner task (or open one) and start ticket.yml."""
    if DRY:
        return 0
    gh = {"Authorization": f"Bearer {scan.ENV['TASKS_PAT']}", "Accept": "application/vnd.github+json"}
    repo = scan.ENV["TASKS_REPO"]
    issues = scan.get(f"https://api.github.com/repos/{repo}/issues?state=all&per_page=100", gh)
    t = next((i for i in issues if "pull_request" not in i and key in i["title"]), None)
    extra = f"\n\n## Comment cần sửa ({who['displayName']})\n{text}\n\nYêu cầu: {note}\n"
    if t:
        n = t["number"]
        labels = [x["name"] for x in t["labels"] if x["name"] not in ("done", "blocked") and not x["name"].endswith(("-done", "-todo"))]
        patch(f"https://api.github.com/repos/{repo}/issues/{n}", gh,
              {"body": (t.get("body") or "") + extra, "state": "open", "labels": labels + ["todo"]})
        scan.post(f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/actions/workflows/ticket.yml/dispatches",
                  {"Authorization": f"Bearer {os.environ['DISPATCH_TOKEN']}", "Accept": "application/vnd.github+json"},
                  {"ref": "main", "inputs": {"issue": str(n)}})
        return n
    started = scan.auto_start([(f, key)])
    if started:
        n = started[0][0]
        b = scan.get(f"https://api.github.com/repos/{repo}/issues/{n}", gh)["body"]
        patch(f"https://api.github.com/repos/{repo}/issues/{n}", gh, {"body": b + extra})
        return n
    return None


why = scan.esc(d.get("why", ""))
if act == "none":
    msg = f"🤖 Không cần rep · {head}\n<i>{why}</i>"
elif act == "reply":
    msg = f"🤖 <b>Đã rep</b> · {head}\n↪️ {scan.esc(d['reply'])} ({jira_reply(d['reply'])})"
elif act == "fix":
    n = start_fix(d.get("fix_note") or text)
    rep = jira_reply(d["reply"]) if n is not None else ""
    msg = (f"🛠 <b>Tự sửa</b> · {head}\n" + (f"Runner task #{n or '?'} · đã rep: {scan.esc(d['reply'])} ({rep})"
           if n is not None else "Không mở được task runner, anh xem giúp") + f"\n<i>{why}</i>")
else:
    act = "ask_percy"
    msg = f"❓ <b>Cần anh xử lý</b> · {head}\n<i>{why}</i>" + (f"\nNháp: {scan.esc(d.get('reply', ''))}" if d.get("reply") else "")
    # Author has an alias → the draft goes out as a ✅ Gửi card (Jira reply with a real mention) instead of plain text.
    alias = next((a for a, i in json.loads(os.environ.get("JIRA_MEMBERS") or "{}").items() if i == who["accountId"]), None)
    if d.get("reply", "").strip() and alias and not DRY:
        try:
            from propose import propose
            propose(key, (f.get("customfield_10001") or {}).get("name") or "-", f"@{alias} {d['reply'].strip()}", "",
                    f"{d.get('why', '')} · Comment của {who['displayName']}: \"{text[:200]}\" "
                    f"{scan.JIRA}/browse/{key}?focusedCommentId={cid}")
            msg = None
        except Exception as e:  # noqa: BLE001  fall back to the plain note
            print(f"propose failed: {type(e).__name__}")
if msg:
    scan.send(f, key, ("🧪 (chạy thử) " if DRY else "") + msg, False)
print(f"reply: {act}")
