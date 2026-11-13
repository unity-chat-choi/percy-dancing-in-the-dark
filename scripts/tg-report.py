"""Send a runner report (Markdown-ish text) to the ticket's squad topic in Telegram.

Usage: tg-report.py <report.md> <context.md> <title line>
Env: TG_TICKET_BOT_TOKEN TG_NOTIFY_CHAT_ID TG_SQUAD_TOPICS. The squad comes from the ticket's "Team:" line.
"""
import json, os, re, sys, urllib.request

report = open(sys.argv[1]).read().strip() if os.path.exists(sys.argv[1]) else "(Claude không viết report)"
team = re.search(r"Team: ([^\n·]+)", open(sys.argv[2]).read()) if os.path.exists(sys.argv[2]) else None
topic = json.loads(os.environ.get("TG_SQUAD_TOPICS") or "{}").get(team.group(1).strip() if team else "")
esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
body = re.sub(r"^#+\s*(.+)$", r"<b>\1</b>", esc(report), flags=re.M)
body = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", body)
text = f"🤖 {esc(sys.argv[3])}\n\n{body}"
parts, cur = [], ""
for line in text.split("\n"):  # 4096-char cap; never cut inside a tag
    if cur and len(cur) + len(line) > 3800:
        parts.append(cur)
        cur = ""
    cur = f"{cur}\n{line}" if cur else line
parts.append(cur)
for p in parts:
    msg = {"chat_id": os.environ["TG_NOTIFY_CHAT_ID"], "text": p, "parse_mode": "HTML", "disable_web_page_preview": True}
    if topic:
        msg["message_thread_id"] = topic
    urllib.request.urlopen(urllib.request.Request(
        f"https://api.telegram.org/bot{os.environ['TG_TICKET_BOT_TOKEN']}/sendMessage",
        data=json.dumps(msg).encode(), headers={"Content-Type": "application/json"}), timeout=30)
print("report sent")
