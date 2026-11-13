"""Sprint retro for Percy -> Telegram topic "📊 Sprint Retro". Content never goes to the log (public repo).

Done work (points, per squad), what to improve (rework, bugs on own tickets, cycle time) and team
contributions (MR reviews, shared agent docs/skills). AI cost is posted separately from each Mac (ai-cost.sh).
Env: GITLAB_TOKEN GITLAB_PROJECT JIRA_URL JIRA_EMAIL JIRA_API_TOKEN TG_TICKET_BOT_TOKEN TG_NOTIFY_CHAT_ID TG_RETRO_TOPIC
     LOCAL=1 prints instead of sending.
"""
import base64, collections, datetime as dt, json, os, re, statistics, urllib.parse, urllib.request

env = os.environ.get
JIRA = env("JIRA_URL", "").rstrip("/")
VN = dt.timezone(dt.timedelta(hours=7))
PASSED = {"ready to test", "in testing", "ready for release", "released", "resolved", "done", "closed"}
REWORK = {"fixing", "review fail"}
POINT = re.compile(r"Point:\s*([\d.]+)", re.I)


def http(url, headers=None, data=None):
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers or {}), timeout=30) as r:
        body = r.read()
    return json.loads(body) if body else {}


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def adf_text(n):
    return n.get("text", "") + " ".join(adf_text(c) for c in n.get("content", [])) if isinstance(n, dict) else ""


def short(summary):
    return re.sub(r"^(\s*\[[^\]]*\]\s*)+", "", summary).strip(" -–") or summary


def link(k):
    return f'<a href="{JIRA}/browse/{k}">{k}</a>'


