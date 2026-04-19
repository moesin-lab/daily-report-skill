## 第 2.0 步范围

第 2.0 步只生成 `$MAIN_BODY`，包含：

- 概览
- 今日工作
- GitHub 活动
- 沙盒外活动（条件）
- 总结
- 运行时问题（条件）

不生成：

- 思考
- 建议
- Token 统计
- Session 指标
- 审议过程附录

输入：

- `$SESSION_CARDS_FILE`
- `$GITHUB_EVENTS_FILE`
- `$OUTSIDE_NOTES_FILE`（可为空或只含 `<!-- empty -->`）
- `$RUN_DIR/runtime-issues.txt`（可不存在）

主 agent 禁止回读 raw jsonl。
