"""Ask Percy to approve a Jira comment and/or Google Chat message. Sends a draft with ✅ Gửi / ❌ Bỏ buttons
to the squad's Telegram topic; the poll job (daily.py) posts it when he taps ✅.

Usage: propose.py <ISSUE-KEY> "<squad = Chat space name>" [--jira FILE] [--chat FILE] [--why FILE]
       propose.py --asks <asks.json> <ISSUE-KEY>   (runner: [{"jira","chat","why"}], squad = the ticket's Jira team)
  FILE = plain text, "@Alias" becomes a real mention on Jira and Chat. The Chat message gets the Jira link
  (with the new comment id) prepended automatically. --why = why this needs Percy's OK (shown, never sent).
Env: TG_TICKET_BOT_TOKEN TG_NOTIFY_CHAT_ID TG_SQUAD_TOPICS (+ JIRA_URL JIRA_EMAIL JIRA_API_TOKEN for --asks)
"""
import base64, json, os, sys, urllib.request


def propose(key, squad, jira="", chat="", why=""):
    esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Bodies are boxed (<pre>); Telegram hands the text back without tags. The poll job parses this exact layout
    # back from the message (first line, then "━━ " sections), keep markers in sync with daily.py.
    text = f"📝 <b>DUYỆT GỬI</b> · {key} · {esc(squad or '-')}"
    if why:
        text += f"\n💡 <i>Vì sao cần anh duyệt: {esc(why.replace('━━', '—').strip())}</i>"
    if jira:
        text += f"\n━━ Jira comment\n<pre>{esc(jira.strip())}</pre>"
    if chat:
        text += f"\n━━ Google Chat\n<pre>{esc(chat.strip())}</pre>"
    topics = json.loads(os.environ.get("TG_SQUAD_TOPICS") or "{}")
    msg = {"chat_id": os.environ["TG_NOTIFY_CHAT_ID"], "text": text[:4000], "parse_mode": "HTML",
           "disable_web_page_preview": True,
           "reply_markup": {"inline_keyboard": [[{"text": "✅ Gửi", "callback_data": "send"},
                                                 {"text": "❌ Bỏ", "callback_data": "skip"}]]}}
    if topics.get(squad):
        msg["message_thread_id"] = topics[squad]
    req = urllib.request.Request(f"https://api.telegram.org/bot{os.environ['TG_TICKET_BOT_TOKEN']}/sendMessage",
                                 data=json.dumps(msg).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)["result"]["message_id"]


def ask_all(key, asks):
    """Runner drafts (backend/PO questions): one card each, routed to the ticket's squad (or its parent story's)."""
    asks = [a for a in asks or [] if a.get("jira") or a.get("chat")][:3]
    if not asks:
        return 0
    auth = {"Authorization": "Basic " + base64.b64encode(f"{os.environ['JIRA_EMAIL']}:{os.environ['JIRA_API_TOKEN']}".encode()).decode()}
    get = lambda k: json.load(urllib.request.urlopen(urllib.request.Request(
        f"{os.environ['JIRA_URL'].rstrip('/')}/rest/api/3/issue/{k}?fields=customfield_10001,parent", headers=auth), timeout=20))["fields"]
    f = get(key)
    team = (f.get("customfield_10001") or {}).get("name") or (
        f.get("parent") and (get(f["parent"]["key"]).get("customfield_10001") or {}).get("name")) or "-"
    for a in asks:
        propose(key, team, a.get("jira", ""), a.get("chat", ""), a.get("why", ""))
    return len(asks)


def main(argv):
    if argv[1:2] == ["--asks"]:
        try:
            asks = json.load(open(argv[2]))
        except (OSError, ValueError):
            asks = []
        print("asks:", ask_all(argv[3], asks))
        return
    if len(argv) < 3 or "--jira" not in argv and "--chat" not in argv:
        sys.exit(__doc__)
    arg = lambda f: open(argv[argv.index(f) + 1]).read().strip() if f in argv else ""
    print("proposed, message", propose(argv[1], argv[2], arg("--jira"), arg("--chat"), arg("--why")))


if __name__ == "__main__":
    main(sys.argv)
