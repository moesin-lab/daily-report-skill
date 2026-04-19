### 步骤 a：派 `session-reader`

对 `$RUN_DIR/kept-sessions.txt` 中每个 session 并行调用 Agent tool：

- `subagent_type: session-reader`
- 默认 Sonnet；短会话或 facet 缓存命中且只需 phase1 卡片时可用 Haiku。

传入变量块：

```text
SESSION_FILE=<绝对路径>
WINDOW_START_ISO=<...>
WINDOW_END_ISO=<...>
TARGET_DATE=<YYYY-MM-DD>
RUN_DIR=/tmp/dr-<TARGET_DATE>
METADATA_FILE=/tmp/dr-<TARGET_DATE>/metadata-<sid>.json
FACET_OUT=/tmp/dr-<TARGET_DATE>/facet-<sid>.json
```

子代理产物：

- `$RUN_DIR/phase1-<sid>.md`
- `$RUN_DIR/facet-<sid>.json`

读取约束：

- `session-reader` 不直接整读大 jsonl。
- 先用 `scripts/session/slice-session.py` 生成 index 和 chunks，再按 index 读取 chunk。
- 只有切片不足以支撑关键判断时，才允许 `Read(offset, limit)` 小范围补读；`limit <= 200` 行。
- 主 agent 不读 raw jsonl。

缺文件降级：

session-reader 全部返回后，直接执行：

```bash
RUN_DIR="$RUN_DIR" python3 ~/.claude/skills/daily-report/scripts/session/fallback-session-artifacts.py --ensure-all
```

脚本会为缺失的 `phase1-<sid>.md` / `facet-<sid>.json` 写入最小合法降级文件，并记录 `$RUN_DIR/runtime-issues.txt`。
