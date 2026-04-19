#!/usr/bin/env bash
set -euo pipefail

TARGET_DATE="${TARGET_DATE:?TARGET_DATE is required}"
CONTENT_FILE="${1:?usage: send-telegram-opposing.sh <opposing-content-file>}"
CONFIG_FILE="${CC_CONNECT_CONFIG:-$HOME/.cc-connect/config.toml}"
GROUP_ID="${CODEX_GROUP_ID:-}"

# CODEX_GROUP_ID 未配置视为"不使用 codex 反方推送"，静默跳过
if [ -z "$GROUP_ID" ]; then
  echo "[daily-report] info: CODEX_GROUP_ID not set, skipping codex Telegram push" >&2
  exit 0
fi

token="$(
  awk '
    /^\[\[projects\]\]/ { inproj=0 }
    /name *= *"codex"/ { inproj=1 }
    inproj && /token *=/ { print; exit }
  ' "$CONFIG_FILE" | sed 's/.*token *= *"\([^"]*\)".*/\1/'
)"

if [ -z "$token" ]; then
  echo "[daily-report] warning: codex bot token not found" >&2
  exit 0
fi

content="$(cat "$CONTENT_FILE")"
msg="🧐 日报 ${TARGET_DATE} — Codex 反方视角:

${content}"

if [ "${#msg}" -gt 4000 ]; then
  msg="${msg:0:3900}

...（截断，完整内容见博客日报）"
fi

tmp="${RUN_DIR:-/tmp}/daily-report-tg-send.json"
curl -sS -X POST "https://api.telegram.org/bot${token}/sendMessage" \
  -d "chat_id=${GROUP_ID}" \
  --data-urlencode "text=${msg}" \
  > "$tmp" 2>&1 || true

if ! grep -q '"ok":true' "$tmp" 2>/dev/null; then
  echo "[daily-report] warning: Telegram notify to group failed, see $tmp" >&2
fi
