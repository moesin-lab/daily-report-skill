#!/usr/bin/env bash
# 一键启用仓库自带 git hooks（hooks/ 下）。
# clone 后第一次跑一下即可；重跑无副作用。
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

git config core.hooksPath hooks
chmod +x hooks/pre-commit
echo "[install-hooks] core.hooksPath=hooks; 现在 git 会执行 hooks/pre-commit"
