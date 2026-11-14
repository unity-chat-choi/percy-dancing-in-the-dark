"""Verified Maestro setup flows (onboarding, theme, language…), shared by every QC run.
Stored in the private task repo under flows/ (app details stay private), next to lessons/qc.md.

get <dir> [path]   download every flow under <path> (default flows/) into <dir>
put <dir> [path]   upload <dir>/*.yaml to <path> (same name replaces the stored flow)
Per-ticket test scenarios live under scenarios/<ticket key>/.
Env: GH_TOKEN, TASKS_REPO
"""
import base64, glob, json, os, sys, urllib.error, urllib.request

cmd, d = sys.argv[1], sys.argv[2]
API = f"https://api.github.com/repos/{os.environ['TASKS_REPO']}/contents/" + (sys.argv[3] if len(sys.argv) > 3 else "flows").strip("/")
H = {"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json"}


def call(url, data=None, method=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, headers=H, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def listing():
    try:
        return {f["name"]: f for f in call(API) if f["name"].endswith(".yaml")}
    except urllib.error.HTTPError:
        return {}


have = listing()
if cmd == "get":
    os.makedirs(d, exist_ok=True)
    for name, f in have.items():
        open(os.path.join(d, name), "wb").write(base64.b64decode(call(f["url"])["content"]))
    print(f"flows: {len(have)}")
elif cmd == "put":
    n = 0
    for p in sorted(glob.glob(os.path.join(d, "*.yaml"))):
        name = os.path.basename(p)
        body = {"message": f"flow {name}", "content": base64.b64encode(open(p, "rb").read()).decode()}
        if name in have:
            body["sha"] = have[name]["sha"]
        call(f"{API}/{name}", body, "PUT"); n += 1
    print(f"flows: +{n}")
