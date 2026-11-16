"""Kotlin port follow-up that used to need Percy's Mac (port-watch + merge/approve), run by .github/workflows/kotlin-gate.yml.

1. Unit MRs  migration/* -> */percy/*   : pipeline success + NEEDS_HUMAN "không có" -> merge.
2. Feature   */percy/* or a filed migration/bug-* -> app-develop : pipeline success + mergeable -> approve (Mason merges).
   A failed pipeline whose log says the Gradle local cache entry is missing gets its job retried once.
3. Done comments: ports/queue.json in the private task repo lists RN branches waiting for their Kotlin feature MR:
   [{"branch", "rn_mr", "tickets": [{"key", "comment_id"?, "shots_issue"?}], "done"?}]. When the feature MR exists:
   comment_id -> append "* MR Android: <url>" to that comment; else post the team comment (dark|light shots from
   shots/issue-<n>, MR RN, MR Android, cc Mason). In Progress tickets move to REVIEW CODE.
Public repo: prints counts and MR numbers only.
Env: GITLAB_TV_TOKEN GITLAB_PROJECT JIRA_URL JIRA_EMAIL JIRA_API_TOKEN TASKS_PAT TASKS_REPO
"""
import base64, json, os, re, urllib.parse, urllib.request, uuid

KT = "https://gitlab.uniscore.tv/api/v4/projects/uniscore-mobile%2Funiscore-kotlin"
GLT = {"PRIVATE-TOKEN": os.environ["GITLAB_TV_TOKEN"]}
J = os.environ["JIRA_URL"].rstrip("/")
JA = {"Authorization": "Basic " + base64.b64encode(f"{os.environ['JIRA_EMAIL']}:{os.environ['JIRA_API_TOKEN']}".encode()).decode()}
GH = {"Authorization": f"Bearer {os.environ['TASKS_PAT']}", "Accept": "application/vnd.github+json"}
REPO = os.environ["TASKS_REPO"]
RN = "https://gitlab.com/" + os.environ["GITLAB_PROJECT"] + "/-/merge_requests/"
MASON = "712020:6df676d4-7e2b-4711-9f90-2f0c1f8119c6"
BUGS = {"migration/bug-275", "migration/bug-295"}  # factory bug requests Percy filed


def http(url, headers, data=None, method=None, raw=False):
    if isinstance(data, (dict, list)):
        data, headers = json.dumps(data).encode(), {**headers, "Content-Type": "application/json"}
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=60) as r:
        body = r.read()
    return body if raw else (json.loads(body) if body.strip() else None)


def gate():
    acted = 0
    for m in http(f"{KT}/merge_requests?state=opened&per_page=100", GLT):
        src, tgt, iid = m["source_branch"], m["target_branch"], m["iid"]
        unit = src.startswith("migration/") and "/percy/" in tgt
        feature = tgt == "app-develop" and ("/percy/" in src or src in BUGS)
        if not (unit or feature):
            continue
        full = http(f"{KT}/merge_requests/{iid}", GLT)
        pipe = full.get("head_pipeline") or {}
        if pipe.get("status") == "failed":
            jobs = [j for j in http(f"{KT}/pipelines/{pipe['id']}/jobs", GLT) if j["status"] == "failed"]
            if jobs and len(jobs) == 1 and jobs[0].get("retried") is not True:
                trace = http(f"{KT}/jobs/{jobs[0]['id']}/trace", GLT, raw=True).decode("utf-8", "replace")
                if "Failed to load cache entry" in trace:
                    http(f"{KT}/jobs/{jobs[0]['id']}/retry", GLT, b"", "POST")
                    print(f"!{iid}: CI cache flake, job retried"); acted += 1
                else:
                    print(f"!{iid}: pipeline failed, needs a look")
            continue
        if pipe.get("status") != "success" or full.get("detailed_merge_status") != "mergeable":
            continue
        if unit:
            nh = re.search(r"NEEDS_HUMAN[^\n]*\n?[^\n]*", full.get("description") or "", re.I)
            if nh and not re.search(r"không có|none", nh.group(0), re.I):
                print(f"!{iid}: NEEDS_HUMAN has items, left for Percy")
                continue
            http(f"{KT}/merge_requests/{iid}/merge", GLT, b"", "PUT")
            print(f"!{iid}: unit merged"); acted += 1
        else:
            ap = http(f"{KT}/merge_requests/{iid}/approvals", GLT)
            if ap.get("user_can_approve") and not ap.get("user_has_approved"):
                http(f"{KT}/merge_requests/{iid}/approve", GLT, b"", "POST")
                print(f"!{iid}: approved for review"); acted += 1
    return acted


