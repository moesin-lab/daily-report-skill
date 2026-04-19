# Session-reader Facet 填写模板与纪律

本文件是 session-reader sub-agent 的**附加模板**。除了按 `session-reader.card.md` 产出 `phase1-<sid>.md` 这张人读的 Markdown 卡片之外，你还要为**同一个 session** 产出一份结构化的 `facet-<sid>.json`，供下游的 lint / aggregate / publish 脚本和未来的周月度聚合管线消费。本文件定义这份 facet JSON 的 schema 和判断字段的填写纪律。

facet JSON 的字段分两类：**机械字段**（`session_id` / `target_date` / `duration_minutes` / `tools_used` / `raw_stats` 等）由零 LLM 脚本 `extract-metadata.py` 预先算好，落在 `$METADATA_FILE`（即 `$RUN_DIR/metadata-<sid>.json`），你**原样继承、不得修改任何值**；**判断字段**（`goal` / `goal_detail` / `satisfaction` / `friction_types` / `anchors` / `first_prompt_summary` / `summary` / `status`）由你这个 sub-agent 读会话内容后填写。写完落盘到 `$RUN_DIR/facet-<sid>.json`。

## Facet JSON 结构

完整 schema = `metadata-<sid>.json` 的**所有字段原样继承** ⊕ 下方判断字段。完整样例如下：

```json
{
  "... (metadata 全部字段原样继承) ...": "...",

  "goal": "修Bug",
  "goal_detail": "修复 watchdog 误杀子进程导致服务无法重启",
  "satisfaction": "likely_satisfied",
  "friction_types": ["tool_error"],
  "anchors": {
    "repo": "my-service",
    "branch_or_pr": "PR #42",
    "issue_or_bug": null,
    "target_object": "watchdog pgrep",
    "files": ["src/watchdog.py"]
  },
  "first_prompt_summary": "修 watchdog 重启不掉",
  "summary": "修复 watchdog 在子进程误判下无法重启服务的问题",
  "status": "已交付",
  "runtime_warning": null,

  "goal_categories": {"fix_bug": 1},
  "outcome": "fully_achieved",
  "claude_helpfulness": "very_helpful",
  "session_type": "single_task",
  "friction_counts": {"tool_failed": 1},
  "friction_detail": "Read 工具首次读取大文件失败，改为切片读取。",
  "primary_success": "correct_code_edits",
  "brief_summary": "用户要修 watchdog，最终已落地修复。",
  "user_instructions": []
}
```

**机械字段 ⊕ 判断字段分段说明**：

- **机械字段**（从 `$METADATA_FILE` 原样继承，逐字段拷贝，`==` 比较必须一致）：
  - `session_id` / `target_date` / `window_start_iso` / `window_end_iso`
  - `start_ts` / `end_ts` / `duration_minutes` / `user_message_count` / `turn_count`
  - `tools_used` / `languages`
  - `raw_stats`（含 `input_tokens` / `output_tokens` / `cache_creation_input_tokens` / `cache_read_input_tokens` / `tool_errors` / `user_interruptions` / `git_commits` / `git_pushes`）
  - `schema_version`
- **判断字段**（由本 sub-agent 填写）：
  - `goal` / `goal_detail` / `satisfaction` / `friction_types` / `anchors` / `first_prompt_summary` / `summary` / `status`
- **可选 insights-compatible 字段**（由本 sub-agent 填写；旧 facet 可没有这些字段）：
  - `goal_categories` / `outcome` / `claude_helpfulness` / `session_type` / `friction_counts` / `friction_detail` / `primary_success` / `brief_summary` / `user_instructions`

写入路径：`$RUN_DIR/facet-<session_id>.json`，`ensure_ascii=False, indent=2`，UTF-8。

## 判断字段填写纪律

### Long transcript summary

当 `session-reader.md` 的切片 index 里有多个 chunk 时，先对每个 chunk 做内部摘要，再提取字段。chunk 摘要必须保持 3-5 句，聚焦：

1. 用户提出了什么
2. Claude 做了什么（工具、文件、修改对象）
3. 是否有摩擦或问题
4. outcome 是什么

保留具体文件名、错误签名和用户反馈；不要保留大段命令输出、token、chat_id、API key、邮箱等敏感值。

### goal

严格从下列 **6 档** taxonomy 中选**一个**（中文原值）：

