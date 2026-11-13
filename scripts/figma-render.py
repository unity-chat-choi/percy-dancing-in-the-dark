"""Render every Figma frame linked in a ticket-context file to PNG, so Claude can compare the UI with the design.

Usage: figma-render.py <context.md> <out-dir>    Env: FIGMA_TOKEN. Writes <out-dir>/<fileKey>_<node>.png (max 8).
"""
import json, os, re, sys, urllib.parse, urllib.request

ctx, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
links = re.findall(r"figma\.com/(?:design|file)/([A-Za-z0-9]+)/[^\s?|\])]*\?[^\s|\])]*?node-id=([0-9]+[-:][0-9]+)", open(ctx).read())
nodes = list(dict.fromkeys((k, n.replace("-", ":")) for k, n in links))[:8]
H = {"X-Figma-Token": os.environ["FIGMA_TOKEN"]}
done = 0
for key, node in nodes:
    q = urllib.parse.urlencode({"ids": node, "scale": 2, "format": "png"})
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://api.figma.com/v1/images/{key}?{q}", headers=H), timeout=90) as r:
            url = (json.load(r).get("images") or {}).get(node)
        if url:
            urllib.request.urlretrieve(url, os.path.join(out, f"{key}_{node.replace(':', '-')}.png"))
            done += 1
    except Exception as e:  # a dead link must not stop the run
        print("figma skip:", type(e).__name__)
print(f"figma: {done}/{len(nodes)} frames")