def when(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f%z")


jauth = {"Authorization": "Basic " + base64.b64encode(f"{env('JIRA_EMAIL')}:{env('JIRA_API_TOKEN')}".encode()).decode(),
         "Accept": "application/json"}
q = urllib.parse.urlencode({"jql": "(assignee = currentUser() OR cf[10075] = currentUser()) AND sprint in openSprints()",
                            "fields": "summary,status,issuetype,description,customfield_10020,customfield_10001",
                            "expand": "changelog", "maxResults": 100})
issues = http(f"{JIRA}/rest/api/3/search/jql?{q}", jauth).get("issues", [])
sprint = next((s for i in issues for s in i["fields"].get("customfield_10020") or [] if s.get("state") == "active"), {})
start = when(sprint["startDate"].replace("Z", "+0000")) if sprint.get("startDate") else None
sprint_name = re.sub(r"^\d{4}\s+", "", sprint.get("name", "Sprint"))

per_squad = collections.defaultdict(lambda: {"done": [], "open": [], "pts_done": 0.0, "pts_all": 0.0})
rework, cycle = [], []
for i in issues:
    f, k = i["fields"], i["key"]
    team = f.get("customfield_10001")
    sq = (team.get("name") if isinstance(team, dict) else None) or "Chưa gắn squad"
    m = POINT.search(adf_text(f.get("description")))
    p = float(m.group(1)) if m else 0.0
    st = f["status"]["name"].lower()
    bucket = per_squad[sq]
    bucket["pts_all"] += p
    if st in PASSED:
        bucket["done"].append(k)
        bucket["pts_done"] += p
    else:
        bucket["open"].append(k)
    # Changelog: times it bounced back to FIXING / Review fail, and In Progress -> REVIEW CODE time.
    moves = [(when(h["created"]), it["toString"] or "") for h in i.get("changelog", {}).get("histories", [])
             for it in h["items"] if it["field"] == "status"]
    moves.sort()
    back = sum(1 for t, to in moves if to.lower() in REWORK and (not start or t >= start))
    if back:
        rework.append((k, back, f["summary"]))
    t_ip = next((t for t, to in moves if to.lower() == "in progress"), None)
    t_rv = next((t for t, to in moves if to.lower() == "review code" and t_ip and t > t_ip), None)
    if t_ip and t_rv:
        cycle.append((t_rv - t_ip).total_seconds() / 86400)

since = (start or dt.datetime.now(VN) - dt.timedelta(days=14)).strftime("%Y-%m-%d")
bq = urllib.parse.urlencode({"jql": f'type = Bug AND (assignee = currentUser() OR cf[10075] = currentUser()) AND created >= "{since}"',
                             "fields": "summary,status", "maxResults": 50})
bugs = http(f"{JIRA}/rest/api/3/search/jql?{bq}", jauth).get("issues", [])

# GitLab: MRs, reviews on others' MRs, commits to shared agent docs/skills.
gh = {"PRIVATE-TOKEN": env("GITLAB_TOKEN")}
G = "https://gitlab.com/api/v4"
proj = urllib.parse.quote(env("GITLAB_PROJECT"), safe="")
me = http(f"{G}/user", gh)["id"]
merged = http(f"{G}/projects/{proj}/merge_requests?" + urllib.parse.urlencode(
    {"author_id": me, "state": "merged", "updated_after": since + "T00:00:00Z", "per_page": 100}), gh)
events = http(f"{G}/users/{me}/events?" + urllib.parse.urlencode({"after": since, "per_page": 100}), gh)
reviewed = {e["note"]["noteable_iid"] for e in events if e.get("action_name") == "commented on"
            and (e.get("note") or {}).get("noteable_type") == "MergeRequest"}
own_iids = {m["iid"] for m in merged}
reviews = len(reviewed - own_iids)
shared = collections.Counter()
for path in ("docs/ai", ".claude/skills", "AGENTS.md"):
    cs = http(f"{G}/projects/{proj}/repository/commits?" + urllib.parse.urlencode(
        {"path": path, "since": since + "T00:00:00Z", "all": "true", "per_page": 100}), gh)
    shared[path] = sum(1 for c in cs if c["author_name"].lower() == "percy")

# --- Report
total_done = sum(b["pts_done"] for b in per_squad.values())
total_all = sum(b["pts_all"] for b in per_squad.values())
out = [f"📊 <b>RETRO · {esc(sprint_name)}</b>", f"<i>cập nhật {dt.datetime.now(VN):%H:%M %d/%m}</i>", "",
       f"<b>━━ ✅ Đã làm</b>  {total_done:g}/{total_all:g} point qua test"]
for sq, b in sorted(per_squad.items()):
    out.append(f"• <b>{esc(sq)}</b>: {len(b['done'])}/{len(b['done']) + len(b['open'])} ticket · {b['pts_done']:g}/{b['pts_all']:g}p")
out.append(f"• MR đã merge: {len(merged)}")

out += ["", "<b>━━ 📚 Cần cải thiện</b>"]
if rework:
    out.append(f"🔁 Bị trả về sửa ({len(rework)} ticket):")
    out += [f"   • {link(k)} ×{n} — {esc(short(s)[:60])}" for k, n, s in rework]
else:
    out.append("🔁 Không ticket nào bị trả về sửa 👍")
out.append(f"🐞 Bug trên ticket của mình từ {since[8:10]}/{since[5:7]}: {len(bugs)}"
           + (" — " + ", ".join(link(b["key"]) for b in bugs[:8]) if bugs else ""))
if cycle:
    out.append(f"⏱ Từ In Progress tới Review: trung vị {statistics.median(cycle):.1f} ngày ({len(cycle)} ticket)")

out += ["", "<b>━━ 🤝 Đóng góp cho team</b>",
        f"• Review MR của người khác: {reviews}",
        f"• Commit tài liệu agent chung (docs/ai): {shared['docs/ai']}",
        f"• Commit skill chung (.claude/skills, AGENTS.md): {shared['.claude/skills'] + shared['AGENTS.md']}"]

html = "\n".join(out)
if env("LOCAL") == "1":
    print(re.sub(r'<a href="[^"]+">', "<a>", html))
else:
    msg = {"chat_id": env("TG_NOTIFY_CHAT_ID"), "text": html, "parse_mode": "HTML", "disable_web_page_preview": True}
    if env("TG_RETRO_TOPIC"):
        msg["message_thread_id"] = int(env("TG_RETRO_TOPIC"))
    http(f"https://api.telegram.org/bot{env('TG_TICKET_BOT_TOKEN')}/sendMessage", {"Content-Type": "application/json"},
         json.dumps(msg).encode())
    print("retro sent")
