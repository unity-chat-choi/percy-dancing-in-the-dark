"""Q&A bot: Percy asks about the uniscore project in the "💬 Hỏi đáp" topic, Claude Code answers read-only.

Runs on a Mac (launchd keeps it alive). Two Macs can run it at once: Telegram lets only one long-poll a bot,
the other gets 409 Conflict and waits, so it takes over when the first goes offline.
- New message in the topic = new question. Reply to a bot answer = follow-up in the same Claude session.
- "/opus <question>" uses Opus; default Sonnet.
Reads ~/.config/cutcut/uniscore-runner-secrets.env (TG_ASK_BOT_TOKEN, TG_NOTIFY_CHAT_ID, TG_QA_TOPIC).
"""
import json, os, re, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

HOME = os.path.expanduser("~")
ENV = {k: v.strip().strip("'\"") for k, v in (l.split("=", 1) for l in open(
    f"{HOME}/.config/cutcut/uniscore-runner-secrets.env").read().splitlines() if "=" in l and not l.startswith("#"))}
API = f"https://api.telegram.org/bot{ENV['TG_ASK_BOT_TOKEN']}"
CHAT, TOPIC = str(ENV["TG_NOTIFY_CHAT_ID"]), int(ENV["TG_QA_TOPIC"])
REPO = os.environ.get("ASK_REPO", f"{HOME}/uniscore-mobile")
STATE = f"{HOME}/.config/cutcut/ask-bot-sessions.json"  # bot message id -> Claude session id
CLAUDE = os.environ.get("CLAUDE_BIN", f"{HOME}/.local/bin/claude")
# Read-only: no edits, no network, no git writes.
TOOLS = ["Read", "Grep", "Glob", "Bash(git log:*)", "Bash(git show:*)", "Bash(git grep:*)", "Bash(git diff:*)",
         "Bash(git branch:*)", "Bash(git status:*)", "Bash(ls:*)"]
RULES = ("Bạn trả lời câu hỏi của Percy về dự án trong repo hiện tại qua Telegram. Trả lời tiếng Việt, ngắn gọn, "
         "đi thẳng vào ý, dẫn file:dòng khi có. Chỉ đọc code/tài liệu; không sửa file, không chạy lệnh ghi. "
         "Không in secret. Không dùng bảng markdown (Telegram không hiển thị), dùng gạch đầu dòng.")


def call(method, **params):
    data = urllib.parse.urlencode({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in params.items()}).encode()
    with urllib.request.urlopen(f"{API}/{method}", data=data, timeout=70) as r:
        return json.load(r)["result"]


def send(text, reply_to):
    mid = None
    for i in range(0, max(len(text), 1), 3900):  # Telegram caps a message at 4096 chars
        mid = call("sendMessage", chat_id=CHAT, message_thread_id=TOPIC, text=text[i:i + 3900] or "…",
                   reply_parameters={"message_id": reply_to}, disable_web_page_preview="true")["message_id"]
    return mid


def load():
    try:
        return json.load(open(STATE))
    except (OSError, ValueError):
        return {}


def save(s):
    s = dict(list(s.items())[-500:])
    with open(STATE, "w") as f:
        json.dump(s, f)
    os.chmod(STATE, 0o600)
    return s


def ask(question, model, resume):
    cmd = [CLAUDE, "-p", question, "--model", model, "--output-format", "json", "--append-system-prompt", RULES,
           "--allowedTools", *TOOLS, "--disallowedTools", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch"]
    if resume:
        cmd += ["--resume", resume]
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=900)
    out = json.loads(p.stdout or "{}")
    return out.get("result") or f"Lỗi khi chạy Claude (exit {p.returncode}).", out.get("session_id")


def main():
    sessions, offset = load(), None
    print("ask-bot up", flush=True)
    while True:
        try:
            ups = call("getUpdates", offset=offset or 0, timeout=50, allowed_updates=["message"])
        except urllib.error.HTTPError as e:
            if e.code == 409:  # another Mac is polling; take over when it stops
                time.sleep(60)
                continue
            time.sleep(10)
            continue
        except Exception:
            time.sleep(10)
            continue
        for u in ups:
            offset = u["update_id"] + 1
            m = u.get("message") or {}
            if str(m.get("chat", {}).get("id")) != CHAT or m.get("message_thread_id") != TOPIC:
                continue
            if m.get("from", {}).get("is_bot") or not m.get("text"):
                continue
            text, model = m["text"].strip(), "sonnet"
            hit = re.match(r"^/opus(@\w+)?\s+", text)
            if hit:
                text, model = text[hit.end():], "opus"
            parent = (m.get("reply_to_message") or {}).get("message_id")
            resume = sessions.get(str(parent)) if parent else None
            call("sendChatAction", chat_id=CHAT, message_thread_id=TOPIC, action="typing")
            try:
                answer, sid = ask(text, model, resume)
            except subprocess.TimeoutExpired:
                answer, sid = "Quá 15 phút chưa xong, hỏi hẹp lại giúp mình nha.", None
            mid = send(answer, m["message_id"])
            if sid and mid:
                sessions[str(mid)] = sid
                sessions = save(sessions)


if __name__ == "__main__":
    sys.exit(main())
