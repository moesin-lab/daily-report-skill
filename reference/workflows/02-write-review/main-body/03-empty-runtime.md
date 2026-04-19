## 空 session 行为

`$SESSION_CARDS_FILE` 为空时：

- 概览写“当天无对话会话”。
- 省略主轴行。
- 省略 `## 今日工作`。
- GitHub 活动、总结照常写。
- 沙盒外活动按 `$OUTSIDE_NOTES_FILE` 判定，有内容照写，空则省略。
- 运行时问题有则写，无则省略。

## 运行时问题

记录本次日报生成过程中的基础设施问题、降级和工具失败。

格式：

- 章节名：`## 运行时问题`
- 每条 1 行 bullet，≤ 60 字。
- 无问题时整节省略。

来源：

- `$RUN_DIR/runtime-issues.txt`。
- `$RUN_DIR/filtered-sessions.json` 中非常规过滤原因，如 `subagents_path_leak`。
- `$RUN_DIR/facet-*.json` 中非空 `runtime_warning`。