```
修Bug | 新功能 | 治理 | 调研 | 工具 | 其他
```

边界说明：

- **修Bug**：已有功能坏了要修
- **新功能**：新增用户可见功能
- **治理**：重构 / 清理 / gitignore / issue 体系 / 文档等非功能性改进
- **调研**：prompt engineering / 方案选型 / 探索实验
- **工具**：环境 / CLI / skill / mcp / statusline 等工作流改进
- **其他**：实在不属于上面的

跨多类型时按**主要产出**归类，不要硬拆。无法判断时走失败降级样板（`goal="其他"`）。

### goal_detail

**≤ 40 字**中文短句，说明用户本 session 想解决的具体问题。**只计用户明确提出的目标**；Claude 自主探索分支、顺手做的额外事情不写入。

示例：`修复 watchdog 误杀子进程导致服务无法重启`（用户明确要修 watchdog 的 bug）。

### satisfaction

严格从下列 **6 档** taxonomy 中选**一个**（英文 key）：

```
frustrated | dissatisfied | likely_satisfied | satisfied | happy | unsure
```

中文注释：

- `frustrated` — 明显沮丧（用户出现强烈负面情绪、反复抱怨、放弃等信号）
- `dissatisfied` — 不满但可继续（有明确抱怨或纠正，但对话仍在推进）
- `likely_satisfied` — 大概满意（无明显抱怨，结果交付但缺乏正面反馈）
- `satisfied` — 明确满意（用户有肯定表述，如「好」「可以」「搞定」）
- `happy` — 超预期（用户表现出积极正面情绪，如「nice」「漂亮」「这个好」）
- `unsure` — 信号不足（窗口末端无足够情绪信号，或对话半途中断）

**关键准则**：**只看窗口末端用户最后情绪，不看 Claude 自评**。Claude 自己说「已完成」「修好了」不等于用户满意；用户在末尾那条消息（或最后几轮）里怎么反应才算数。

### friction_types

严格从下列 **12 种** taxonomy 中选，**可多选、可空数组 `[]`**（英文 key）：

```
misunderstood_request        # 误解需求
wrong_approach               # 错方案
buggy_code                   # buggy 代码
tool_error                   # 工具失效
user_rejected_action         # 用户拒绝动作
user_interruption            # 用户打断
repeated_same_error          # 反复同一错
external_dependency_blocked  # 外部依赖阻塞
rate_limit                   # 限流
context_loss                 # 上下文漂移
destructive_action_attempted # 尝试破坏性动作
other                        # 其他
```

中文注释（按 key 含义）：

- `misunderstood_request` — Claude 误解了用户需求，导致方向走偏
- `wrong_approach` — 技术方案选错了，用户或事实推翻重来
- `buggy_code` — 写出的代码有 bug，需要返工修
- `tool_error` — 工具调用失败（命令失败、API 报错、脚本异常等）
- `user_rejected_action` — 用户明确拒绝 Claude 提议的动作或方案
- `user_interruption` — 用户打断 Claude 的执行（含 `[Request interrupted by user]`）
- `repeated_same_error` — 同一个错误反复出现，没一次性解决
- `external_dependency_blocked` — 外部依赖（API 限流之外的阻塞，如网络、权限、第三方服务）
- `rate_limit` — 限流（Claude API / OpenAI API / Telegram 等被限流）
- `context_loss` — 上下文漂移（Claude 忘了前文约束、改写了无关代码）
- `destructive_action_attempted` — 尝试破坏性动作（如未经许可的 `rm -rf` / `git reset --hard` / `push --force`）
- `other` — 其他可感知摩擦，但不属于以上 11 类

**关键准则**：**只标用户可感知的（抱怨、打断、返工），不标 Claude 内部自我修正**。Claude 自己跑了个命令失败然后自己改对了，用户根本没注意到，不算摩擦；用户出来纠正 / 打断 / 表达不满才算。**允许空数组**（当天无摩擦就是 `[]`，不要硬凑）。

### anchors

对齐 `session-reader.card.md` 的聚类锚点纪律。5 个键必须齐全：

