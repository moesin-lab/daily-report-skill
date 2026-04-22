# 01b-outside-notes

## 第 1.5 步：沙盒外笔记汇总

本阶段输入 `$TARGET_DATE`、`$RUN_DIR`，输出 `$OUTSIDE_NOTES_FILE`，供第 2 步写作使用。沙盒外笔记由容器外写入，已是 md 摘要，本阶段不做再摘要，只做聚合和结构规整。

## 输入源

目录固定为 `$OUTSIDE_NOTES_DIR/$TARGET_DATE/`，文件命名 `HHMM-slug.md`，内部段落固定为 `## Summary` / `## Verification`（可选）/ `## Follow-up`（可选）。

## 调度

调度 Haiku 临时子 agent（`subagent_type: general-purpose`，模型 `haiku`），任务：

1. 检查目录 `$OUTSIDE_NOTES_DIR/$TARGET_DATE/`。
2. 目录不存在或无 `.md` 文件：
   - 写空文件 `$RUN_DIR/outside-notes.md`（只含一行 `<!-- empty -->`）。
   - 向 `$RUN_DIR/runtime-issues.txt` 追加一行：`outside-notes: 当日无沙盒外笔记`。runtime-issues 采集本身是可选信号，不阻塞。
3. 存在文件时按文件名升序遍历，每个文件产出一个三行结构：

   ```markdown
   - **HH:MM 标题** — Summary 首段压成一句，≤ 50 字。
     - 验证：Verification 摘要，≤ 40 字；缺节省略。
     - 跟进：Follow-up 摘要，≤ 40 字；缺节省略。
   ```

   - HH:MM 从文件名前四位拆出，格式 `HH:MM`。
   - 标题取正文首行 `#` 标题，缺则回退到 slug。
   - 不摘编 Summary 以外的段落内容；只做句子裁剪，不意译、不合并多条笔记。

4. 输出路径固定 `$RUN_DIR/outside-notes.md`。文件首行写 `# outside-notes $TARGET_DATE`，其后空行，再接 bullet 列表。

## 回报

子 agent 回报以下字段：

- `OUTSIDE_NOTES_FILE`：写入路径。
- `OUTSIDE_NOTES_COUNT`：bullet 条数（空目录为 0）。

`$OUTSIDE_NOTES_FILE` 已由第 0 步 bootstrap 固化进 `$BOOTSTRAP_ENV_FILE` 和 `/tmp/daily-report/current.env`（值为 `$RUN_DIR/outside-notes.md`），子 agent 只需按该路径写入，后续阶段 `source /tmp/daily-report/current.env` 即可读到，无需再追加 export。

## 约束

- 子 agent 禁止读 `$OUTSIDE_NOTES_DIR/` 以外的路径。
- 子 agent 禁止调 Agent tool 起二级子 agent。
- 子 agent 不做写作级重述；原文若敏感，不做掩码（第 2.1 和 2.6 步的隐私审查会兜底）。
- 本阶段失败不阻塞日报：降级为写空 `$OUTSIDE_NOTES_FILE` 并在 runtime-issues 记一行。
