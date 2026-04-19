#!/usr/bin/env bash
set -euo pipefail

TARGET_DATE="${TARGET_DATE:?TARGET_DATE is required}"
BLOG_DIR="${BLOG_DIR:?BLOG_DIR is required (local path to your Hexo blog checkout)}"
POST_PATH="${1:-source/_posts/daily-report-${TARGET_DATE}.md}"

cd "$BLOG_DIR"
git pull origin main

yyyy="${TARGET_DATE%%-*}"
rest="${TARGET_DATE#*-}"
mm="${rest%%-*}"
dd="${TARGET_DATE##*-}"

git add "$POST_PATH"
git commit -m "docs: 日报 ${TARGET_DATE}"
git push origin main
