# 99-rules

## 全局规则

- 全文中文。
- 日报主体以会话内容为核心，GitHub 活动只作补充。
- 公开发布前必须完成初审和全文隐私复审。
- 发布目标是 `$BLOG_DIR` 对应的 `$DAILY_REPORT_REPO`（作者自己的博客仓库）；禁止推到任何协作用户的仓库。
- 主 agent 在 session pipeline 后不得再读 raw jsonl。

## 隐私边界

日报正文、附录、通知中禁止出现：

- API Key、Token、Secret、Bearer 值。
- 密码、凭证、环境变量值。
- 邮箱、手机号、IP 地址。
- Telegram Bot Token、Chat ID、User ID。
- 私有仓库内部 URL 或可定位入侵面的细节。

本 skill 只审查即将公开发布的日报文本；本地凭证明文迁移不在本 workflow 范围内。
