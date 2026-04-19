## 第 2.7 步：TL;DR 生成与插入

在第 2.6 步全文隐私复审通过之后、第 3.0 步发布之前，为日报补一段面向「半年后回看」的 TL;DR。位置：frontmatter 之后、`## 概览` 之前。

### 产物

- 更新后的 `$BLOG_DIR/source/_posts/daily-report-$TARGET_DATE.md`，顶部多一节 `## TL;DR`。

### 变量

```bash
FINAL_MD="$BLOG_DIR/source/_posts/daily-report-$TARGET_DATE.md"
TLDR_RAW="$RUN_DIR/tldr-raw.txt"
TLDR_PROMPT="$RUN_DIR/tldr-prompt.txt"
PROMPT_TEMPLATE="$HOME/.claude/skills/daily-report/reference/prompts/tldr-generator.md"
MAX_ATTEMPTS=3
LAST_ERROR=""
TLDR_OK=0
```

### 执行循环

最多尝试 `MAX_ATTEMPTS` 次。每次流程：

1. **构造 prompt**：把 `$PROMPT_TEMPLATE` 文本里的占位符替换后落到 `$TLDR_PROMPT`：
   - `{{TARGET_DATE}}` → `$TARGET_DATE`
   - `{{FINAL_MARKDOWN_PATH}}` → `$FINAL_MD`
   - `{{LAST_ERROR_SECTION}}` → 首次空串；重试时填：

     ```text
     ## 上一次产出被验证器拒绝

     错误清单（必须每条都避开）：

     <LAST_ERROR 原文，保留每行前缀>
     ```

   模板里的 ``` 围栏只是让 prompt 正文在本文档里可读，替换时**取围栏内的文本**，不要把围栏也写进 `$TLDR_PROMPT`。

2. **派单**：调用 `general-purpose` sub-agent，模型指定 Opus。prompt 内容 = `$TLDR_PROMPT` 的文件正文。sub-agent 只产出 TL;DR 正文，不执行其他动作。主 agent 把返回文本写进 `$TLDR_RAW`。

3. **验证 + 插入**：

   ```bash
   VALIDATOR_OUT=$(python3 ~/.claude/skills/daily-report/scripts/review/insert-tldr.py \
     --markdown-path "$FINAL_MD" \
     --tldr-path "$TLDR_RAW" \
     --output "$FINAL_MD" 2>&1)
   VALIDATOR_EXIT=$?
   ```

   - `VALIDATOR_EXIT == 0`：TL;DR 已插入 `$FINAL_MD`，设 `TLDR_OK=1`，跳出循环。
   - `VALIDATOR_EXIT == 2`：校验失败，把 stderr 内容赋给 `LAST_ERROR`，进入下一次尝试。
   - `VALIDATOR_EXIT == 1`：脚本内部错误（缺文件、frontmatter 缺失等），立即终止本步骤并报错，不重试。

### 失败降级

三次尝试后 `TLDR_OK` 仍为 `0`：

- 不阻塞发布。
- 在第 3.4 步的通知里附加 `TL;DR 生成失败，最终 3 条错误：<$LAST_ERROR>`。
- `$FINAL_MD` 保持原样，`## TL;DR` 节不存在。

### 约束

- TL;DR 生成只基于 `$FINAL_MD`，不回读 session cards / opposing / analysis / raw jsonl。
- 验证由脚本层兜底，不在 prompt 里恳求模型自查；模型只负责写作，校验 + 重派由本步骤的循环控制。
- TL;DR 文本不再做额外隐私审查：输入已经是第 2.6 步放行的文本，校验器正则覆盖 session id / commit hash / 文件路径三类机械泄露；若未来发现模型会从系统 prompt 外引入新内容，再追加 Haiku 隐私复审子步骤。
