"""QC rulebook that improves every run, stored in the private task repo (lessons/qc.md: app details stay private).

get <out.md>       download the rulebook (empty file if none yet)
add <new.md>       append the bullet lines of <new.md> that are not in the rulebook yet
Env: GH_TOKEN, TASKS_REPO
"""
import base64, json, os, re, sys, urllib.error, urllib.request

URL = f"https://api.github.com/repos/{os.environ['TASKS_REPO']}/contents/lessons/qc.md"
H = {"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json"}


def fetch():
    try:
        with urllib.request.urlopen(urllib.request.Request(URL, headers=H), timeout=30) as r:
            d = json.load(r)
        return base64.b64decode(d["content"]).decode(), d["sha"]
    except urllib.error.HTTPError:
        return "# Quy tắc QC (tự cập nhật sau mỗi lần chạy)\n", None


norm = lambda l: re.sub(r"\W+", " ", l.lower()).strip()
cmd = sys.argv[1]
text, sha = fetch()
if cmd == "get":
    open(sys.argv[2], "w").write(text)
elif cmd == "add" and os.path.exists(sys.argv[2]):
    have = {norm(l) for l in text.splitlines()}
    new = [l.rstrip() for l in open(sys.argv[2]) if l.strip().startswith("- ") and norm(l) not in have]
    if new:
        body = {"message": f"lessons +{len(new)}", "content": base64.b64encode((text.rstrip() + "\n" + "\n".join(new) + "\n").encode()).decode()}
        if sha:
            body["sha"] = sha
        urllib.request.urlopen(urllib.request.Request(URL, data=json.dumps(body).encode(), headers=H, method="PUT"), timeout=30)
    print(f"lessons: +{len(new)}")
