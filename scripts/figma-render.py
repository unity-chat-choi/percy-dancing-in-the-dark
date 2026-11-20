"""Render every Figma frame linked in a ticket-context file to PNG + a text spec (sizes, paddings, fonts, colours),
so the coding agent can match the design exactly.

Usage: figma-render.py <context.md> <out-dir>    Env: FIGMA_TOKEN.
Writes <out-dir>/<fileKey>_<node>.png and .spec.txt (max 16 frames).
"""
import json, os, re, sys, urllib.parse, urllib.request

ctx, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
links = re.findall(r"figma\.com/(?:design|file)/([A-Za-z0-9]+)/[^\s?|\])]*\?[^\s|\])]*?node-id=([0-9]+[-:][0-9]+)", open(ctx).read())
nodes = list(dict.fromkeys((k, n.replace("-", ":")) for k, n in links))[:16]
H = {"X-Figma-Token": os.environ["FIGMA_TOKEN"]}
done = 0


def hexc(paints):
    for p in paints or []:
        if p.get("type") == "SOLID" and p.get("visible", True):
            c = p["color"]
            return "#%02X%02X%02X" % tuple(round(c[x] * 255) for x in "rgb") + ("" if p.get("opacity", 1) == 1 else f"@{p['opacity']:.2f}")
    return ""


def spec(n, depth, out):
    if len(out) > 600 or not n.get("visible", True):
        return
    b = n.get("absoluteBoundingBox") or {}
    st = n.get("style") or {}
    bits = [f"{n['type']} '{n.get('name', '')[:40]}'", f"{round(b.get('width', 0))}x{round(b.get('height', 0))}" if b else ""]
    if n.get("layoutMode"):
        bits.append(f"{n['layoutMode'].lower()} gap={n.get('itemSpacing', 0)} pad={n.get('paddingTop', 0)},{n.get('paddingRight', 0)},{n.get('paddingBottom', 0)},{n.get('paddingLeft', 0)}")
    if n.get("cornerRadius"):
        bits.append(f"radius={n['cornerRadius']}")
    if hexc(n.get("fills")):
        bits.append(("text=" if n["type"] == "TEXT" else "fill=") + hexc(n.get("fills")))
    if hexc(n.get("strokes")):
        bits.append(f"stroke={hexc(n.get('strokes'))}/{n.get('strokeWeight', 1)}")
    if n["type"] == "TEXT":
        bits.append(f"font={st.get('fontFamily')} {st.get('fontWeight')} {st.get('fontSize')}/{round(st.get('lineHeightPx', 0))} \"{n.get('characters', '')[:40]}\"")
    out.append("  " * depth + " ".join(x for x in bits if x))
    for c in n.get("children", []):
        spec(c, depth + 1, out)


for key, node in nodes:
    try:  # text spec first: exact numbers the PNG cannot give
        q = urllib.parse.urlencode({"ids": node})
        with urllib.request.urlopen(urllib.request.Request(f"https://api.figma.com/v1/files/{key}/nodes?{q}", headers=H), timeout=90) as r:
            doc = ((json.load(r).get("nodes") or {}).get(node) or {}).get("document")
        if doc:
            lines = []
            spec(doc, 0, lines)
            open(os.path.join(out, f"{key}_{node.replace(':', '-')}.spec.txt"), "w").write("\n".join(lines))
    except Exception as e:
        print("figma spec skip:", type(e).__name__)
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
