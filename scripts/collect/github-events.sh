#!/usr/bin/env bash
set -euo pipefail

# 暂时禁用：sentixA 封号后 gh CLI 卸载，GitHub user events feed 没有 mcp__github__* 端点对应。
# 重新启用前考虑用 mcp__github__search_pull_requests / search_issues 在主 agent 上下文里采集。
exit 0
