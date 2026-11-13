"""09:00 report + the developer's row in the team daily sheet, from GitLab commits and Jira.

Sheet: B (hôm qua) = tickets in Percy's commits on the previous working day; C (hôm nay) = his In Progress /
FIXING tickets; D (khó khăn) = those whose [API] sibling is not ready. Only empty cells are written.
Telegram (Task topic): sprint points, tickets without points, work grouped by status, APIs to chase,
new comments and new bugs in the last 24h. Content never goes to the log (public repo).
Env: GITLAB_TOKEN GITLAB_PROJECT JIRA_URL JIRA_EMAIL JIRA_API_TOKEN GOOGLE_OAUTH TG_TICKET_BOT_TOKEN
     TG_NOTIFY_CHAT_ID TG_SQUAD_TOPICS DATE (dd/MM/yyyy) OFF_DAYS ("dd/MM,..") DRYRUN=1 RETRY=1 LOCAL=1
     CHAT_WEBHOOKS CHAT_MEMBERS JIRA_MEMBERS (for ✅ Gửi on drafts from propose.py)
     REACT_ONLY=1: only handle Telegram updates — ❤ reactions and ✅/❌ draft buttons (Percy hearts an item = handled, never shown again).
State (state/daily-state.json, committed): hashed item ids only, so the public repo shows no ticket data.
"""
import base64, datetime as dt, hashlib, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

SHEET = os.environ.get("DAILY_SHEET_ID", "")
ROW_NAME, AUTHOR = os.environ.get("DAILY_ROW_NAME", ""), "percy"
KEY = re.compile(r"\b(?:US|UTD|UOB)-\d+\b")
POINT = re.compile(r"Point:\s*([\d.]+)", re.I)
VN = dt.timezone(dt.timedelta(hours=7))
env = os.environ.get
JIRA = env("JIRA_URL", "").rstrip("/")

# Status groups, in report order. Unknown statuses fall into "Khác".
GROUPS = [
    ("🟠 Đang sửa", {"fixing", "review fail"}),
    ("🟡 Đang làm", {"in progress"}),
    ("⚪ Chưa làm", {"to do", "open"}),
    ("🔵 Chờ review", {"review code"}),
    ("🟣 Đang test", {"ready to test", "in testing"}),
    ("✅ Xong", {"ready for release", "released", "resolved", "done", "closed"}),
]
DONE = GROUPS[-1][1]
API_READY = DONE | {"ready to test", "in testing"}


def http(url, headers=None, data=None, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    return json.loads(body) if body else {}


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tg(html, thread=None):
    """Send HTML to the group (topic `thread`); returns the last message id."""
    if env("LOCAL") == "1":
        print(re.sub(r'<a href="[^"]+">', "<a>", html))
        return None
    bot = env("TG_TICKET_BOT_TOKEN") or env("TG_BOT_TOKEN_1")
    if not bot or not env("TG_NOTIFY_CHAT_ID"):
        return None
    # Telegram caps a message at 4096 chars; split on line breaks so no HTML tag is cut in half.
    parts, cur = [], ""
    for line in html.split("\n"):
        if cur and len(cur) + len(line) + 1 > 3800:
            parts.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line
    parts.append(cur)
    mid = None
    for text in parts:
        msg = {"chat_id": env("TG_NOTIFY_CHAT_ID"), "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        if thread:
            msg["message_thread_id"] = int(thread)
        for attempt in range(5):  # group limit ~20 msgs/min: honour 429 retry_after
            try:
                mid = http(f"https://api.telegram.org/bot{bot}/sendMessage", {"Content-Type": "application/json"},
                           json.dumps(msg).encode())["result"]["message_id"]
                break
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == 4:
                    raise
                wait = json.loads(e.read() or b"{}").get("parameters", {}).get("retry_after", 5)
                time.sleep(wait + 1)
        time.sleep(1.2)
    return mid


# --- ❤ = handled. Telegram keeps updates for 24h, so a 30-min job records reactions (REACT_ONLY=1).
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "state", "daily-state.json")
HEARTS = {"❤", "❤️", "❤‍🔥", "💖", "💗", "💓", "😍", "🥰"}
try:
    state = json.load(open(STATE_FILE))
except (OSError, ValueError):
    state = {}
state.setdefault("offset", 0)
state.setdefault("resolved", [])
state.setdefault("sent", {})


def item_id(raw):
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def save_state():
    if env("LOCAL") == "1" or env("DRYRUN") == "1":
        return
    state["sent"] = dict(list(state["sent"].items())[-600:])
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=0, sort_keys=True)


