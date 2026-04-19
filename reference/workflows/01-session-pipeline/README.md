# 01-session-pipeline

## 第 1 步：Session 拆分阅读

本阶段输入窗口变量和 session 文件列表，输出 `$SESSION_CARDS_FILE` 与 facet JSON。完成后主 agent 不再读 raw jsonl。

## 调度边界

`session-reader` / `session-merger` 只能由主流程调度；临时子 agent 只运行脚本、读取产物并回报摘要，不读 raw jsonl。

按顺序执行：

1. 读取 `00-overview.md` 和 `99-failure-rules.md`。
2. 调度临时子 agent 读取并执行 `01-prepare-run.md`。
3. 读取 `02-session-reader.md` 并调度 `session-reader`。
4. 调度临时子 agent 读取并执行 `03-lint-retry-fallback.md`；如需重派，只回报失败 sid/errors，再重派 `session-reader`。
5. 调度临时子 agent 读取并执行 `04-merge.md` 的聚类；如有 merge group，调度 `session-merger`。
6. 调度临时子 agent 读取并执行 `05-assemble-publish-facet.md`，回报 `$SESSION_CARDS_FILE`。

快速出口：`kept-sessions.txt` 为空时跳过 reader / lint / merge，直接组装空 `$SESSION_CARDS_FILE`。

阶段产物：

- `$RUN_DIR/session-cards.md`
- `$SESSION_CARDS_FILE="$RUN_DIR/session-cards.md"`
- `$RUN_DIR/facet-*.json`
- `$BLOG_FACETS_ROOT/YYYY/MM/DD/<sid>.json`
- `$RUN_DIR/merge-groups.json`
