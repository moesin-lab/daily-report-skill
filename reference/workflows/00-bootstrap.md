# 00-bootstrap

## 第零步：前置收集

所有查询使用 epoch 窗口 `[WINDOW_START, WINDOW_END)`；展示、文件名和通知使用 `$TARGET_DATE`。

执行唯一入口：

```bash
eval "$(python3 ~/.claude/skills/daily-report/scripts/bootstrap.py --args "$调用方传来的 args")"
```

脚本输出环境变量：

- `$BRANCH`：`epoch` / `ymd` / `default`
- `$WINDOW_START` / `$WINDOW_END`
- `$WINDOW_START_ISO` / `$WINDOW_END_ISO`
- `$TARGET_DATE`
- `$RUN_DIR`
- `$SESSION_FILES_FILE`
- `$TOKEN_STATS_FILE`
- `$GITHUB_EVENTS_FILE`
- `$RUNTIME_ISSUES_FILE`
- `$BOOTSTRAP_SUMMARY_FILE`
- `$BOOTSTRAP_ENV_FILE`
- `$CURRENT_BOOTSTRAP_ENV_FILE`
- `$CURRENT_BOOTSTRAP_SUMMARY_FILE`
- `$SESSION_CARDS_FILE`（固定为 `$RUN_DIR/session-cards.md`）
- `$OUTSIDE_NOTES_FILE`（固定为 `$RUN_DIR/outside-notes.md`）
- `$BLOG_DIR`（来自 skill `.env`；缺省则不导出，publish 阶段脚本自带校验）
- `$BLOG_FACETS_ROOT`（来自 skill `.env`；未显式设置时默认为 `$BLOG_DIR/facets/facets`）
- `$TOKEN_STATS`

脚本产物：

- `$RUN_DIR/session-files.txt`
- `$RUN_DIR/token-stats.json`
- `$RUN_DIR/github-events.jsonl`
- `$RUN_DIR/bootstrap-summary.json`
- `$RUN_DIR/bootstrap.env`
- `/tmp/daily-report/current.env`
- `/tmp/daily-report/current-summary.json`
- `$RUN_DIR/runtime-issues.txt`（仅出现可降级问题时）

约束：

- 不在后续步骤重新解析 args。
- 不手写 `date` 逻辑重算窗口。
- 不重新扫描主 session 列表，后续只使用 `$SESSION_FILES_FILE`。
- 不假设 `eval` 后的环境变量能跨 Bash tool 调用持久化；后续独立 Bash 调用必须先 `source /tmp/daily-report/current.env`，或使用 bootstrap stdout 中的 `$BOOTSTRAP_ENV_FILE` 显式 source。
- `/tmp/daily-report/current.env` 是当前日报运行的固定指针文件，里面包含 `$RUN_DIR` 和 `$BOOTSTRAP_ENV_FILE`。
- 如果 stderr 自检日志里的 `$BRANCH` 与调用方预期不符，暂停确认。
- GitHub 活动是补充材料；采集失败时脚本写空 `$GITHUB_EVENTS_FILE` 并记录 runtime issue，不阻断日报。
- 主 agent 不读取 raw jsonl；session 内容过滤、metadata 和 facet cache 由 session pipeline 处理。
