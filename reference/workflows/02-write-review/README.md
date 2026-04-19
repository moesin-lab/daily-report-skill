# 02-write-review

## 第 2.0 步到第 2.6 步

输入：`$SESSION_CARDS_FILE`、`$GITHUB_EVENTS_FILE`、`$OUTSIDE_NOTES_FILE`、`$TOKEN_STATS`、运行时问题记录。主 agent 禁止回读 raw jsonl。

## 调度边界

所有 Claude 子 agent 均使用 `subagent_type: general-purpose`，模型按任务指定：

- Opus：写作、辨析、候选生成、最终拼装。
- Haiku：隐私审查、全文复审、候选验证、临时脚本执行。

临时脚本子 agent 只运行脚本、读取产物并回报摘要，不承担写作或判断。

按顺序执行：

1. 调度 Opus 写作子 agent 读取并执行 `00-main-body.md`，回报 `$MAIN_BODY`。
2. 读取 `01-privacy-first-pass.md` 并调度 Haiku 隐私审查子 agent。
3. 调度 Haiku 临时脚本子 agent 读取并执行 `02-opposing-codex.md`，回报 `$OPPOSING_OK` 和产物路径。
4. `$OPPOSING_OK == 1` 时读取 `03-neutral-analysis.md` 并调度 Opus 中立辨析子 agent。
5. 读取 `04-candidates.md` 并调度 Opus generator 与 Haiku validator；组装脚本可交给 Haiku 临时脚本子 agent。
6. 调度 Opus 写作子 agent 读取并执行 `05-final-assembly.md`，回报日报 Markdown 路径。
7. 读取 `06-privacy-final-pass.md` 并调度 Haiku 全文隐私复审子 agent。
8. 读取 `07-tldr.md` 并按重试循环调度 Opus TL;DR 生成子 agent，校验 + 插入由 `scripts/review/insert-tldr.py` 兜底；失败不阻塞发布。

阶段产物：

- `$MAIN_BODY`
- `$OPPOSING_CONTENT` / `$OPPOSING_OK`
- `$ANALYSIS_CONTENT`
- `$REFLECTION_SECTION`
- `$SUGGESTIONS_SECTION`
- `/tmp/dr-$TARGET_DATE-memory-candidates.json`
- `$BLOG_DIR/source/_posts/daily-report-$TARGET_DATE.md`

边界：

- 第 2.0 步只写主体，不生成思考、建议、Token 统计、Session 指标或附录。
- 只有第 2.2 步使用 Codex。
- 第 2.6 步通过后才能进入第 2.7 步；第 2.7 步失败仍可发布，只是缺 TL;DR 节。
