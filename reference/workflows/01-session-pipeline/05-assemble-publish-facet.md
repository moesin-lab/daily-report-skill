### 步骤 f：组装卡片并发布 facet

组装 Markdown 卡片：

```bash
python3 ~/.claude/skills/daily-report/scripts/session/assemble-session-cards.py
export SESSION_CARDS_FILE="$RUN_DIR/session-cards.md"
```

发布 facet JSON 到 submodule：

```bash
RUN_DIR="$RUN_DIR" \
TARGET_DATE="$TARGET_DATE" \
BLOG_FACETS_ROOT=$BLOG_FACETS_ROOT \
python3 ~/.claude/skills/daily-report/scripts/session/publish-facet.py
```

第 3.1 步负责 commit / push `$BLOG_DIR/facets`。

可选 sanity check：

- 如果 `merged-<gid>.md` 明显是无关 session 拼接，删除该 merged card，移除对应 merge group，重跑本步骤。
- 不再基于 merged card 发起新一轮聚类。

`$SESSION_CARDS_FILE` 是第 2.0 步唯一会话输入。
