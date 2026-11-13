"""Rule-based Jira watcher (no LLM, no tokens): runs on the Mac every 5 min from trigger.sh.

Rules (JQL), each item reported once (state in ~/.cache/percy-scan/state.json):
  new_task   assigned to me / I'm Engineer, in an open sprint, not a Bug, not seen before
  new_bug    Bug assigned to me / I'm Engineer, not seen before
  qc_back    my ticket moved to FIXING / Review fail since the last scan (QC sent it back)
  mention    a new comment that @mentions me
Each report goes to the ticket's squad topic with buttons: ▶️ Giao runner làm (run:<KEY>) / 👀 Để sau (skip:<KEY>).
The daily poll handles the buttons. First run only records the current state (no flood).
Reads ~/.config/cutcut/uniscore-runner-secrets.env. LOCAL=1 prints instead of sending.
"""
import base64, datetime as dt, hashlib, json, os, re, urllib.parse, urllib.request

HOME = os.path.expanduser("~")
if os.environ.get("JIRA_URL"):  # GitHub runner: secrets come in as env
    ENV = dict(os.environ)
else:  # Mac
    ENV = {k: v.strip().strip("'\"") for k, v in (l.split("=", 1) for l in open(
        f"{HOME}/.config/cutcut/uniscore-runner-secrets.env").read().splitlines() if "=" in l and not l.startswith("#"))}
JIRA = ENV["JIRA_URL"].rstrip("/")
AUTH = {"Authorization": "Basic " + base64.b64encode(f"{ENV['JIRA_EMAIL']}:{ENV['JIRA_API_TOKEN']}".encode()).decode(),
        "Accept": "application/json"}
STATE = os.environ.get("SCAN_STATE") or f"{HOME}/.cache/percy-scan/state.json"
# In the public runner repo the state is committed, so keys and comment ids are stored only as hashes.
H = (lambda x: hashlib.sha1(str(x).encode()).hexdigest()[:12]) if os.environ.get("SCAN_HASH") == "1" else str
MINE = "(assignee = currentUser() OR cf[10075] = currentUser())"
BACK = {"fixing", "review fail"}


def get(url, headers=AUTH):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return json.load(r)


def jql(q, fields="summary,status,issuetype,customfield_10001", n=100):
    u = f"{JIRA}/rest/api/3/search/jql?" + urllib.parse.urlencode({"jql": q, "fields": fields, "maxResults": n})
    return get(u).get("issues", [])


def adf_text(n):
    if isinstance(n, dict):
        if n.get("type") == "mention":
            return "@" + n.get("attrs", {}).get("text", "").lstrip("@")
        return n.get("text", "") + " ".join(adf_text(c) for c in n.get("content", []))
    return ""


