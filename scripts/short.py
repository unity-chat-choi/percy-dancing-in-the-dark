"""Shorten a Markdown report for Telegram: title, verdict line and at most a few bullets. Usage: short.py <in.md> <out.md> [max_bullets]"""
import re, sys

src, dst = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 4
lines = [l.rstrip() for l in open(src) if l.strip()]
keep, bullets = [], 0
for l in lines:
    if re.match(r"^#{1,2}\s*Kết quả", l) or re.match(r"^\*\*(iOS|Android)", l):
        keep.append(re.sub(r"^#+\s*", "", l)); continue
    if l.lstrip().startswith(("- ", "• ", "* ")) and bullets < n:
        keep.append("• " + re.sub(r"^\s*[-•*]\s*", "", l)[:140]); bullets += 1
open(dst, "w").write("\n".join(keep[: n + 3]) + "\n")
