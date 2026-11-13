"""Send screenshots (and the Figma frames) as Telegram albums to the ticket's squad topic.

Usage: tg-photos.py <context.md> <caption> <png>...    Env: TG_TICKET_BOT_TOKEN TG_NOTIFY_CHAT_ID TG_SQUAD_TOPICS
Albums hold at most 10 photos; images go in the order given.
"""
import json, os, re, sys, urllib.request, uuid

ctx, caption, files = sys.argv[1], sys.argv[2], [f for f in sys.argv[3:] if os.path.getsize(f) > 0]
team = re.search(r"Team: ([^\n·]+)", open(ctx).read()) if os.path.exists(ctx) else None
topic = json.loads(os.environ.get("TG_SQUAD_TOPICS") or "{}").get(team.group(1).strip() if team else "")
api = f"https://api.telegram.org/bot{os.environ['TG_TICKET_BOT_TOKEN']}/sendMediaGroup"

for i in range(0, len(files), 10):
    batch = files[i:i + 10]
    media = [{"type": "photo", "media": f"attach://p{j}", **({"caption": caption[:1000]} if i == 0 and j == 0 else {})}
             for j in range(len(batch))]
    fields = {"chat_id": os.environ["TG_NOTIFY_CHAT_ID"], "media": json.dumps(media)}
    if topic:
        fields["message_thread_id"] = str(topic)
    boundary = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for j, path in enumerate(batch):
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"p{j}\"; filename=\"{os.path.basename(path)}\"\r\n"
                 "Content-Type: image/png\r\n\r\n").encode() + open(path, "rb").read() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    urllib.request.urlopen(urllib.request.Request(api, data=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}"}), timeout=120)
print(f"sent {len(files)} photos")
