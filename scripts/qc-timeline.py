"""Where does a QC run spend its time? Reads `claude -p --output-format stream-json --verbose` on stdin.

Writes <ctx>/qc.json (the final result event, same as --output-format json) and <ctx>/qc-timeline.txt:
seconds per category (maestro, device, image reads, API calls, other tools, model thinking) + the slowest calls.
Written again after every tool result, so a run killed by its time cap still leaves the timeline.
Usage: claude ... --output-format stream-json --verbose | python3 -u qc-timeline.py <ctx dir>
"""
import json, os, sys, time

ctx = sys.argv[1]
start = last = time.time()
pending = {}            # tool_use_id -> (t, category, label)
cat_s, calls = {}, []    # seconds per category; (seconds, category, label)


def category(name, inp):
    if name == "Bash":
        c = (inp.get("command") or "").strip()
        if "maestro" in c:
            return "maestro"
        if c.startswith(("xcrun", "adb")) or " simctl " in c:
            return "device"
        if c.startswith(("python3", "node")) and ("http" in c or "fetch" in c or "urlopen" in c):
            return "api"
        return "bash other"
    if name == "Read":
        return "read image" if (inp.get("file_path") or "").lower().endswith((".png", ".jpg", ".jpeg")) else "read text"
    return name.lower()


def label(name, inp):
    s = inp.get("command") or inp.get("file_path") or inp.get("pattern") or ""
    return f"{name}: {' '.join(str(s).split())[:110]}"


def dump():
    total = time.time() - start
    lines = [f"total {total / 60:.1f} min, {len(calls)} tool calls"]
    for c, s in sorted(cat_s.items(), key=lambda x: -x[1]):
        lines.append(f"{c:12} {s / 60:5.1f} min  {100 * s / max(total, 1):3.0f}%")
    lines.append("\nslowest calls:")
    lines += [f"{s:5.0f}s  {c:11} {l}" for s, c, l in sorted(calls, reverse=True)[:15]]
    open(os.path.join(ctx, "qc-timeline.txt"), "w").write("\n".join(lines) + "\n")


for raw in sys.stdin:
    try:
        ev = json.loads(raw)
    except ValueError:
        continue
    now = time.time()
    if ev.get("type") == "assistant":
        # Time since the previous event that ended in a model turn = thinking/writing.
        cat_s["model"] = cat_s.get("model", 0) + (now - last)
        for b in ev.get("message", {}).get("content") or []:
            if b.get("type") == "tool_use":
                inp = b.get("input") or {}
                pending[b["id"]] = (now, category(b.get("name", ""), inp), label(b.get("name", ""), inp))
    elif ev.get("type") == "user":
        for b in ev.get("message", {}).get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
                t, c, l = pending.pop(b["tool_use_id"])
                cat_s[c] = cat_s.get(c, 0) + (now - t)
                calls.append((now - t, c, l))
        dump()
    elif ev.get("type") == "result":
        open(os.path.join(ctx, "qc.json"), "w").write(json.dumps(ev))
    last = now
dump()
