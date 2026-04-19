#!/usr/bin/env bash
set -euo pipefail

WINDOW_START_ISO="${WINDOW_START_ISO:?WINDOW_START_ISO is required}"
WINDOW_END_ISO="${WINDOW_END_ISO:?WINDOW_END_ISO is required}"
GITHUB_USER="${GITHUB_USER:?GITHUB_USER is required (your GitHub login)}"

gh api "users/${GITHUB_USER}/events" --jq \
  ".[] | select(.created_at >= \"${WINDOW_START_ISO}\" and .created_at < \"${WINDOW_END_ISO}\")"
