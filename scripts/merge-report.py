"""Merge the iOS and Android QC results of a task into one report.

Usage: merge-report.py <title> <figma dir> <qc root> <issue> <out dir>
<qc root>/<platform>/ holds qc-report.md, pairs.json and screenshots (fetched by task-files.py get).
Writes <out>/report.html (Figma | Light | Dark | RTL per screen and platform), <out>/comment.md (with in-repo
image links, for the private task) and <out>/telegram.md (text only).
"""
import base64, html, json, os, re, subprocess, sys

title, figma_dir, root, issue, out = sys.argv[1:6]
PLATS = [p for p in ("ios", "android") if os.path.isfile(os.path.join(root, p, "qc-report.md"))]
NAME = {"ios": "iOS", "android": "Android"}
MODES = ("light", "dark", "rtl")
esc = html.escape
os.makedirs(out, exist_ok=True)


def verdict(md):
    m = re.search(r"Kết quả:\s*([^\n]+)", md)
    return m.group(1).strip() if m else "?"


def load(p):
    d = os.path.join(root, p)
    md = open(os.path.join(d, "qc-report.md")).read()
    try:
        pairs = json.load(open(os.path.join(d, "pairs.json")))
    except (OSError, ValueError):
        pairs = []
    shots = sorted(f for f in os.listdir(d) if f.endswith(".png"))
    if not pairs:  # group "<n>-<screen>-<mode>.png"
        g = {}
        for f in shots:
            m = re.match(r"(.+)-(light|dark|rtl)\.png$", f)
            g.setdefault(m.group(1) if m else f, {})[m.group(2) if m else "light"] = f
        pairs = [{"screen": k, "shots": v} for k, v in g.items()]
    return {"md": md, "pairs": pairs, "dir": d, "verdict": verdict(md)}


data = {p: load(p) for p in PLATS}
figmas = sorted(f for f in os.listdir(figma_dir) if f.endswith(".png")) if os.path.isdir(figma_dir) else []


def color(v):
    v = v.upper()
    return "#16a34a" if "PASS" in v else "#dc2626" if "FAIL" in v else "#d97706"


def img(path):
    if not path or not os.path.isfile(path):
        return '<div class="none">—</div>'
    return f'<img src="data:image/png;base64,{base64.b64encode(open(path, "rb").read()).decode()}">'


def key(s):
    return re.sub(r"^\d+-", "", (s or "").lower()).strip()


screens = {}
for p, d in data.items():
    for pr in d["pairs"]:
        e = screens.setdefault(key(pr.get("screen")), {"name": pr.get("screen", ""), "figma": "", "rows": {}})
        e["figma"] = e["figma"] or pr.get("figma", "")
        e["rows"][p] = pr

sections = []
for e in screens.values():
    fig = os.path.join(figma_dir, e["figma"]) if e["figma"] else (os.path.join(figma_dir, figmas[0]) if figmas else "")
    rows = []
    for p in PLATS:
        pr = e["rows"].get(p)
        if not pr:
            continue
        s = pr.get("shots") or {}
        cells = "".join(f'<figure><figcaption>{m.upper()}</figcaption>{img(os.path.join(data[p]["dir"], s.get(m, "")))}</figure>' for m in MODES)
        rows.append(f'<div class="plat"><b>{NAME[p]}</b> <span class="tag">{esc(pr.get("verdict", ""))}</span>'
                    f'<p class="notes">{esc(pr.get("notes", ""))}</p><div class="grid3">{cells}</div></div>')
    sections.append(f'<section><h3>{esc(e["name"])}</h3><div class="row"><figure class="fig"><figcaption>FIGMA</figcaption>{img(fig)}</figure>'
                    f'<div class="plats">{"".join(rows)}</div></div></section>')


def md_html(text):
    o, ul = [], False
    for line in text.splitlines():
        h = re.match(r"^(#+)\s*(.+)", line)
        li = re.match(r"^\s*(?:[-*]|\d+\.)\s+(.+)", line)
        if ul and not li:
            o.append("</ul>"); ul = False
        if h:
            o.append(f"<h4>{esc(h.group(2))}</h4>")
        elif li:
            if not ul:
                o.append("<ul>"); ul = True
            o.append(f"<li>{esc(li.group(1))}</li>")
        elif line.strip():
            o.append(f"<p>{esc(line)}</p>")
    if ul:
        o.append("</ul>")
    return "\n".join(o)


badges = "".join(f'<span class="badge" style="background:{color(d["verdict"])}">{NAME[p]}: {esc(d["verdict"])}</span>' for p, d in data.items())
texts = "".join(f'<details open><summary>{NAME[p]} — chi tiết</summary>{md_html(d["md"])}</details>' for p, d in data.items())
page = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>
:root{{--bg:#fff;--fg:#111;--mut:#666;--card:#f4f4f5;--line:#e4e4e7}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0b0b0c;--fg:#eee;--mut:#9a9a9a;--card:#18181b;--line:#27272a}}}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,system-ui,sans-serif}}
main{{max-width:1300px;margin:auto}} h1{{font-size:20px;margin:0 0 8px}}
.badge{{display:inline-block;margin:0 6px 6px 0;padding:4px 10px;border-radius:8px;color:#fff;font-weight:700}}
section{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:16px 0}}
.row{{display:grid;grid-template-columns:1fr 3fr;gap:12px}} .grid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}
@media (max-width:800px){{.row{{grid-template-columns:1fr}}}}
.plat{{margin-bottom:12px}} figure{{margin:0}} figcaption{{font-size:11px;color:var(--mut);font-weight:700;margin-bottom:4px}}
img{{width:100%;border-radius:8px;border:1px solid var(--line)}} .none{{padding:40px 8px;text-align:center;color:var(--mut);border:1px dashed var(--line);border-radius:8px}}
.tag,.notes{{color:var(--mut);font-size:13px}} .notes{{margin:2px 0 6px}} details{{margin-top:16px}} summary{{font-weight:700;cursor:pointer}}
</style></head><body><main><h1>{esc(title)}</h1>{badges}
<h2>So sánh từng màn</h2>{''.join(sections) or '<p>Không có ảnh chụp.</p>'}{texts}</main></body></html>"""
open(os.path.join(out, "report.html"), "w").write(page)

head = f"# {title}\n" + " · ".join(f"**{NAME[p]}: {d['verdict']}**" for p, d in data.items()) + "\n"
tg = head + "".join(f"\n## {NAME[p]}\n" + re.sub(r"^## Kết quả:[^\n]*\n", "", d["md"], flags=re.M) for p, d in data.items())
open(os.path.join(out, "telegram.md"), "w").write(tg)
comment = tg
for p, d in data.items():
    imgs = [f for f in sorted(os.listdir(d["dir"])) if f.endswith(".png")]
    if imgs:
        links = subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(__file__), "task-files.py"), "url", issue, p, "x"],
                               capture_output=True, text=True).stdout.strip().rsplit("/", 1)[0]
        comment += f"\n### Ảnh {NAME[p]}\n" + "\n".join(f'<img src="{links}/{f}?raw=true" width="220" alt="{f}">' for f in imgs) + "\n"
open(os.path.join(out, "comment.md"), "w").write(comment)
print(f"merged: {', '.join(PLATS) or 'none'}; {len(screens)} screens")
