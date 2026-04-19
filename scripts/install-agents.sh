#!/usr/bin/env bash
# 把 skill 捆绑的 session-reader / session-merger agent 定义装到
# ~/.claude/agents/，供 Claude Code 主 agent 用 Agent 工具调用时发现。
#
# 默认用 symlink，改动 repo 内 agents/ 下文件会立即生效；
# 传 --copy 改为 copy 模式（跨文件系统 / 不想被 submodule 更新影响时用）。
set -euo pipefail

MODE="symlink"
if [ "${1:-}" = "--copy" ]; then
  MODE="copy"
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$REPO_ROOT/agents"
DEST_DIR="$HOME/.claude/agents"

if [ ! -d "$SRC_DIR" ]; then
  echo "[install-agents] error: $SRC_DIR not found" >&2
  exit 1
fi

mkdir -p "$DEST_DIR"

installed=0
for src in "$SRC_DIR"/*.md; do
  [ -e "$src" ] || continue
  name="$(basename "$src")"
  dest="$DEST_DIR/$name"

  if [ -e "$dest" ] || [ -L "$dest" ]; then
    if cmp -s "$dest" "$src" 2>/dev/null; then
      continue  # content identical (symlink or copy), no action needed
    fi
    echo "[install-agents] warning: $dest exists with different content"
    echo "  skill source: $src"
    echo "  existing: $(readlink -f "$dest" 2>/dev/null || echo "$dest")"
    echo "  skipping; diff them manually, then remove the existing file and rerun to overwrite"
    continue
  fi

  if [ "$MODE" = "symlink" ]; then
    ln -s "$src" "$dest"
  else
    cp "$src" "$dest"
  fi
  installed=$((installed + 1))
done

echo "[install-agents] mode=$MODE installed=$installed into $DEST_DIR"
