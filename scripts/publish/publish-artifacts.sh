#!/usr/bin/env bash
set -euo pipefail

# Publish all daily report artifacts to the facets submodule repo.
# Handles: facets (already written by publish-facet.py), cards, reviews, candidates.
# Commits and pushes inside the submodule, then updates submodule ref in blog repo.

TARGET_DATE="${TARGET_DATE:?TARGET_DATE is required}"
RUN_DIR="${RUN_DIR:?RUN_DIR is required}"
BLOG_DIR="${BLOG_DIR:?BLOG_DIR is required (local path to your Hexo blog checkout)}"
SUBMODULE_DIR="${BLOG_DIR}/facets"

if [ ! -d "$SUBMODULE_DIR/.git" ] && [ ! -f "$SUBMODULE_DIR/.git" ]; then
  echo "[publish-artifacts] error: $SUBMODULE_DIR is not a git submodule" >&2
  exit 1
fi

cd "$SUBMODULE_DIR"

# cards
if [ -f "$RUN_DIR/session-cards.md" ]; then
  mkdir -p cards
  cp "$RUN_DIR/session-cards.md" "cards/${TARGET_DATE}.md"
fi

# reviews
mkdir -p reviews
[ -f "$RUN_DIR/opposing.txt" ] && cp "$RUN_DIR/opposing.txt" "reviews/${TARGET_DATE}-opposing.txt"
[ -f "$RUN_DIR/analysis.txt" ] && cp "$RUN_DIR/analysis.txt" "reviews/${TARGET_DATE}-analysis.txt"

# candidates
mkdir -p candidates
[ -f "/tmp/dr-${TARGET_DATE}-candidates.json" ] && cp "/tmp/dr-${TARGET_DATE}-candidates.json" "candidates/${TARGET_DATE}-candidates.json"
[ -f "$RUN_DIR/validations.jsonl" ] && cp "$RUN_DIR/validations.jsonl" "candidates/${TARGET_DATE}-validations.jsonl"

# commit and push inside submodule
git add -A
if git diff --cached --quiet; then
  echo "[publish-artifacts] nothing to commit in submodule"
else
  git commit -m "docs: artifacts ${TARGET_DATE}"
  git push origin main
  echo "[publish-artifacts] pushed artifacts for ${TARGET_DATE}"
fi

# update submodule ref in blog repo
cd "$BLOG_DIR"
git add facets
if git diff --cached --quiet; then
  echo "[publish-artifacts] submodule ref unchanged"
else
  git commit -m "chore: update facets submodule for ${TARGET_DATE}"
  git push origin main
  echo "[publish-artifacts] updated submodule ref"
fi
