"""Ask Percy to approve a Jira comment and/or Google Chat message. Sends a draft with ✅ Gửi / ❌ Bỏ buttons
to the squad's Telegram topic; the poll job (daily.py) posts it when he taps ✅.

Usage: propose.py <ISSUE-KEY> "<squad = Chat space name>" [--jira FILE] [--chat FILE]
  FILE = plain text, "@Alias" becomes a real mention on Jira and Chat. The Chat message gets the Jira link
  (with the new comment id) prepended automatically.
Env: TG_TICKET_BOT_TOKEN TG_NOTIFY_CHAT_ID TG_SQUAD_TOPICS
"""
import json, os, sys, urllib.request


def main(argv):
    if len(argv) < 3 or "--jira" not in argv and "--chat" not in argv:
        sys.exit(__doc__)
    key, squad = argv[1], argv[2]
    jira = open(argv[argv.index("--jira") + 1]).read().strip() if "--jira" in argv else ""
    chat = open(argv[argv.index("--chat") + 1]).read().strip() if "--chat" in argv else ""
    esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # The poll job parses this exact layout back from the message, keep markers in sync with daily.py.
    text = f"📝 <b>DUYỆT GỬI</b> · {key} · {esc(squad)}"
    if jira:
        text += f"\n━━ Jira comment\n{esc(jira)}"
    if chat:
        text += f"\n━━ Google Chat\n{esc(chat)}"
    topics = json.loads(os.environ.get("TG_SQUAD_TOPICS") or "{}")
    msg = {"chat_id": os.environ["TG_NOTIFY_CHAT_ID"], "text": text, "parse_mode": "HTML",
           "disable_web_page_preview": True,
           "reply_markup": {"inline_keyboard": [[{"text": "✅ Gửi", "callback_data": "send"},
                                                 {"text": "❌ Bỏ", "callback_data": "skip"}]]}}
    if topics.get(squad):
        msg["message_thread_id"] = topics[squad]
    req = urllib.request.Request(f"https://api.telegram.org/bot{os.environ['TG_TICKET_BOT_TOKEN']}/sendMessage",
                                 data=json.dumps(msg).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        print("proposed, message", json.load(r)["result"]["message_id"])


if __name__ == "__main__":
    main(sys.argv)
