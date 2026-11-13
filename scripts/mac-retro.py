"""Mac-side half of the sprint retro (needs local Claude logs + memory): AI cost and lessons learned.
Posts to the "📊 Sprint Retro" topic. Run on every Mac Percy works on: python3 scripts/mac-retro.py
Reads ~/.config/cutcut/uniscore-runner-secrets.env and ~/.claude/jira-credentials.json. LOCAL=1 prints only.
Cost = ccusage's API-price equivalent of the tokens used; the subscription itself is a flat fee.
"""
import base64, glob, json, os, re, socket, subprocess, urllib.parse, urllib.request
import datetime as dt

HOME = os.path.expanduser("~")
VN = dt.timezone(dt.timedelta(hours=7))
env = dict(l.split("=", 1) for l in open(f"{HOME}/.config/cutcut/uniscore-runner-secrets.env").read().splitlines()
           if "=" in l and not l.startswith("#"))
env = {k: v.strip().strip("'\"") for k, v in env.items()}


def http(url, headers=None, data=None):
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers or {}), timeout=30) as r:
        return json.loads(r.read() or b"{}")


# Sprint window from Jira (active sprint of Percy's tickets); fall back to the last 14 days.
c = json.load(open(f"{HOME}/.claude/jira-credentials.json"))
auth = {"Authorization": "Basic " + base64.b64encode(f"{c['email']}:{c['token']}".encode()).decode(), "Accept": "application/json"}
q = urllib.parse.urlencode({"jql": "assignee = currentUser() AND sprint in openSprints()", "fields": "customfield_10020", "maxResults": 5})
sprints = [s for i in http(f"{env['JIRA_URL'].rstrip('/')}/rest/api/3/search/jql?{q}", auth).get("issues", [])
           for s in i["fields"].get("customfield_10020") or [] if s.get("state") == "active"]
start = (dt.datetime.fromisoformat(sprints[0]["startDate"].replace("Z", "+00:00")) if sprints and sprints[0].get("startDate")
         else dt.datetime.now(VN) - dt.timedelta(days=14))
name = re.sub(r"^\d{4}\s+", "", sprints[0]["name"]) if sprints else "14 ngày qua"

# AI cost per session (ccusage), grouped by Claude project folder.
raw = subprocess.run(["npx", "-y", "ccusage@latest", "session", "--since", start.strftime("%Y%m%d"), "--json"],
                     capture_output=True, text=True, timeout=300).stdout
sessions = json.loads(raw or "{}").get("session", [])
proj_of = {os.path.basename(p)[:-6]: os.path.basename(os.path.dirname(p))
           for p in glob.glob(f"{HOME}/.claude/projects/*/*.jsonl")}
uni = other = 0.0
models = {}
for s in sessions:
    cost = s.get("totalCost", 0)
    if "uniscore" in proj_of.get(s.get("period", ""), ""):
        uni += cost
        for m in s.get("modelBreakdowns", []):
            key = re.sub(r"^claude-|-\d+$", "", m.get("modelName", "?"))
            models[key] = models.get(key, 0) + m.get("cost", 0)
    else:
        other += cost

# Lessons = feedback memories written or changed during the sprint (each one is a correction Percy made).
lessons = []
for p in glob.glob(f"{HOME}/.claude/projects/*uniscore*/memory/feedback*.md"):
    text = open(p).read()
    mod = re.search(r"^\s*modified:\s*(\S+)", text, re.M)  # memory frontmatter; file mtime lies after copies
    when = (dt.datetime.fromisoformat(mod.group(1).replace("Z", "+00:00")) if mod
            else dt.datetime.fromtimestamp(os.path.getmtime(p), dt.timezone.utc))
    if when >= start:
        m = re.search(r"^description:\s*\"?(.+?)\"?\s*$", text, re.M)
        lessons.append(m.group(1) if m else os.path.basename(p))

esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
out = [f"💸 <b>AI · {esc(name)}</b> · máy {esc(socket.gethostname().split('.')[0])}",
       f"Uniscore: <b>${uni:,.2f}</b> (giá API tương đương)"]
if models:
    out.append("   " + " · ".join(f"{k} ${v:,.0f}" for k, v in sorted(models.items(), key=lambda x: -x[1])))
out.append(f"Project khác: ${other:,.2f}")
out += ["", f"<b>━━ 📚 Bài học trong sprint ({len(lessons)})</b>"]
out += [f"• {esc(l)}" for l in lessons] or ["<i>chưa có bài học mới</i>"]
html = "\n".join(out)

if os.environ.get("LOCAL") == "1":
    print(html)
else:
    msg = {"chat_id": env["TG_NOTIFY_CHAT_ID"], "text": html, "parse_mode": "HTML", "message_thread_id": int(env["TG_RETRO_TOPIC"])}
    http(f"https://api.telegram.org/bot{env['TG_TICKET_BOT_TOKEN']}/sendMessage", {"Content-Type": "application/json"},
         json.dumps(msg).encode())
    print("sent")
