"""Gather everything about a Jira ticket into one Markdown file, so it can be read end to end before acting.

ticket + parent story + sibling tickets ([API]/[Web]...) + subtasks, all comments, every Confluence page that
mentions any of those keys (full text, including Out of scope / Q&A), and Figma links found anywhere.
Usage: ticket-context.py <ISSUE-KEY> [out.md]   (default: ~/.cache/ticket-context/<KEY>.md)
Credentials: env JIRA_URL/JIRA_EMAIL/JIRA_API_TOKEN, else ~/.claude/jira-credentials.json.
"""
import base64, html, json, os, re, sys, urllib.parse, urllib.request

KEY = sys.argv[1].upper()
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser(f"~/.cache/ticket-context/{KEY}.md")
if os.environ.get("JIRA_API_TOKEN"):
    email, token = os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"]
else:
    c = json.load(open(os.path.expanduser("~/.claude/jira-credentials.json")))
    email, token = c["email"], c["token"]
SITE = os.environ.get("JIRA_URL") or next((l.split("=", 1)[1].strip() for l in open(os.path.expanduser(
    "~/.config/cutcut/uniscore-runner-secrets.env")) if l.startswith("JIRA_URL=")), "")
SITE = SITE.rstrip("/")
H = {"Authorization": "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode(), "Accept": "application/json"}


def get(path):
    with urllib.request.urlopen(urllib.request.Request(SITE + path, headers=H), timeout=40) as r:
        return json.load(r)


def strip_html(s):
    s = re.sub(r"<(br|/p|/li|/h\d|/tr)[^>]*>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"[ \t]+", " ", html.unescape(s)).strip()


def issue(k):
    f = get(f"/rest/api/2/issue/{k}?fields=summary,status,assignee,reporter,description,comment,issuelinks,subtasks,"
            "customfield_10001,customfield_10020")["fields"]
    return f


seen, sections, figma = {}, [], set()


def add(k, role):
    if k in seen:
        return seen[k]
    f = issue(k)
    seen[k] = f
    team = (f.get("customfield_10001") or {}).get("name") if isinstance(f.get("customfield_10001"), dict) else None
    lines = [f"## {role}: {k} — {f['summary']}",
             f"Status: {f['status']['name']} · Assignee: {(f.get('assignee') or {}).get('displayName')} · "
             f"Reporter: {(f.get('reporter') or {}).get('displayName')} · Team: {team}",
             "", "### Description", f.get("description") or "(none)"]
    for cm in f["comment"]["comments"]:
        lines += ["", f"### Comment {cm['id']} — {cm['author']['displayName']} {cm['created'][:16]}", cm["body"]]
    sections.append("\n".join(lines))
    figma.update(re.findall(r"https://www\.figma\.com/[^\s|\]\)]+", "\n".join(lines)))
    return f


main = add(KEY, "Ticket")
parents = [l["inwardIssue"]["key"] for l in main["issuelinks"] if l["type"]["name"] == "Parent - Child" and "inwardIssue" in l]
for p in parents:
    pf = add(p, "Parent story")
    for l in pf["issuelinks"]:
        o = l.get("outwardIssue")
        if o and l["type"]["name"] == "Parent - Child":
            add(o["key"], "Sibling")
for l in main["issuelinks"]:
    o = l.get("outwardIssue") or l.get("inwardIssue")
    if o and l["type"]["name"] != "Parent - Child":
        add(o["key"], f"Linked ({l['type']['name']})")
for k in list(seen):
    for s in seen[k].get("subtasks", []):
        add(s["key"], f"Subtask of {k}")

pages = {}
for k in seen:
    q = urllib.parse.urlencode({"cql": f'text ~ "{k}"', "limit": 10})
    for r in get(f"/wiki/rest/api/search?{q}").get("results", []):
        cid = (r.get("content") or {}).get("id")
        if cid and cid not in pages:
            pages[cid] = r["content"]["title"]
for cid, title in pages.items():
    body = get(f"/wiki/rest/api/content/{cid}?expand=body.storage,version")
    text = strip_html(body["body"]["storage"]["value"])
    figma.update(re.findall(r"https://www\.figma\.com/[^\s|\]\)\"]+", text))
    sections.append(f"## Confluence {cid}: {title} (v{body['version']['number']}, {body['version']['when'][:10]})\n"
                    f"{SITE}/wiki/pages/{cid}\n\n{text}")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
head = [f"# Context {KEY}", f"Tickets: {', '.join(seen)}", f"Confluence pages: {len(pages)}",
        "Figma: " + (", ".join(sorted(figma)) or "none"),
        "", "> Read every section, especially Out of scope, open questions (Q1..), status/rollout and comment replies."]
with open(OUT, "w") as f:
    f.write("\n".join(head) + "\n\n" + "\n\n---\n\n".join(sections) + "\n")
print(f"{OUT}  ({len(seen)} tickets, {len(pages)} pages, {sum(len(s) for s in sections) // 1000}k chars)")
