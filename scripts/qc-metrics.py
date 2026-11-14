"""One row per QC run in the private task repo (metrics/qc.csv), to see QC getting faster run after run.

add <platform>   append: time, issue, ticket, platform, minutes, shots, tmp shots, scenarios replayed/new, setup flows new, result
Run from the workspace root (reads ctx/, shots/). Env: GH_TOKEN, TASKS_REPO, ISSUE, KEY
"""
import base64, glob, json, os, sys, time, urllib.error, urllib.request

URL = f"https://api.github.com/repos/{os.environ['TASKS_REPO']}/contents/metrics/qc.csv"
H = {"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json"}
HEAD = "time,issue,ticket,platform,qc_min,shots,tmp_shots,scenarios_replayed,scenarios_new,flows_new,result\n"

n = lambda pat: len(glob.glob(pat))
try:
    start = int(open("ctx/qc-start").read().strip())
except (OSError, ValueError):
    start = None
try:
    result = json.load(open("ctx/verdict.json")).get("result", "?")
except (OSError, ValueError):
    result = "none"
row = [time.strftime("%Y-%m-%d %H:%M", time.gmtime()), os.environ.get("ISSUE", ""), os.environ.get("KEY", ""), sys.argv[2],
       f"{(time.time() - start) / 60:.0f}" if start else "", str(n("shots/*.png")), str(n("shots/tmp*.png")),
       str(n("ctx/scenarios/*.yaml")), str(n("ctx/scenarios-new/*.yaml")), str(n("ctx/flows-new/*.yaml")), result]

try:
    with urllib.request.urlopen(urllib.request.Request(URL, headers=H), timeout=30) as r:
        d = json.load(r)
    text, sha = base64.b64decode(d["content"]).decode(), d["sha"]
except urllib.error.HTTPError:
    text, sha = HEAD, None
body = {"message": "qc metrics", "content": base64.b64encode((text + ",".join(row) + "\n").encode()).decode()}
if sha:
    body["sha"] = sha
urllib.request.urlopen(urllib.request.Request(URL, data=json.dumps(body).encode(), headers=H, method="PUT"), timeout=30)
print(f"qc metrics: {row[3]} {row[4]} min")
