#!/usr/bin/env bash
set -euo pipefail

# cc-connect 运行时会自动注入 CC_PROJECT / CC_SESSION_KEY 指向当前会话；
# 如果想把通知发到固定主 DM（而非当前会话），设置 *_OVERRIDE 变量。
PROJECT="${CC_PROJECT_OVERRIDE:-${CC_PROJECT:?CC_PROJECT is required (set by cc-connect or provide manually)}}"
SESSION_KEY="${CC_SESSION_KEY_OVERRIDE:-${CC_SESSION_KEY:?CC_SESSION_KEY is required (set by cc-connect or provide manually)}}"

if [ "$#" -gt 0 ]; then
  message="$*"
else
  message="$(cat)"
fi

cc-connect send -p "$PROJECT" -s "$SESSION_KEY" -m "$message"
