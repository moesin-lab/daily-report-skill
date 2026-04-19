#!/usr/bin/env bash
set -euo pipefail

TARGET_DATE="${TARGET_DATE:?TARGET_DATE is required}"
BLOG_DIR="${BLOG_DIR:?BLOG_DIR is required (local path to your Hexo blog checkout)}"
MD_PATH="${1:-${BLOG_DIR}/source/_posts/daily-report-${TARGET_DATE}.md}"
HTML_PATH="${2:-/tmp/dr-${TARGET_DATE}-email.html}"
TO="${DAILY_REPORT_EMAIL_TO:?DAILY_REPORT_EMAIL_TO is required (e.g. you@example.com)}"
LOG_PATH="${RUN_DIR:-/tmp}/dr-${TARGET_DATE}-mail.log"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 "$SCRIPT_DIR/render-email.py" --markdown "$MD_PATH" --output "$HTML_PATH" >/dev/null

set +e
mails send \
  --to "$TO" \
  --subject "日报 ${TARGET_DATE}" \
  --html "$(cat "$HTML_PATH")" \
  --attach "$MD_PATH" 2>&1 | tee "$LOG_PATH"
code=${PIPESTATUS[0]}
set -e

if [ "$code" -eq 0 ] && grep -q "${DR_MAIL_SUCCESS_GREP:-Sent via mails.dev}" "$LOG_PATH"; then
  echo "已投递到 ${TO}"
  exit 0
fi

echo "邮件投递失败：$(tail -3 "$LOG_PATH" | tr '\n' ' ')" >&2
exit 1