- `repo`：真实仓库名（如 `project-a` / `project-b` / `docs` / `blog`）；没有则 `null`
- `branch_or_pr`：分支名或 PR 号（如 `"PR #42"` / `"feat/watchdog-fix"`）；没有则 `null`
- `issue_or_bug`：issue 号或可识别 bug 签名（如 `"#123"` / `"Conflict: terminated by other getUpdates"`）；没有则 `null`
- `target_object`：本 session 操作的主对象（如 `"watchdog pgrep"` / `"readLoop"`）；没有则 `null`
- `files`：真被读/改的路径数组。无则 `[]`（**不是 `[null]`**）。路径用**绝对或仓库根相对**，不要 `./xxx` 相对写法

**如实填写，不要脑补**：repo / PR / issue / files 只写对话里真实出现的，填不了就 `null`（或 `files` 为 `[]`）。宁可 `null` 也不要硬写猜测值，聚类会被污染。

### first_prompt_summary

**≤ 40 字**中文概括用户首条消息的意图。

**PII 防泄**：**不贴原文**，**不含 token / 邮箱 / chat_id / 密码 / Bot token / API key** 等任何敏感值。只写「做了什么」，不写「用了什么值」。

**不承载运行时警告**（警告一律写 `runtime_warning` 字段）。保持 ≤ 40 字硬上限。

### summary

**≤ 60 字**中文，本 session 一句话结论（要解决什么 + 最终状态）。

**PII 防泄**：同 `first_prompt_summary`，任何敏感凭证一律不写入。

### status

严格从下列 **5 档** taxonomy 中选**一个**（中文原值），与 `session-reader.card.md` 现有 status 字段对齐：

```
已交付 | 在分支 | 调研中 | 阻塞 | 无需交付
```

边界：

- **已交付**：代码已合并 / 方案已落地 / 问题已解
- **在分支**：代码在 branch 上未合主线 / PR 在途
- **调研中**：还没结论 / 在做实验 / 读文档
- **阻塞**：遇到外部依赖或用户决策阻塞
- **无需交付**：纯讨论、无 deliverable 的对话

### runtime_warning

- 类型：`str | null`
- 默认：`null`（绝大多数 session 应是 null）
- **仅当发现机械字段与会话事实明显矛盾时写入**，例如：
  - `"metadata duration=0 但对话实际有 20+ 条消息，疑似 timestamp 解析异常"`
  - `"tools_used 为空但对话中明显使用了 Bash 多次，疑似 jsonl 结构漂移"`
- 字数无硬上限（异常路径优先说清楚，不压字数）
- **职责分离**：原意图写 `first_prompt_summary`，警告写 `runtime_warning`。两者互不混合
- 下游：主 agent 第三步把所有非 null 的 `runtime_warning` 聚到日报"运行时问题"章节

## Insights-compatible 可选字段

这些字段参考 Claude Code `/insights` 的 facet extraction。它们不替代日报当前必需字段，而是给后续聚合和周/月报提供更细粒度输入。旧 facet 没有这些字段也合法；新生成 facet 应尽量填写。

### goal_categories

类型：`dict[str, int]`。严格从下列 taxonomy 计数，可多选：

```
debug_investigate | implement_feature | fix_bug | write_script_tool | refactor_code |
configure_system | create_pr_commit | analyze_data | understand_codebase |
write_tests | write_docs | deploy_infra | warmup_minimal
```

**只计用户明确提出的目标**。不要计 Claude 自主探索、顺手清理或自己决定做的分支。非常短或只有暖场的 session 用 `{"warmup_minimal": 1}`。

与现有 `goal` 的关系：`goal` 仍按日报 6 档选主类型；`goal_categories` 记录更细的用户目标分布。

### outcome

严格从下列 taxonomy 选一个：

```
fully_achieved | mostly_achieved | partially_achieved | not_achieved | unclear_from_transcript
```

只看用户目标是否达成，不看 Claude 自评。没有足够证据时用 `unclear_from_transcript`。

### claude_helpfulness

严格从下列 taxonomy 选一个：

```
unhelpful | slightly_helpful | moderately_helpful | very_helpful | essential
```

这是对 Claude 在本 session 中实际帮助程度的判断。不要因为工具调用多就自动判高；看是否推动用户目标达成。

### session_type

严格从下列 taxonomy 选一个：

```
single_task | multi_task | iterative_refinement | exploration | quick_question
```

按用户互动形态选：单一任务、多任务、来回打磨、探索理解、快速问答。

### friction_counts