MENTION = re.compile(r"(?<![\w<])@([A-Za-z][\w.-]*)")


def jira_adf(text, ids):
    """Plain text -> ADF paragraphs; @alias -> real mention when the alias is known."""
    paras = []
    for line in text.split("\n"):
        nodes, pos = [], 0
        for m in MENTION.finditer(line):
            acc = ids.get(m.group(1).lower())
            if not acc:
                continue
            if m.start() > pos:
                nodes.append({"type": "text", "text": line[pos:m.start()]})
            nodes.append({"type": "mention", "attrs": {"id": acc, "text": "@" + m.group(1)}})
            pos = m.end()
        if pos < len(line):
            nodes.append({"type": "text", "text": line[pos:]})
        paras.append({"type": "paragraph", "content": nodes})
    return {"type": "doc", "version": 1, "content": paras}


def send_draft(text):
    """Post a draft made by propose.py: Jira comment first, then Chat with the comment link on top."""
    head = re.match(r"📝 DUYỆT GỬI · ([A-Z]+-\d+) · (.+)", text.split("\n", 1)[0])
    if not head:
        raise ValueError("not a draft")
    key, space = head.group(1), head.group(2).strip()
    parts = dict(re.findall(r"━━ (Jira comment|Google Chat)\n(.*?)(?=\n━━ |\Z)", text, re.S))
    jira_txt, chat_txt = parts.get("Jira comment", "").strip(), parts.get("Google Chat", "").strip()
    auth = {"Authorization": "Basic " + base64.b64encode(f"{env('JIRA_EMAIL')}:{env('JIRA_API_TOKEN')}".encode()).decode(),
            "Accept": "application/json", "Content-Type": "application/json"}
    jira_url = env("JIRA_URL").rstrip("/")
    link = f"{jira_url}/browse/{key}"
    if jira_txt:
        ids = json.loads(env("JIRA_MEMBERS") or "{}")
        c = http(f"{jira_url}/rest/api/3/issue/{key}/comment", auth, json.dumps({"body": jira_adf(jira_txt, ids)}).encode(), "POST")
        link += f"?focusedCommentId={c['id']}"
    if chat_txt:
        hooks = json.loads(env("CHAT_WEBHOOKS") or "{}")
        if space not in hooks:
            raise ValueError(f"no Chat webhook for {space}")
        summary = http(f"{jira_url}/rest/api/3/issue/{key}?fields=summary", auth)["fields"]["summary"]
        members = {k.lower(): v for k, v in json.loads(env("CHAT_MEMBERS") or "{}").items()}
        body = MENTION.sub(lambda m: f"<users/{members[m.group(1).lower()]}>" if m.group(1).lower() in members else m.group(0), chat_txt)
        http(hooks[space], {"Content-Type": "application/json; charset=UTF-8"},
             json.dumps({"text": f"<{link}|{key}> - {summary}\n\n{body}"}).encode())
    return link


