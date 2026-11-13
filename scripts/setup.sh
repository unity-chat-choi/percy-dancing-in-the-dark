#!/bin/bash
# Load every secret this repo's workflows need from local files into GitHub Actions secrets.
# Usage: scripts/setup.sh [owner/repo]   (needs: gh logged in with repo scope)
# Sources (copy them to a new machine first, chmod 600, never commit them):
#   ~/.config/cutcut/uniscore-runner-secrets.env   GITLAB_*, JIRA_*, FIGMA_TOKEN, CLAUDE_CODE_OAUTH_TOKEN_1..3, TG_*
#   ~/.claude/squad-webhooks.json                  {"<space>": "<Google Chat webhook>"}
#   ~/.claude/squad-members.json                   {"<alias>": "<Chat user id>"}
#   ~/.claude/jira-members.json                    {"<alias>": "<Jira accountId>"}
#   ~/.config/cutcut/google-oauth.json             {client_id, client_secret, refresh_token} (Sheets scope)
set -euo pipefail
REPO="${1:-unity-chat-choi/percy-dancing-in-the-dark}"
ENV_FILE="${RUNNER_ENV:-$HOME/.config/cutcut/uniscore-runner-secrets.env}"

gh auth status >/dev/null 2>&1 || { echo "Run: gh auth login" >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE" >&2; exit 1; }
set -a; . "$ENV_FILE"; set +a

for k in GITLAB_TOKEN GITLAB_PROJECT JIRA_URL JIRA_EMAIL JIRA_API_TOKEN FIGMA_TOKEN \
         CLAUDE_CODE_OAUTH_TOKEN_1 CLAUDE_CODE_OAUTH_TOKEN_2 CLAUDE_CODE_OAUTH_TOKEN_3 \
         TG_BOT_TOKEN_1 TG_TICKET_BOT_TOKEN TG_SQUAD_TOPICS TG_RETRO_TOPIC TASKS_PAT TASKS_REPO DAILY_SHEET_ID DAILY_ROW_NAME TG_CHAT_ID TG_THREAD_ID TG_NOTIFY_CHAT_ID TG_NOTIFY_THREAD_ID; do
  v="${!k:-}"
  if [ -z "$v" ]; then echo "skip  $k (empty)"; continue; fi
  printf %s "$v" | gh secret set "$k" -R "$REPO" && echo "set   $k"
done

for pair in CHAT_WEBHOOKS:"$HOME/.claude/squad-webhooks.json" CHAT_MEMBERS:"$HOME/.claude/squad-members.json" \
            GOOGLE_OAUTH:"$HOME/.config/cutcut/google-oauth.json" JIRA_MEMBERS:"$HOME/.claude/jira-members.json"; do
  k="${pair%%:*}"; f="${pair#*:}"
  if [ -f "$f" ]; then gh secret set "$k" -R "$REPO" < "$f" && echo "set   $k"; else echo "skip  $k ($f missing)"; fi
done

gh secret list -R "$REPO"

# Mac half of the sprint retro (AI cost + lessons), Friday 17:05.
if [ "$(uname)" = Darwin ]; then
  repo="$(cd "$(dirname "$0")/.." && pwd)"
  plist="$HOME/Library/LaunchAgents/com.percy.retro.plist"
  sed "s#__REPO__#$repo#" "$repo/mac/com.percy.retro.plist" > "$plist"
  launchctl bootout "gui/$(id -u)" "$plist" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$plist" && echo "launchd com.percy.retro ok"
  # Q&A bot (topic 💬 Hỏi đáp), always on. Needs `claude` logged in and ~/uniscore-mobile cloned.
  plist="$HOME/Library/LaunchAgents/com.percy.ask-bot.plist"
  sed -e "s#__REPO__#$repo#" -e "s#__HOME__#$HOME#" "$repo/mac/com.percy.ask-bot.plist" > "$plist"
  launchctl bootout "gui/$(id -u)" "$plist" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$plist" && echo "launchd com.percy.ask-bot ok"
fi
