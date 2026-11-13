"""Store / fetch QC files of a task in the private task repo under qc/issue-<n>/<platform>/.

put <issue> <platform> <file>...   upload (overwrite)
get <issue> <platform> <out dir>  download everything for that platform (missing platform = empty dir)
url <issue> <platform> <name>     print the in-repo image URL (renders for org members)
Env: GH_TOKEN, TASKS_REPO
"""
import base64, json, os, sys, urllib.error, urllib.request

repo = os.environ["TASKS_REPO"]
H = {"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json"}
api = f"https://api.github.com/repos/{repo}/contents"


def call(url, data=None, method=None, raw=False):
    h = dict(H, Accept="application/vnd.github.raw") if raw else H
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h, method=method), timeout=60) as r:
        return r.read() if raw else json.load(r)


cmd, issue, plat = sys.argv[1], sys.argv[2], sys.argv[3]
base = f"qc/issue-{issue}/{plat}"
if cmd == "url":
    print(f"https://github.com/{repo}/blob/HEAD/{base}/{sys.argv[4]}?raw=true")
elif cmd == "put":
    for path in sys.argv[4:]:
        if not os.path.isfile(path):
            continue
        url = f"{api}/{base}/{os.path.basename(path)}"
        body = {"message": f"qc #{issue} {plat}", "content": base64.b64encode(open(path, "rb").read()).decode()}
        try:
            body["sha"] = call(url)["sha"]
        except urllib.error.HTTPError:
            pass
        call(url, json.dumps(body).encode(), "PUT")
elif cmd == "get":
    out = sys.argv[4]
    os.makedirs(out, exist_ok=True)
    try:
        items = call(f"{api}/{base}")
    except urllib.error.HTTPError:
        items = []
    for it in items:
        open(os.path.join(out, it["name"]), "wb").write(call(f"{api}/{base}/{it['name']}", raw=True))
    print(f"{plat}: {len(items)} files")