def handle_callback(bot, cb):
    msg = cb.get("message") or {}
    if str((msg.get("chat") or {}).get("id")) != str(env("TG_NOTIFY_CHAT_ID")) or cb["from"].get("is_bot"):
        return
    api = f"https://api.telegram.org/bot{bot}"
    text, now = msg.get("text", ""), dt.datetime.now(VN).strftime("%H:%M %d/%m")
    try:
        if cb.get("data") == "send":
            link = send_draft(text)
            note, toast = f"✅ Đã gửi {now}\n{link}", "Đã gửi"
        else:
            note, toast = f"❌ Đã bỏ {now}", "Đã bỏ"
    except Exception as e:  # keep the buttons so Percy can retry
        print("draft failed:", type(e).__name__)
        http(f"{api}/answerCallbackQuery", {"Content-Type": "application/json"},
             json.dumps({"callback_query_id": cb["id"], "text": f"Lỗi: {type(e).__name__}", "show_alert": True}).encode())
        return
    http(f"{api}/editMessageText", {"Content-Type": "application/json"}, json.dumps({
        "chat_id": msg["chat"]["id"], "message_id": msg["message_id"], "text": f"{text}\n\n{note}",
        "disable_web_page_preview": True}).encode())
    try:  # the button press may be older than Telegram's 15-min window; editing the message is what matters
        http(f"{api}/answerCallbackQuery", {"Content-Type": "application/json"},
             json.dumps({"callback_query_id": cb["id"], "text": toast}).encode())
    except urllib.error.HTTPError:
        pass


def collect_reactions():
    bot = env("TG_TICKET_BOT_TOKEN")
    if not bot or env("LOCAL") == "1":
        return 0
    q = urllib.parse.urlencode({"offset": state["offset"], "timeout": 0, "allowed_updates": json.dumps(["message_reaction", "callback_query"])})
    ups = http(f"https://api.telegram.org/bot{bot}/getUpdates?{q}").get("result", [])
    resolved, n = set(state["resolved"]), 0
    for u in ups:
        state["offset"] = u["update_id"] + 1
        if u.get("callback_query"):
            handle_callback(bot, u["callback_query"])
            n += 1
            continue
        r = u.get("message_reaction")
        if not r or str(r["chat"]["id"]) != str(env("TG_NOTIFY_CHAT_ID")) or (r.get("user") or {}).get("is_bot"):
            continue
        h = state["sent"].get(str(r["message_id"]))
        if not h:
            continue
        hearted = any(x.get("emoji") in HEARTS for x in r.get("new_reaction", []))
        (resolved.add if hearted else resolved.discard)(h)
        n += 1
    state["resolved"] = sorted(resolved)
    if ups:  # confirm the offset so Telegram drops what we just read
        http(f"https://api.telegram.org/bot{bot}/getUpdates?" + urllib.parse.urlencode({"offset": state["offset"], "timeout": 0}))
    return n


if env("REACT_ONLY") == "1":
    print(f"reactions={collect_reactions()}")
    save_state()
    sys.exit(0)
collect_reactions()


# --- dates
def tab_name(d):
    return d.strftime("%d/%m")


off = {s.strip() for s in (env("OFF_DAYS") or "").split(",") if s.strip()}
today = dt.datetime.strptime(env("DATE"), "%d/%m/%Y").date() if env("DATE") else dt.datetime.now(VN).date()
prev = today - dt.timedelta(days=1)
while prev.weekday() >= 5 or tab_name(prev) in off:
    prev -= dt.timedelta(days=1)

# --- Jira
jauth = {"Authorization": "Basic " + base64.b64encode(f"{env('JIRA_EMAIL')}:{env('JIRA_API_TOKEN')}".encode()).decode(),
         "Accept": "application/json"}
FIELDS = "summary,status,assignee,issuelinks,issuetype,description,customfield_10020,customfield_10001"


def jql(q, n=100, fields=FIELDS):
    u = f"{JIRA}/rest/api/3/search/jql?" + urllib.parse.urlencode({"jql": q, "fields": fields, "maxResults": n})
    return {i["key"]: i["fields"] for i in http(u, jauth).get("issues", [])}


def adf_text(node):
    if isinstance(node, dict):
        if node.get("type") == "mention":
            return node.get("attrs", {}).get("text", "@")
        return node.get("text", "") + " ".join(adf_text(c) for c in node.get("content", []))
    return ""


def short(summary):
    # "[App][Basketball][League] - Thêm Block X" -> "Thêm Block X"
    return re.sub(r"^(\s*\[[^\]]*\]\s*)+", "", summary).strip(" -–") or summary


def link(key):
    return f'<a href="{JIRA}/browse/{key}">{key}</a>'


