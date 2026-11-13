"""Store screenshots in the private task repo (shots/issue-<n>/) and print Markdown that shows them in an issue.

Usage: task-images.py <issue> <png>...     Env: GH_TOKEN (TASKS_PAT), TASKS_REPO
The images live in a private repo, so only org members can see them; nothing goes to the public runner repo.
"""
import base64, json, os, sys, urllib.error, urllib.request

issue, files = sys.argv[1], sys.argv[2:]
repo, H = os.environ["TASKS_REPO"], {"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                                     "Accept": "application/vnd.github+json"}
lines = []
for path in files:
    name = os.path.basename(path)
    dest = f"shots/issue-{issue}/{name}"
    url = f"https://api.github.com/repos/{repo}/contents/{dest}"
    body = {"message": f"shots #{issue}", "content": base64.b64encode(open(path, "rb").read()).decode()}
    try:  # overwrite on rerun
        with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=30) as r:
            body["sha"] = json.load(r)["sha"]
    except urllib.error.HTTPError:
        pass
    urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(body).encode(), headers=H, method="PUT"), timeout=60)
    lines.append(f'<img src="https://github.com/{repo}/blob/HEAD/{dest}?raw=true" width="220" alt="{name}">')
print("\n".join(lines))
