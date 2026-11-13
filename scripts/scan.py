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

    for f, k, text, buttons in out:
        send(f, k, text, buttons)
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump({"seen": sorted(seen), "status": status, "comments": sorted(comments)[-2000:],
               "at": dt.datetime.now().isoformat()}, open(STATE, "w"))
    print(f"scan: {len(out)} new" + (" (first run: baseline only)" if first else ""))  # counts only: public log


if __name__ == "__main__":
    main()