def status(f):
    return f["status"]["name"]


def point(f):
    m = POINT.search(adf_text(f.get("description")))
    return float(m.group(1)) if m else None


def fmt_pt(p):
    return f"{p:g}"


def api_sibling(fields):
    """[API] ticket under the same parent story: (key, status, assignee) or None."""
    for l in fields.get("issuelinks", []):
        if l["type"]["name"] == "Parent - Child" and "inwardIssue" in l:
            kids = http(f"{JIRA}/rest/api/3/issue/{l['inwardIssue']['key']}?fields=issuelinks", jauth)
            for k in kids["fields"]["issuelinks"]:
                o = k.get("outwardIssue")
                if o and k["type"]["name"] == "Parent - Child" and o["fields"]["summary"].startswith("[API"):
                    full = http(f"{JIRA}/rest/api/3/issue/{o['key']}?fields=status,assignee", jauth)["fields"]
                    return o["key"], full["status"]["name"], (full.get("assignee") or {}).get("displayName", "?")
    return None


me = http(f"{JIRA}/rest/api/3/myself", jauth)["accountId"]
MINE = "(assignee = currentUser() OR cf[10075] = currentUser())"

# Sprint: Percy's tickets in the open sprint that covers today.
sprint_issues = jql(f"{MINE} AND sprint in openSprints() ORDER BY key")
sprint = None
for f in sprint_issues.values():
    for s in f.get("customfield_10020") or []:
        if s.get("state") == "active":
            sprint = s
sprint_name = re.sub(r"^\d{4}\s+", "", sprint["name"]) if sprint else "Sprint"
days_left = None
if sprint and sprint.get("endDate"):
    end = dt.datetime.fromisoformat(sprint["endDate"].replace("Z", "+00:00")).astimezone(VN).date()
    days_left = sum(1 for i in range((end - today).days + 1) if (today + dt.timedelta(days=i)).weekday() < 5)

doing = {k: f for k, f in sprint_issues.items() if status(f).lower() in {"in progress", "fixing", "review fail"}
         and (f.get("assignee") or {}).get("accountId") == me}
apis = {k: api_sibling(f) for k, f in doing.items() if f["issuetype"]["name"] != "Bug"}
chase = {k: a for k, a in apis.items() if a and a[1].lower() not in API_READY}

# GitLab: Percy's non-merge commits on the previous working day (VN time).
start = dt.datetime.combine(prev, dt.time(), VN)
proj = urllib.parse.quote(env("GITLAB_PROJECT"), safe="")
commits, page = [], 1
while True:
    q = urllib.parse.urlencode({"since": start.isoformat(), "until": (start + dt.timedelta(days=1)).isoformat(),
                                "all": "true", "per_page": 100, "page": page})
    batch = http(f"https://gitlab.com/api/v4/projects/{proj}/repository/commits?{q}", {"PRIVATE-TOKEN": env("GITLAB_TOKEN")})
    commits += batch
    if len(batch) < 100:
        break
    page += 1
done_keys = list(dict.fromkeys(k for c in commits if c["author_name"].lower() == AUTHOR
                               and not c["title"].startswith(("Merge ", "WIP", "wip")) for k in KEY.findall(c["title"])))
done = jql(f"key in ({','.join(done_keys)})") if done_keys else {}

# Last 24h: comments by others on Percy's tickets, and new bugs for him.
since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
comments = []
recent = jql(f"{MINE} AND updated >= -1d ORDER BY updated DESC", 30, "summary,customfield_10001")
for k, f in recent.items():
    for c in http(f"{JIRA}/rest/api/3/issue/{k}/comment?orderBy=-created&maxResults=10", jauth).get("comments", []):
        created = dt.datetime.strptime(c["created"], "%Y-%m-%dT%H:%M:%S.%f%z")  # Jira: 2026-11-13T14:07:24.240+0700
        if created >= since and c["author"]["accountId"] != me:
            text = re.sub(r"\s+", " ", adf_text(c["body"])).strip()
            tagged = me in json.dumps(c["body"])
            comments.append((k, c["author"]["displayName"], text[:90] + ("…" if len(text) > 90 else ""), c["id"], tagged))
