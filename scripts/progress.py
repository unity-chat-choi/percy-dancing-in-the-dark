"""Record the current step of a task on one platform: progress/issue-<n>-<platform>.json in the private task repo.

Usage: progress.py <issue> <platform: ios|android|code> <text>     Env: GH_TOKEN, TASKS_REPO
Read by Percy World (3D map) to show what each worker is doing. Never fails the caller.
"""
import base64, datetime, json, os, sys, urllib.error, urllib.request

try:
    issue, plat, text = sys.argv[1], sys.argv[2], " ".join(sys.argv[3:])[:160]
    url = f"https://api.github.com/repos/{os.environ['TASKS_REPO']}/contents/progress/issue-{issue}-{plat}.json"
    H = {"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json"}
    body = {"message": f"progress #{issue} {plat}",
            "content": base64.b64encode(json.dumps({"step": text, "at": datetime.datetime.utcnow().isoformat() + "Z",
                                                    "worker": f"{plat}-{os.environ.get('WORKER') or 1}"},
                                                   ensure_ascii=False).encode()).decode()}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=20) as r:
            body["sha"] = json.load(r)["sha"]
    except urllib.error.HTTPError:
        pass
    urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(body).encode(), headers=H, method="PUT"), timeout=20)
except Exception:
    pass
