"""Pick which Claude account (CLAUDE_CODE_OAUTH_TOKEN_1..3) a runner job should use.

Skip an account when it has used >= 90% of its weekly quota and the weekly reset is more than 1 day away,
or >= 95% of its 5-hour session.
Among the rest, take the preferred one if given (argv[1]), else the least-used 5-hour session (then weekly).
Quota comes from the rate-limit headers of a 1-token Haiku call. Prints the account number, or exits 1 if none.
"""
import json, os, sys, time, urllib.error, urllib.request

WEEK_PCT, WEEK_DAYS = 0.90, 1


def quota(token):
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps({
        "model": "claude-haiku-5-5", "max_tokens": 1,
        # OAuth tokens only work with the Claude Code system prompt.
        "system": "You are Claude Code, Anthropic's official CLI for Claude.", "messages": [{"role": "user", "content": "hi"}]}).encode(),
        headers={"Authorization": f"Bearer {token}", "anthropic-version": "2023-06-01",
                 "anthropic-beta": "oauth-2025-04-20", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            h = r.headers
    except urllib.error.HTTPError as e:  # 429 still carries the quota headers
        h = e.headers
    used = h.get("anthropic-ratelimit-unified-7d-utilization")
    reset = h.get("anthropic-ratelimit-unified-7d-reset")
    five = h.get("anthropic-ratelimit-unified-5h-utilization")
    return (float(used) if used else None), (int(reset) if reset else None), (float(five) if five else 0.0)


pref = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in "123" else None
ok = {}
for n in "123":
    tok = os.environ.get(f"CLAUDE_CODE_OAUTH_TOKEN_{n}")
    if not tok:
        continue
    used, reset, five = quota(tok)
    days = (reset - time.time()) / 86400 if reset else None
    # The 5-hour session limit kills a run after one turn, so a nearly full session counts as blocked too.
    blocked = (used is not None and used >= WEEK_PCT and (days is None or days > WEEK_DAYS)) or five >= 0.95 or (used or 0) >= 0.98
    print(f"account {n}: week {used if used is not None else '?'} reset in {days:.1f}d{' SKIP' if blocked else ''}"
          if days is not None else f"account {n}: week {used} reset ?{' SKIP' if blocked else ''}", file=sys.stderr)
    if not blocked:
        # Spread load by the 5-hour session first: picking by weekly use alone sent every worker to one account.
        ok[n] = (five, used if used is not None else 0.5)
if not ok:
    sys.exit(1)
print(pref if pref in ok else min(ok, key=ok.get))