bugs = jql(f"type = Bug AND {MINE} AND created >= -1d ORDER BY created DESC", 20)

# --- Sheet cells
if tab_name(today) in off:
    B = C = "Off"
    D = ""
else:
    B = "\n".join(f"- {k} — {short(done[k]['summary'])}" if k in done else f"- {k}" for k in done_keys[:8])
    C = "\n".join(f"- {k} — {short(f['summary'])}" for k, f in doing.items())
    D = "\n".join(f"- {k} — chờ API {a[0]} ({a[1]})" for k, a in chase.items())

g = json.loads(env("GOOGLE_OAUTH"))
token = http("https://oauth2.googleapis.com/token", data=urllib.parse.urlencode(
    {**{k: g[k] for k in ("client_id", "client_secret", "refresh_token")}, "grant_type": "refresh_token"}).encode())["access_token"]
sh = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
base = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET}"
tabs = [s["properties"]["title"] for s in http(base + "?fields=sheets.properties.title", sh)["sheets"]]
tab = next((t for t in tabs if t in (tab_name(today), today.strftime("%d/%m/%Y"))), None)

writes, sheet_note = [], "chưa có tab ngày này"
if tab:
    rows = http(base + "/values/" + urllib.parse.quote(f"'{tab}'!A1:D40", safe=""), sh).get("values", [])
    row = next((i + 1 for i, r in enumerate(rows) if r and r[0].strip() == ROW_NAME), None)
    if not row:
        sheet_note = f"không thấy dòng {ROW_NAME}"
    else:
        cur = (rows[row - 1] + ["", "", "", ""])[1:4]
        writes = [{"range": f"'{tab}'!{col}{row}", "values": [[val]]}
                  for col, val, now in (("B", B, cur[0]), ("C", C, cur[1]), ("D", D, cur[2])) if val and not now.strip()]
        if writes and env("DRYRUN") != "1":
            http(base + "/values:batchUpdate", sh, json.dumps({"valueInputOption": "RAW", "data": writes}).encode(), "POST")
        sheet_note = ("xem trước, chưa ghi " if env("DRYRUN") == "1" else "đã điền ") + f"{len(writes)} ô" if writes else "đã có sẵn"

print(f"tab={'ok' if tab else 'none'} writes={len(writes)} dryrun={env('DRYRUN') == '1'}")

# One Telegram topic per squad: {"<Jira team name>": <topic id>, ...}; anything without a squad goes to General.
TOPICS = json.loads(env("TG_SQUAD_TOPICS") or "{}")

# 10:00 retry: only speak up when it actually filled the sheet.
if env("RETRY") == "1":
    save_state()
    if writes:
        tg(f"📋 <b>Daily {tab}</b>: {sheet_note} (lần 10h)", next(iter(TOPICS.values()), None))
    sys.exit(0)

# One report per day: the Mac trigger and the GitHub cron may both fire.
if env("DRYRUN") != "1" and not env("DATE") and state.get("report_date") == tab_name(today):
    print("report already sent today")
    save_state()
    sys.exit(0)
state["report_date"] = tab_name(today) if env("DRYRUN") != "1" else state.get("report_date")

# --- Report: one message per squad, sent to that squad's topic
LABEL = {"in progress": "🟡 đang làm", "fixing": "🟠 đang sửa", "review fail": "🟠 review fail",
         "to do": "⚪ chưa làm", "open": "⚪ chưa làm", "review code": "🔵 chờ review"}
PASSED = DONE | {"ready to test", "in testing"}
NO_SQUAD = "Chưa gắn squad"


def squad(f):
    t = f.get("customfield_10001")
    return (t.get("name") if isinstance(t, dict) else None) or NO_SQUAD


def clink(k, cid):
    return f'<a href="{JIRA}/browse/{k}?focusedCommentId={cid}">{k}</a>'


