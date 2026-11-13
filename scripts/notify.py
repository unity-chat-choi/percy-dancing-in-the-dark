"""Send one text message to a Google Chat space. Never prints webhook URLs.

SPACE "telegram" goes to the Telegram bot instead (TG_BOT_TOKEN_1, TG_NOTIFY_CHAT_ID, TG_NOTIFY_THREAD_ID).
Env: CHAT_WEBHOOKS = {"<space name>": "<webhook url>"}, CHAT_MEMBERS = {"<alias>": "<chat user id>"},
     SPACE, TEXT, DRYRUN=1 to print the body only. "@alias" becomes a real mention when the alias is known.
"""
import json, os, re, sys, urllib.request

hooks = json.loads(os.environ.get("CHAT_WEBHOOKS") or "{}")
ids = {k.lower(): v for k, v in json.loads(os.environ.get("CHAT_MEMBERS") or "{}").items()}
space, text = os.environ["SPACE"].strip(), os.environ["TEXT"].replace("\\n", "\n")

text = re.sub(r"(?<![\w<])@([A-Za-z][\w.-]*)",
              lambda m: f"<users/{ids[m.group(1).lower()]}>" if m.group(1).lower() in ids else m.group(0), text)
body = json.dumps({"text": text}).encode()

if os.environ.get("DRYRUN") == "1":
    # Public repo: logs are public, so hide member ids.
    print(re.sub(r"users/\d+", "users/***", body.decode())); sys.exit(0)
if space.lower() == "telegram":
    data = {"chat_id": os.environ["TG_NOTIFY_CHAT_ID"], "text": text}
    if os.environ.get("TG_NOTIFY_THREAD_ID", "").strip() not in ("", "0", "1"):
        data["message_thread_id"] = os.environ["TG_NOTIFY_THREAD_ID"]
    req = urllib.request.Request(f"https://api.telegram.org/bot{os.environ['TG_BOT_TOKEN_1']}/sendMessage",
                                 data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        print(f"Sent to telegram (HTTP {r.status})")
    sys.exit(0)
url = hooks.get(space)
if not url:
    sys.exit(f"No webhook for space: {space}. Known: {', '.join(hooks)}")
req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json; charset=UTF-8"})
with urllib.request.urlopen(req, timeout=20) as r:
    print(f"Sent to {space} (HTTP {r.status})")
