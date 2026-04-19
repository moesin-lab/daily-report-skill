## 第 1 步概览

执行结构：

1. 每个 kept session 派一个 `session-reader`，产出 phase1 卡片和 facet JSON。
2. 脚本读取 phase1 卡片，按结构化锚点生成合并组。
3. 对明确同主题的多 session 组派 `session-merger`，产出合并卡片。
4. 组装最终 `$SESSION_CARDS_FILE`。

约束：

- 合并最多一轮，不递归。
- 子代理负责读 raw jsonl；主 agent 只消费卡片、metadata、facet 和脚本产物。
- 合并卡片是重评，不是拼接。
