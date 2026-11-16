"""Ask Percy to approve a Jira comment and/or Google Chat message. Sends a draft with ✅ Gửi / ❌ Bỏ buttons
to the squad's Telegram topic; the poll job (daily.py) posts it when he taps ✅.

Usage: propose.py <ISSUE-KEY> "<squad = Chat space name>" [--jira FILE] [--chat FILE] [--why FILE]
  FILE = plain text, "@Alias" becomes a real mention on Jira and Chat. The Chat message gets the Jira link
  (with the new comment id) prepended automatically. --why = why this needs Percy's OK (shown, never sent).
Env: TG_TICKET_BOT_TOKEN TG_NOTIFY_CHAT_ID TG_SQUAD_TOPICS
"""
import json, os, sys, urllib.request


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


def main(argv):
    if len(argv) < 3 or "--jira" not in argv and "--chat" not in argv:
        sys.exit(__doc__)
    arg = lambda f: open(argv[argv.index(f) + 1]).read().strip() if f in argv else ""
    print("proposed, message", propose(argv[1], argv[2], arg("--jira"), arg("--chat"), arg("--why")))


if __name__ == "__main__":
    main(sys.argv)
