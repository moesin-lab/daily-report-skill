## 第 2.4 步：生成思考、建议和 memory 候选

产物：

- `$REFLECTION_SECTION`
- `$SUGGESTIONS_SECTION`
- `/tmp/dr-$TARGET_DATE-memory-candidates.json`

约束：

- Generator 用 `general-purpose` 子 agent，模型指定 Opus。
- Validator 通过 `proxy-agent` 子 agent 派给外部 `deepseek-chat`（走 opencode，不消耗 Anthropic token）。
- 禁止调用 `codex-review`、`codex exec`、`cc-connect relay`。
- Generator 先按 prompt 做预筛，禁止把明显不合格候选交给 Validator 兜底。
- Validator 独立并行复核，候选未通过则丢弃。

### 2.4a Generator

调用 1 个 `general-purpose` 子 agent，模型指定 Opus。读取 `reference/prompts/candidate-generator.md`，替换：

- `{{TARGET_DATE}}`
- `{{MAIN_BODY}}`
- `{{OPPOSING}}`
- `{{ANALYSIS}}`
- `{{SESSION_CARDS}}`

Generator 写出 `/tmp/dr-$TARGET_DATE-candidates.json`。主 agent 读取为 `$CANDIDATES`。

Generator 可以输出空数组 `[]`；这表示当天没有足够强的思考、建议或 memory 候选，不算失败。

反方失败时，`{{OPPOSING}}` / `{{ANALYSIS}}` 填降级文本，不编造反方材料。

### 2.4b Validator

对 `$CANDIDATES` 每条候选 N（从 0 起编号）并行调用 1 个 `proxy-agent` 子 agent，`BACKEND` 指定 `deepseek-chat`。

每条候选的派发流程：

1. 主 agent 读取 `reference/prompts/candidate-validator.md`，替换：
   - `{{CANDIDATE_JSON}}`
   - `{{SESSION_CARDS}}`
   渲染后的 prompt 写入 `$RUN_DIR/validator-prompt-$N.txt`。
2. 派一个 `proxy-agent`，prompt 体的 KV 输入：

   ```text
   BACKEND=deepseek-chat
   PROMPT_FILE=$RUN_DIR/validator-prompt-$N.txt
   TIMEOUT_S=120
   ```

3. `proxy-agent` 返回的 wrapper 形如 `<<<PROXY_BEGIN backend=deepseek-chat exit=E duration_ms=M>>>BODY<<<PROXY_END>>>`。主 agent 抽出 `BODY`（应为严格一行 JSON），追加写入 `$RUN_DIR/validations.jsonl`。
4. 失败语义（任一命中则该候选按失败处理，写占位 `{"pass": false, "reason": "validator runtime failure: <短原因>"}` 到 `validations.jsonl`）：
   - `proxy-agent` 报错或 wrapper 缺失
   - wrapper 中 `exit != 0`
   - `BODY` 不是合法 JSON 或不含 `pass` 字段

Validator 负责复核格式、锚点真实性、认知非重复、触发条件和后续用途。

### 2.4c 组装

```bash
python3 ~/.claude/skills/daily-report/scripts/review/assemble-candidates.py \
  --candidates "/tmp/dr-$TARGET_DATE-candidates.json" \
  --validations "$RUN_DIR/validations.jsonl" \
  --target-date "$TARGET_DATE" \
  --output-dir /tmp
```

读回变量：

- `$REFLECTION_SECTION`：`/tmp/dr-$TARGET_DATE-new-reflection.md`
- `$SUGGESTIONS_SECTION`：`/tmp/dr-$TARGET_DATE-suggestions.md`
- `$MEMORY_CANDIDATES`：`/tmp/dr-$TARGET_DATE-memory-candidates.json`

组装规则由脚本负责：

- 思考最多 3 条，空则写空文件。
- 建议分“给自己（`$AUTHOR_AGENT_NAME`，未设时为"作者"）”和“给用户（`$USER_NAME`，未设时为"用户"）”，各最多 3 条，空子节省略。
- memory 候选为空时写 `[]`。

如果 candidates JSON 无法解析，跳过本步骤：思考和建议写空，memory 候选写 `[]`，并记录运行时问题。
