# 03-publish-notify

本阶段由 Haiku 临时脚本子 agent 读取并执行。只运行发布脚本、处理失败降级并回报摘要；不改写日报正文，不做内容判断。

## 第 3.0 步：发布博客

使用本地 `$BLOG_DIR`，不要 clone。文件名使用 `$TARGET_DATE`。

```bash
TARGET_DATE="$TARGET_DATE" ~/.claude/skills/daily-report/scripts/publish/publish-blog.sh
```

## 第 3.1 步：发布 artifacts

```bash
TARGET_DATE="$TARGET_DATE" RUN_DIR="$RUN_DIR" \
  "${DR_FACETS_PUBLISH_CMD:-$HOME/.claude/skills/daily-report/scripts/publish/publish-artifacts.sh}"
```

脚本提交并推送 `$BLOG_DIR/facets` submodule，再更新博客仓库 submodule ref。
用 `DR_FACETS_PUBLISH_CMD` 可替换为任何接受相同 env（TARGET_DATE、RUN_DIR）的脚本。

## 第 3.2 步：写入 memory 候选

输入：`/tmp/dr-$TARGET_DATE-memory-candidates.json`。

```bash
MEMORY_CHANGES=$(python3 ~/.claude/skills/daily-report/scripts/publish/apply-memory-candidates.py \
  --candidates "/tmp/dr-$TARGET_DATE-memory-candidates.json" 2>&1) || \
  MEMORY_ERROR="$MEMORY_CHANGES"
```

约束：

- `memory-candidates.json` 为空数组时，`$MEMORY_CHANGES` 留空。
- 第 3.2 步失败不阻塞发布，记录 `$MEMORY_ERROR` 并在通知中说明。
- 不覆盖已有 memory 文件；只新建或追加。
- 不把临时任务、代码可直接 grep 得到的信息、凭证值写进 memory。

## 第 3.3 步：邮件投递

```bash
MAIL_STATUS=$(TARGET_DATE="$TARGET_DATE" RUN_DIR="$RUN_DIR" \
  "${DR_MAIL_CMD:-$HOME/.claude/skills/daily-report/scripts/publish/send-email.sh}" 2>&1) || \
  MAIL_STATUS="邮件投递失败：$MAIL_STATUS"
```

约束：

- 邮件失败不阻塞最终通知。
- 不把邮箱、mailbox、api_key 或其他凭证写进日报正文。
- 不嵌入远程图片或远程 CSS。
- 用 `DR_MAIL_CMD=:`（shell no-op）可静默关闭邮件投递。自定义命令需接受
  `TARGET_DATE` / `RUN_DIR` env 和 optional 位置参数 `<markdown_path>`。

## 第 3.4 步：验证与通知

```bash
TARGET_DATE="$TARGET_DATE" ~/.claude/skills/daily-report/scripts/publish/verify-published.sh
```

通知必须发送，无论成功失败：

```bash
"${DR_NOTIFY_CMD:-$HOME/.claude/skills/daily-report/scripts/publish/send-cc-notification.sh}" "<通知内容>"
```

通知内容包含：

- 日报发布状态：成功链接或失败原因。
- 邮件投递状态：`$MAIL_STATUS`。
- memory 变更：`$MEMORY_CHANGES` 非空时附加。
- memory 失败：`$MEMORY_ERROR` 非空时附加。

通知只发主 DM，不发 codex 群。
用 `DR_NOTIFY_CMD=:` 可静默关闭；自定义命令需接受 `"<消息字符串>"` 作为位置参数或 stdin。