def feature_mr(branch):
    q = urllib.parse.urlencode({"state": "all", "source_branch": branch, "target_branch": "app-develop", "per_page": 5})
    mrs = [m for m in http(f"{KT}/merge_requests?{q}", GLT) if m["state"] != "closed"]
    return mrs[0]["web_url"] if mrs else None


def shots(issue):
    """dark first then light (team format), max 4, from shots/issue-<n> in the private repo."""
    try:
        names = [f["name"] for f in http(f"https://api.github.com/repos/{REPO}/contents/shots/issue-{issue}", GH)]
    except Exception:  # noqa: BLE001  no shots folder: comment without images
        return []
    pick = ([n for n in names if "dark" in n][:2] + [n for n in names if "light" in n][:2])[:4] or names[:4]
    return [(n, http(f"https://api.github.com/repos/{REPO}/contents/shots/issue-{issue}/{n}",
                     {**GH, "Accept": "application/vnd.github.raw"}, raw=True)) for n in pick]


def upload(key, name, data):
    b = uuid.uuid4().hex
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\nContent-Type: image/png\r\n\r\n"
            ).encode() + data + f"\r\n--{b}--\r\n".encode()
    return http(f"{J}/rest/api/3/issue/{key}/attachments", {**JA, "X-Atlassian-Token": "no-check",
                "Content-Type": f"multipart/form-data; boundary={b}"}, body, "POST")[0]["filename"]


def to_review(key):
    st = http(f"{J}/rest/api/3/issue/{key}?fields=status", JA)["fields"]["status"]["name"]
    if st == "In Progress":  # team rule; tickets QC sent back stay where QC put them
        http(f"{J}/rest/api/3/issue/{key}/transitions", JA, {"transition": {"id": "51"}}, "POST")


def done_comments():
    url = f"https://api.github.com/repos/{REPO}/contents/ports/queue.json"
    meta = http(url, GH)
    queue = json.loads(base64.b64decode(meta["content"]).decode())
    posted = 0
    for e in queue:
        if e.get("done"):
            continue
        kmr = feature_mr(e["branch"])
        if not kmr:
            continue
        for t in e["tickets"]:
            if t.get("comment_id"):
                c = http(f"{J}/rest/api/2/issue/{t['key']}/comment/{t['comment_id']}", JA)["body"]
                if "MR Android" not in c:
                    m = re.search(r"(\* MR RN: [^\n]+)", c)
                    c = c.replace(m.group(1), m.group(1) + f"\n* MR Android: {kmr}", 1) if m else c + f"\n* MR Android: {kmr}"
                    http(f"{J}/rest/api/2/issue/{t['key']}/comment/{t['comment_id']}", JA, {"body": c}, "PUT")
            else:
                imgs = [upload(t["key"], n, d) for n, d in shots(t.get("shots_issue"))] if t.get("shots_issue") else []
                body = (" ".join(f"!{n}|width=220!" for n in imgs) + "\n\n" if imgs else "") + \
                    f"* MR RN: {RN}{e['rn_mr']}\n* MR Android: {kmr}\n\ncc: [~accountid:{MASON}]\n"
                http(f"{J}/rest/api/2/issue/{t['key']}/comment", JA, {"body": body}, "POST")
            to_review(t["key"])
            posted += 1
        e["done"] = True
    if posted:
        http(url, GH, {"message": "ports: done comments", "sha": meta["sha"],
                       "content": base64.b64encode(json.dumps(queue, indent=1, ensure_ascii=False).encode()).decode()}, "PUT")
    return posted


if __name__ == "__main__":
    a = gate()
    p = done_comments()
    print(f"gate actions: {a}, done comments: {p}")
