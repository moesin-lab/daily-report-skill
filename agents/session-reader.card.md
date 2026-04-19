## session <SESSION_ID>

- **工作类型**: <修Bug | 新功能 | 治理 | 调研 | 工具 | 其他>
- **状态**: <已交付 | 在分支 | 调研中 | 阻塞 | 无需交付>
- **聚类锚点**:
  - repo: `<仓库名，如 project-a / project-b / docs；没有就填 null>`
  - branch_or_pr: `<分支名或 PR 号；没有就填 null>`
  - issue_or_bug: `<issue 号或可识别 bug 签名；没有就填 null>`
  - files:
    - `<涉及的关键文件路径 1>`
    - `<涉及的关键文件路径 2>`
  - target_object: `<本 session 操作的主对象，如 readLoop watchdog；没有就填 null>`
- **关联事件**: <自由文本关键词补充聚类锚点覆盖不到的线索；没有就写「无」>

### 事件摘要

<3-5 行中文段落，客观描述本 session 做了什么、卡在哪、怎么解的>

### 认知增量

<本 session 的"判断变化"或"新约束发现"。**是什么**：判断从 A 变成 B / 发现了一条原先不知道的约束或规律。**不是什么**：动作描述（"完成了 X"/"学会了 X"）是执行事实，不是认知。只是熟练执行没有新认知就写「无」。详见 session-reader.md 的「字段填写纪律」段>

### 残留问题

<未验证参数 / 未补日志 / 未合 PR / 未修 bug。没有就写「无」。**此字段是未来 action 入口，半年后回看时优先级高于认知 —— 有残留的 session 不会被合并到板块末尾，会单独成行**>

<!--
占位符纪律：
- <SESSION_ID> = SESSION_FILE basename 去掉 .jsonl 后缀
- 三个 H3 字段是中文散文，标点和引号随便用，不存在 JSON 转义问题
- 聚类锚点字段用反引号包值便于主 agent 识别；null 就写裸字 null
- files 子列表最多 5 条；没有文件时保留 files: 行、下面写单项 `- (无)`
- 输出本身是纯 Markdown，不要外层代码块、不要前后解释

认知增量正反例（参考 session-reader.md 详细说明）：
- 「完成了 PR #38 的测试补强」 → 执行事实，不是认知，写「无」
- 「学会了用 DOMPurify」 → 执行事实，不是认知，写「无」
- 「发现 DOMPurify 默认保留 data-* / aria-* 属性，不需额外 whitelist」 → 认知（新约束）
- 「发现 subagent worktree 隔离不是无条件生效，主 agent 必须自行确认落盘路径」 → 认知（判断变化）
-->

---

## 失败降级模板

文件读不到、窗口内无消息、或输入变量缺失时用这份最小合法卡片：

## session <SESSION_ID 或 unknown>

- **工作类型**: 其他
- **状态**: 无需交付
- **聚类锚点**:
  - repo: null
  - branch_or_pr: null
  - issue_or_bug: null
  - files:
    - (无)
  - target_object: null
- **关联事件**: 无

### 事件摘要

本 session 在窗口内无有效消息 / 文件无法读取。

### 认知增量

无

### 残留问题

无
