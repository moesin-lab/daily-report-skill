## 第 2.3 步：中立辨析

仅在 `$OPPOSING_OK == 1` 时执行。

调用 Claude sub-agent：

- `subagent_type: general-purpose`
- 模型指定 Opus，不降级。
- 禁止调用 `codex-review`、`codex exec` 或 `cc-connect relay`。

读取 `reference/prompts/neutral-analysis.md`，替换：

- `{{WINDOW_START}}` / `{{WINDOW_END}}`
- `{{WINDOW_START_ISO}}` / `{{WINDOW_END_ISO}}`
- `{{TARGET_DATE}}`
- `{{PRIMARY_REFLECTION}}`
- `{{OPPOSING_VIEW}}`

结果写入 `$ANALYSIS_CONTENT`，不要直接写入日报正文；第 2.4 和第 2.5 步会消费它。
