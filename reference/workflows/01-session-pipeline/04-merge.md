### 步骤 d：机械聚类

执行脚本生成 `$RUN_DIR/merge-groups.json`：

```bash
RUN_DIR="$RUN_DIR" python3 ~/.claude/skills/daily-report/scripts/session/build-merge-groups.py
```

可合并条件：

- 明确属于同一主题工作。
- 至少命中一个结构化锚点，并有辅助信号支撑。
- 每组合并 session 数 <= 5。

结构化锚点：

- `repo` 相同，且 `target_object` 相同或明显关联。
- `branch_or_pr` 相同且非 null。
- `issue_or_bug` 相同且非 null。
- `files` 至少一个路径重合。

辅助信号：

- 「关联事件」提到同一目标。
- 「工作类型」相同且事件摘要指向同一目标。

脚本输出格式：

```json
[
  {
    "group_id": "g1",
    "session_ids": ["abc123", "def456"],
    "merge_reason": "..."
  }
]
```

无合并组时脚本写 `[]`，跳过步骤 e。

### 步骤 e：派 `session-merger`

对每个合并组并行调用 Agent tool：

- `subagent_type: session-merger`
- 固定 Sonnet。

传入变量块：

```text
GROUP_ID=<g1>
SESSION_FILES=
<session 文件路径 1>
<session 文件路径 2>
MERGE_REASON=<merge-groups.json 里的 merge_reason>
PHASE1_CARDS=
<对应 phase1 卡片拼接>
WINDOW_START_ISO=<...>
WINDOW_END_ISO=<...>
TARGET_DATE=<...>
RUN_DIR=/tmp/dr-<TARGET_DATE>
```

产物：`$RUN_DIR/merged-<GROUP_ID>.md`。

读取约束同 `session-reader`：优先切片读 chunks，只在必要时小范围补读 raw jsonl，`limit <= 200` 行。
