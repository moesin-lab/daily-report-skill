### 步骤 0：准备 run 目录

```bash
source /tmp/daily-report/current.env
eval "$(python3 ~/.claude/skills/daily-report/scripts/session/prepare-session-run.py \
  --window-start "$WINDOW_START" \
  --window-end "$WINDOW_END" \
  --window-start-iso "$WINDOW_START_ISO" \
  --window-end-iso "$WINDOW_END_ISO" \
  --target-date "$TARGET_DATE" \
  --run-dir "$RUN_DIR" \
  --session-files "$SESSION_FILES_FILE")"
```

脚本产物：

- `$RUN_DIR/session-files.txt`（来自 bootstrap）
- `$RUN_DIR/kept-sessions.txt`
- `$RUN_DIR/filtered-sessions.json`
- `$RUN_DIR/metadata-<sid>.json`
- `$RUN_DIR/facet-<sid>.json`（缓存命中时）

规则：

- subagents 目录下的 jsonl 不进入主 session 列表。
- 本步骤不重新扫描 session，只消费 `$SESSION_FILES_FILE`。
- `kept-sessions.txt` 为空时，跳过 reader / lint / merge，进入步骤 f。
- metadata 始终由脚本生成，作为 `session-reader` 输入。
- facet 缓存只减少 facet 重写；phase1 Markdown 卡片仍由 `session-reader` 生成。