def team(f):
    t = f.get("customfield_10001")
    return t.get("name") if isinstance(t, dict) else ""


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send(f, key, text, buttons=True):
    if os.environ.get("LOCAL") == "1":
        print("---", key, re.sub("<[^>]+>", "", text)); return
    topics = json.loads(ENV.get("TG_SQUAD_TOPICS") or "{}")
    msg = {"chat_id": ENV["TG_NOTIFY_CHAT_ID"], "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if topics.get(team(f)):
        msg["message_thread_id"] = topics[team(f)]
    if buttons:
        msg["reply_markup"] = {"inline_keyboard": [[{"text": "▶️ Giao runner làm", "callback_data": f"run:{key}"},
                                                    {"text": "👀 Để sau", "callback_data": f"skip:{key}"}]]}
    req = urllib.request.Request(f"https://api.telegram.org/bot{ENV['TG_TICKET_BOT_TOKEN']}/sendMessage",
                                 data=json.dumps(msg).encode(), headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=20)


def link(key):
    return f'<a href="{JIRA}/browse/{key}">{key}</a>'


def group_key(k, f):
    """Same parent story, else the same bracket tags at the start of the summary (one QC pass)."""
    links = get(f"{JIRA}/rest/api/3/issue/{k}?fields=issuelinks")["fields"]["issuelinks"]
    parent = next((l["inwardIssue"]["key"] for l in links if l["type"]["name"] == "Parent - Child" and "inwardIssue" in l), None)
    if parent:
        return f"story {parent}"
    tags = re.findall(r"\[([^\]]+)\]", f["summary"])
    return "nhãn " + "".join(f"[{t}]" for t in tags[:5]) if len(tags) >= 2 else f"ticket {k}"


def auto_start(items):
    """Group new tasks / bugs / QC send-backs, open one task per group in the private repo and start the runner."""
    gh = {"Authorization": f"Bearer {ENV['TASKS_PAT']}", "Accept": "application/vnd.github+json"}
    busy = {m for i in get(f"https://api.github.com/repos/{ENV['TASKS_REPO']}/issues?state=open&per_page=100", gh)
            for m in re.findall(r"(?:US|UTD|UOB)-\d+", i["title"] + " " + (i.get("body") or "")) if "done" not in [x["name"] for x in i["labels"]]}
    groups = {}
    for f, k in items:
        if k in busy or "[api]" in f["summary"].lower() or "[web" in f["summary"].lower():
            continue  # already being worked on / not an app ticket
        groups.setdefault(group_key(k, f), []).append((f, k))
    started = []  # (task number, [(fields, key)], why)
    proj = urllib.parse.quote(ENV["GITLAB_PROJECT"], safe="")
    for why, members in groups.items():
        keys = [k for _, k in members][:4]
        mine = []
        for k in keys:
            br = get(f"https://gitlab.com/api/v4/projects/{proj}/repository/branches?search={k}&per_page=20", {"PRIVATE-TOKEN": ENV["GITLAB_TOKEN"]})
            mine += [b["name"] for b in br if "/percy/" in b["name"] and not b["name"].startswith("runner/")]
        bug = any(f["issuetype"]["name"] == "Bug" or f["status"]["name"].lower() in BACK for f, _ in members)
        branch = mine[0] if mine else f"{'fixbug' if bug else 'feature'}/percy/{'-'.join(keys)}"
        title = f"{' '.join(keys)} {members[0][0]['summary']}"[:200]
        body = (f"branch: {branch}\n" + "\n".join(f"jira: {JIRA}/browse/{k}" for k in keys)
                + f"\n\n## Ghi chú\nTự giao bởi bộ quét ({why}). Làm theo Jira, so Figma, verify/jest, QC iOS/Android.\n")
        n = post(f"https://api.github.com/repos/{ENV['TASKS_REPO']}/issues", gh, {"title": title, "body": body, "labels": ["todo"]})["number"]
        post(f"https://api.github.com/repos/{ENV['GITHUB_REPOSITORY']}/actions/workflows/ticket.yml/dispatches",
             {"Authorization": f"Bearer {ENV['DISPATCH_TOKEN']}", "Accept": "application/vnd.github+json"},
             {"ref": "main", "inputs": {"issue": str(n)}})
        started.append((n, members[:4], why))
    return started


def post(url, headers, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={**headers, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    return json.loads(body) if body else {}


def main():
    try:
        st = json.load(open(STATE))
    except (OSError, ValueError):
        st = {}
    first = not st
    seen, status, comments = set(st.get("seen", [])), st.get("status", {}), set(st.get("comments", []))
    me = get(f"{JIRA}/rest/api/3/myself")["accountId"]
    out = []

    for i in jql(f"{MINE} AND (sprint in openSprints() OR type = Bug) AND statusCategory != Done ORDER BY created DESC"):
        k, f = i["key"], i["fields"]
        s, kind = f["status"]["name"], f["issuetype"]["name"]
        if H(k) not in seen:
            seen.add(H(k))
            if not first:
                tag = "🐞 <b>Bug mới</b>" if kind == "Bug" else "🆕 <b>Task mới</b>"
                out.append((f, k, f"{tag} · {link(k)} {esc(f['summary'])}\n<i>{esc(s)} · {esc(team(f) or 'chưa gắn squad')}</i>", True))
        elif status.get(H(k)) and status[H(k)].lower() != s.lower() and s.lower() in BACK and not first:
            out.append((f, k, f"↩️ <b>QC trả về</b> · {link(k)} {esc(f['summary'])}\n<i>{esc(status[H(k)])} → {esc(s)}</i>", True))
        status[H(k)] = s

    # mentions: comments on my tickets updated in the last hour
    for i in jql(f"{MINE} AND updated >= -60m", "summary,customfield_10001", 30):
        k, f = i["key"], i["fields"]
        for c in get(f"{JIRA}/rest/api/3/issue/{k}/comment?orderBy=-created&maxResults=10").get("comments", []):
            if H(c["id"]) in comments:
                continue
            comments.add(H(c["id"]))
            if first or c["author"]["accountId"] == me or me not in json.dumps(c["body"]):
                continue
            t = re.sub(r"\s+", " ", adf_text(c["body"])).strip()
            out.append((f, k, f'🔔 <b>{esc(c["author"]["displayName"])}</b> tag bạn · '
                              f'<a href="{JIRA}/browse/{k}?focusedCommentId={c["id"]}">{k}</a>\n{esc(t[:300])}', False))

    started = auto_start([(f, k) for f, k, _, b in out if b]) if ENV.get("TASKS_PAT") and not first else []
    grouped = {k for _, members, _ in started for _, k in members}
    for f, k, text, _ in out:
        if k not in grouped:  # started ones are reported once per group below
            send(f, k, text, False)
    for n, members, why in started:
        send(members[0][0], members[0][1], f"🚀 <b>Tự giao runner</b> · task #{n}\n"
             + "\n".join(f"• {link(k)} {esc(f['summary'])}" for f, k in members)
             + (f"\n<i>gom vì cùng {esc(why)}</i>" if len(members) > 1 else "")
             + "\n<i>Làm code → test iOS/Android → báo cáo vào đây.</i>", False)
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump({"seen": sorted(seen), "status": status, "comments": sorted(comments)[-2000:],
               "at": dt.datetime.now().isoformat()}, open(STATE, "w"))
    print(f"scan: {len(out)} new" + (" (first run: baseline only)" if first else ""))  # counts only: public log


if __name__ == "__main__":
    main()
