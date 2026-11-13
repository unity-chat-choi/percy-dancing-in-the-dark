"""Send one file (e.g. the HTML report) to the ticket's squad topic. Usage: tg-doc.py <file> <context.md> <caption>"""
import json, os, re, sys, urllib.request, uuid

path, ctx, caption = sys.argv[1:4]
team = re.search(r"Team: ([^\n·]+)", open(ctx).read()) if os.path.exists(ctx) else None
topic = json.loads(os.environ.get("TG_SQUAD_TOPICS") or "{}").get(team.group(1).strip() if team else "")
fields = {"chat_id": os.environ["TG_NOTIFY_CHAT_ID"], "caption": caption[:1000]}
if topic:
    fields["message_thread_id"] = str(topic)
b = uuid.uuid4().hex
body = b"".join(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode() for k, v in fields.items())
body += (f"--{b}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{os.path.basename(path)}\"\r\n"
         "Content-Type: text/html\r\n\r\n").encode() + open(path, "rb").read() + f"\r\n--{b}--\r\n".encode()
urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{os.environ['TG_TICKET_BOT_TOKEN']}/sendDocument",
                                              data=body, headers={"Content-Type": f"multipart/form-data; boundary={b}"}), timeout=120)
print("doc sent")
