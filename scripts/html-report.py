"""Build a self-contained HTML QC report: Figma | light | dark | RTL side by side per screen, then the text report.

Usage: html-report.py <title> <ios-report.md> <pairs.json> <figma dir> <shots dir> <out.html>
pairs.json (written by Claude): [{"screen", "figma": "<file in figma dir>", "shots": {"light","dark","rtl"}, "verdict", "notes"}]
Without pairs.json, screenshots are grouped by their "<n>-<screen>-<mode>.png" name and every Figma frame is shown on top.
"""
import base64, html, json, os, re, sys

title, md_path, pairs_path, figma_dir, shots_dir, out = sys.argv[1:7]
md = open(md_path).read() if os.path.exists(md_path) else ""
esc = html.escape


def img(path):
    if not path or not os.path.exists(path):
        return '<div class="none">không có ảnh</div>'
    return f'<img src="data:image/png;base64,{base64.b64encode(open(path, "rb").read()).decode()}" alt="{esc(os.path.basename(path))}">'


def md_html(text):
    out, in_list = [], False
    for line in text.splitlines():
        m = re.match(r"^(#+)\s*(.+)", line)
        item = re.match(r"^\s*(?:[-*]|\d+\.)\s+(.+)", line)
        if in_list and not item:
            out.append("</ul>")
            in_list = False
        if m:
            n = min(len(m.group(1)) + 1, 4)
            out.append(f"<h{n}>{esc(m.group(2))}</h{n}>")
        elif item:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{esc(item.group(1))}</li>")
        elif line.strip() and not line.lstrip().startswith("<img"):
            out.append(f"<p>{esc(line)}</p>")
    if in_list:
        out.append("</ul>")
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", "\n".join(out))


try:
    pairs = json.load(open(pairs_path))
except (OSError, ValueError):
    pairs = []
shots = sorted(f for f in os.listdir(shots_dir) if f.endswith(".png")) if os.path.isdir(shots_dir) else []
figmas = sorted(f for f in os.listdir(figma_dir) if f.endswith(".png")) if os.path.isdir(figma_dir) else []
if not pairs:  # fallback: group "<n>-<screen>-<mode>.png"
    groups = {}
    for f in shots:
        m = re.match(r"(.+)-(light|dark|rtl)\.png$", f)
        groups.setdefault(m.group(1) if m else f, {})[m.group(2) if m else "light"] = f
    pairs = [{"screen": k, "figma": figmas[0] if figmas else "", "shots": v} for k, v in groups.items()]

verdict = re.search(r"Kết quả:\s*([^\n(]+)", md)
v = (verdict.group(1).strip() if verdict else "?").upper()
color = "#16a34a" if "PASS" in v else "#dc2626" if "FAIL" in v else "#d97706"
rows = []
for p in pairs:
    s = p.get("shots") or {}
    cells = [img(os.path.join(figma_dir, p.get("figma", ""))) if p.get("figma") else '<div class="none">không có frame</div>']
    cells += [img(os.path.join(shots_dir, s[m])) if s.get(m) else '<div class="none">—</div>' for m in ("light", "dark", "rtl")]
    tag = esc(p.get("verdict", ""))
    rows.append(f'<section><h3>{esc(p.get("screen", ""))} <span class="tag">{tag}</span></h3>'
                f'<p class="notes">{esc(p.get("notes", ""))}</p><div class="grid">'
                + "".join(f'<figure><figcaption>{c}</figcaption>{x}</figure>'
                          for c, x in zip(("Figma", "Light", "Dark", "RTL"), cells)) + "</div></section>")

page = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>
:root{{--bg:#fff;--fg:#111;--mut:#666;--card:#f4f4f5;--line:#e4e4e7}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0b0b0c;--fg:#eee;--mut:#9a9a9a;--card:#18181b;--line:#27272a}}}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,system-ui,sans-serif}}
main{{max-width:1200px;margin:auto}} h1{{font-size:20px;margin:0 0 4px}}
.verdict{{display:inline-block;padding:4px 10px;border-radius:8px;color:#fff;background:{color};font-weight:700}}
section{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:16px 0}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}} @media (max-width:700px){{.grid{{grid-template-columns:repeat(2,1fr)}}}}
figure{{margin:0}} figcaption{{font-size:12px;color:var(--mut);margin-bottom:4px;font-weight:600}}
img{{width:100%;border-radius:8px;border:1px solid var(--line)}} .none{{padding:40px 8px;text-align:center;color:var(--mut);border:1px dashed var(--line);border-radius:8px}}
.tag{{font-size:12px;color:var(--mut)}} .notes{{color:var(--mut);margin:4px 0 10px}} .report{{margin-top:24px}}
</style></head><body><main><h1>{esc(title)}</h1><span class="verdict">{esc(v)}</span>
<h2>So sánh từng màn</h2>{''.join(rows) or '<p>Không có ảnh chụp.</p>'}
<div class="report">{md_html(md)}</div></main></body></html>"""
open(out, "w").write(page)
print(f"html: {len(pairs)} screens")