pts = {k: point(f) for k, f in sprint_issues.items()}
left = f" · còn {days_left} ngày" if days_left is not None else ""
rank_of = lambda f: next((i for i, (_, names) in enumerate(GROUPS) if status(f).lower() in names), 99)
squads = {squad(f) for f in list(sprint_issues.values()) + list(recent.values()) + list(bugs.values())}

for sq in sorted(squads, key=lambda x: (x == NO_SQUAD, x)):
    mine = {k: f for k, f in sprint_issues.items() if squad(f) == sq}
    todo = {k: f for k, f in mine.items() if status(f).lower() not in PASSED}
    sq_pts = {k: pts[k] for k in mine}
    total = sum(p for p in sq_pts.values() if p)
    passed = sum(p for k, p in sq_pts.items() if p and status(mine[k]).lower() in PASSED)
    review = sum(p for k, p in sq_pts.items() if p and status(mine[k]).lower() == "review code")

    out = [f"📋 <b>{esc(sq).upper()} · {tab_name(today)}</b>", f"📝 Daily sheet: {sheet_note}"]
    if mine:
        out += ["", f"<b>━━ {esc(sprint_name)}{left}</b>",
                f"Point: <b>{fmt_pt(total)}</b> · qua test {fmt_pt(passed)} · chờ review {fmt_pt(review)} · "
                f"còn {fmt_pt(total - passed - review)}",
                f"Ticket: {len(todo)} cần làm · {len(mine) - len(todo)} đã qua test"]
    if todo:
        out += ["", "<b>━━ Cần làm</b>"]
        for k in sorted(todo, key=lambda k: rank_of(todo[k])):
            f, p = todo[k], pts[k]
            out.append(f"{LABEL.get(status(f).lower(), '⚫ ' + esc(status(f)))} · {link(k)} {esc(short(f['summary']))}"
                       + (f" · {fmt_pt(p)}p" if p else ""))
            a = apis.get(k)
            if a and a[1].lower() not in API_READY:
                out.append(f"      ↳ ⏳ chờ API {link(a[0])} · {esc(a[2])} ({esc(a[1])})")

    # Action items: one message each so Percy can ❤ them one by one.
    items = []
    for k in (k for k, p in sq_pts.items() if p is None):
        items.append((item_id(f"p:{k}"), f"⚠️ <b>Chưa est point</b> · {link(k)} {esc(short(mine[k]['summary']))}"))
    for k, a in chase.items():
        if squad(sprint_issues[k]) == sq:
            items.append((item_id(f"a:{a[0]}:{a[1]}"),
                          f"🔴 <b>Dí API</b> · {esc(a[2])}: {link(a[0])} <i>{esc(a[1])}</i> → chặn {link(k)}"))
    sq_comments = [c for c in comments if squad(recent[c[0]]) == sq]
    for k, who, t, cid, tagged in sq_comments:
        if tagged:
            items.append((item_id(f"c:{cid}"), f"🔔 <b>Cần trả lời</b> · {clink(k, cid)} <b>{esc(who)}</b>: {esc(t)}"))
    same = {}  # same author + text on many tickets (e.g. "đã có trong build staging") -> one item
    for k, who, t, cid, tagged in sq_comments:
        if not tagged:
            same.setdefault((who, t), []).append((k, cid))
    for (who, t), v in same.items():
        items.append((item_id("c:" + ",".join(cid for _, cid in v)),
                      f"💬 <b>{esc(who)}</b> ({', '.join(clink(k, cid) for k, cid in v)}): {esc(t)}"))
    for k, f in bugs.items():
        if squad(f) == sq:
            items.append((item_id(f"b:{k}"), f"🐞 <b>Bug mới</b> · {link(k)} {esc(short(f['summary']))} — <i>{esc(status(f))}</i>"))
    open_items = [(h, html) for h, html in items if h not in state["resolved"]]
    if open_items:
        out += ["", f"👇 {len(open_items)} việc cần xử lý · thả ❤️ việc nào xong để ẩn"]

    if len(out) > 2 or open_items:
        tg("\n".join(out), TOPICS.get(sq))
    for h, html in open_items:
        mid = tg(html, TOPICS.get(sq))
        if mid:
            state["sent"][str(mid)] = h

save_state()
