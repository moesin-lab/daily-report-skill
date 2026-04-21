## 第 2.2 步：反方视角（异构 Agent）

只通过 `scripts/review/run-opposing-agent.py` 执行。默认 backend 为 `codex-plugin`（走 openai-codex Claude Code 插件的 shared runtime）；替换 backend 用 `OPPOSING_BACKEND` 或 `--opposing-backend`，见 `scripts/README.md` 的「反方 reviewer backend」段。不要手动调用 `codex exec`、`codex-review` skill 或 `cc-connect relay`。

### 执行

```bash
OPPOSING_ENV=$(python3 ~/.claude/skills/daily-report/scripts/review/run-opposing-agent.py \
  --window-start "$WINDOW_START" \
  --window-end "$WINDOW_END" \
  --window-start-iso "$WINDOW_START_ISO" \
  --window-end-iso "$WINDOW_END_ISO" \
  --target-date "$TARGET_DATE" \
  --run-dir "$RUN_DIR" \
  --notify-failure \
  --send-telegram)

. "$OPPOSING_ENV"
OPPOSING_CONTENT=$(cat "$OPPOSING_FILE")
OPPOSING_OK=$(cat "$OPPOSING_OK_FILE")
```

脚本产物：

- `$OPPOSING_FILE`：反方正文，失败时为降级占位文本
- `$OPPOSING_OK_FILE`：`1` / `0`
- `$ANALYSIS_FILE`：失败时的辨析降级文本；成功时为空
- `$OPPOSING_PROMPT_FILE` / `$OPPOSING_RAW_FILE`：排查用，主 workflow 默认不读取

### 分支

- `$OPPOSING_OK == 1`：保留 `$OPPOSING_CONTENT`，继续第 2.3 步中立辨析。
- `$OPPOSING_OK != 1`：跳过第 2.3 步，读取 `$ANALYSIS_FILE` 作为 `$ANALYSIS_CONTENT`，第 2.4 步继续执行。

```bash
if [ "$OPPOSING_OK" != "1" ]; then
  ANALYSIS_CONTENT=$(cat "$ANALYSIS_FILE")
fi
```

### 约束

- 工作流只消费脚本暴露的 env 和文件。
- 第 2.4 步在反方失败时仍运行，但只能基于正文主体和 session cards 生成候选。