类型：`dict[str, int]`。严格从下列 taxonomy 计数：

```
misunderstood_request | wrong_approach | buggy_code | user_rejected_action |
claude_got_blocked | user_stopped_early | wrong_file_or_location |
excessive_changes | slow_or_verbose | tool_failed | user_unclear | external_issue
```

与现有 `friction_types` 的关系：`friction_types` 仍按日报 12 档写用户可感知摩擦；`friction_counts` 用 `/insights` 细分词表计数。两者都不标 Claude 内部自我修正，必须有用户可感知影响或明显阻塞。

### friction_detail

一行中文。没有摩擦写空字符串 `""`。有摩擦时写具体发生了什么和后果，保留稳定错误签名。

### primary_success

严格从下列 taxonomy 选一个：

```
none | fast_accurate_search | correct_code_edits | good_explanations |
proactive_help | multi_file_changes | good_debugging
```

只选最主要的成功模式；没有明显成功用 `none`。

### brief_summary

一行中文，概括“用户想要什么，以及是否拿到了”。可与 `summary` 接近，但 `brief_summary` 更偏 outcome 叙述。

### user_instructions

类型：`list[str]`，最多 3 条。只记录用户明确给 Claude 的可复用工作偏好或重复性指令，例如“以后改完必须跑测试”。不要记录一次性业务需求，不要记录敏感值。

## 关键准则（Prompt 硬约束）

1. **friction_types 只标用户可感知的（抱怨、打断、返工），不标 Claude 内部自我修正**
2. **satisfaction 只看窗口末端用户最后情绪，不看 Claude 自评**
3. **goal_detail 只计用户明确提出的目标；Claude 自主探索分支不计**
4. **绝不修改机械字段**（tokens / tool_counts / duration / raw_stats / languages）
5. **goal_categories 同样只计用户明确提出的目标；Claude 自主探索不计**
6. **outcome / helpfulness / primary_success 都以用户目标是否被推进为准，不以 Claude 自评为准**

**机械字段异常的处理路径**：发现异常时写 `runtime_warning` 字段（新增，v1.1），**不要**塞进 `first_prompt_summary` 或 `summary`。这样 `first_prompt_summary` 可以始终保持"原意图 ≤ 40 字"的语义纯净。

机械字段一致性由下游 lint 脚本逐字段核对，任何篡改都会被判 fail。

## 失败降级样板

当 session-reader **无法判断**（会话内容读不到、窗口内无有效消息、关键信号缺失无法给出合理判断）时，用下面这份**最小合法 facet JSON**。机械字段继承自 `$METADATA_FILE`（用 `<...>` 中文占位表示），判断字段填降级默认值：

```json
{
  "session_id": "<从 METADATA_FILE 继承>",
  "target_date": "<从 METADATA_FILE 继承>",
  "window_start_iso": "<从 METADATA_FILE 继承>",
  "window_end_iso": "<从 METADATA_FILE 继承>",
  "start_ts": null,
  "end_ts": null,
  "duration_minutes": 0,
  "user_message_count": 0,
  "turn_count": 0,
  "tools_used": {},
  "languages": [],
  "raw_stats": {
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
    "tool_errors": 0,
    "user_interruptions": 0,
    "git_commits": 0,
    "git_pushes": 0
  },
  "schema_version": 1,

  "goal": "其他",
  "goal_detail": "本 session 降级处理",
  "satisfaction": "unsure",
  "friction_types": [],
  "anchors": {
    "repo": null,
    "branch_or_pr": null,
    "issue_or_bug": null,
    "target_object": null,
    "files": []
  },
  "first_prompt_summary": "本 session 降级处理",
  "summary": "本 session 降级处理",
  "status": "无需交付",
  "runtime_warning": null
}
```

**何时用此模板**：session-reader 无法判断时（会话内容读不到、窗口内无有效消息、输入变量缺失、或内容无法支撑任何判断字段的合理填写）。

**注意**：实际落盘时，机械字段的真实值**必须**从 `$METADATA_FILE` 逐字段拷贝进来（上方样板里用 `<从 METADATA_FILE 继承>` 占位表示的字符串型机械字段，真写时要换成 metadata 里的真实值；数值/容器型机械字段样板里已经是合法降级值，若 metadata 有真实值则用真实值覆盖）。判断字段部分则原样使用上方降级默认值。
