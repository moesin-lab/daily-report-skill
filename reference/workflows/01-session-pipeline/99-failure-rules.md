### 失败降级

| 故障 | 处理 |
|------|------|
| `session-reader` 缺 md / facet | `fallback-session-artifacts.py --ensure-all` 补最小合法文件 |
| lint 重派后仍失败 | `fallback-session-artifacts.py --from-lint-report` 覆盖失败模板 |
| `session-merger` 缺文件或空文件 | 跳过 merged card，回退 phase1 |
| merged card 不自洽 | 删除 merged card，重跑步骤 f |
| 无 kept session | 产出空 `session-cards.md` |

### 硬约束

- 合并不递归。
- 聚类宁紧勿松。
- 所有中间产物写入 `$RUN_DIR`。
- 子代理不写日报正文。
- 子代理不硬凑认知增量。
