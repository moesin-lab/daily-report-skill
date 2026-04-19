#!/usr/bin/env bash
set -euo pipefail

TARGET_DATE="${TARGET_DATE:?TARGET_DATE is required}"
REPO="${DAILY_REPORT_REPO:?DAILY_REPORT_REPO is required (e.g. your-github-login/your-blog-repo)}"

gh api "repos/${REPO}/contents/source/_posts/daily-report-${TARGET_DATE}.md" --jq '.name' 2>&1
