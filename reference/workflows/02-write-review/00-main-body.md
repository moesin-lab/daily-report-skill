## 第 2.0 步：撰写日报主体

第 2.0 步调用 `general-purpose` 子 agent，模型指定 Opus，只生成 `$MAIN_BODY`：概览、今日工作、GitHub 活动、总结、运行时问题（条件）。

按顺序读取：

1. `reference/workflows/02-write-review/main-body/00-scope-inputs.md`
2. `reference/workflows/02-write-review/main-body/01-audience-axis.md`
3. `$SESSION_CARDS_FILE` 非空时读取 `reference/workflows/02-write-review/main-body/02-work-section.md`
4. `reference/workflows/02-write-review/main-body/03-empty-runtime.md`
5. `reference/workflows/02-write-review/main-body/04-boundaries-style.md`
6. `reference/workflows/02-write-review/main-body/05-template-fill.md`

边界：

- 本阶段不生成思考、建议、Token 统计、Session 指标、审议过程附录。
- 主 agent 禁止读 raw jsonl。
- 今日工作只基于 `$SESSION_CARDS_FILE`。
