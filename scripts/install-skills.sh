#!/usr/bin/env bash
# 把 skill 捆绑的顶层 skill 定义（如 abagent）装到 ~/.claude/skills/，
# 供 Claude Code 主 agent 在 skill 列表里发现。
#
# 默认用 symlink，改动 repo 内 skills/ 下文件会立即生效；
# 传 --copy 改为 copy 模式（跨文件系统 / 不想被 submodule 更新影响时用）。
set -euo pipefail

MODE="symlink"
if [ "${1:-}" = "--copy" ]; then
  MODE="copy"
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$REPO_ROOT/skills"
DEST_DIR="$HOME/.claude/skills"

if [ ! -d "$SRC_DIR" ]; then
  echo "[install-skills] no $SRC_DIR; nothing to install"
  exit 0
fi

mkdir -p "$DEST_DIR"

installed=0
for src_skill in "$SRC_DIR"/*/; do
  [ -d "$src_skill" ] || continue
  src_skill="${src_skill%/}"
  name="$(basename "$src_skill")"
  dest="$DEST_DIR/$name"

  if [ -L "$dest" ]; then
    target="$(readlink "$dest")"
    if [ "$target" = "$src_skill" ]; then
      continue
    fi
    echo "[install-skills] warning: $dest is a symlink pointing elsewhere ($target); skipping"
    continue
  fi

  if [ -e "$dest" ]; then
    echo "[install-skills] warning: $dest exists (not a symlink); skipping"
    echo "  skill source: $src_skill"
    echo "  remove or back up $dest manually, then rerun to overwrite"
    continue
  fi

  if [ "$MODE" = "symlink" ]; then
    ln -s "$src_skill" "$dest"
  else
    cp -r "$src_skill" "$dest"
  fi
  installed=$((installed + 1))
done

echo "[install-skills] mode=$MODE installed=$installed into $DEST_DIR"
