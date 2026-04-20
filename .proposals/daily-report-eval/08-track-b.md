# Step 08 — 真实环境 Track B

前置：`02-fixtures.md`、`04-deterministic.md` 稳定。本 step 优先级高于 `03-mock-layer.md`——成功路径与常见失败由真实调用覆盖。

覆盖变量缺失必须 `exit 1`，严禁回退默认值污染生产。

## 隔离资源清单

- 专用博客仓：`sentixA/daily-report-eval`（独立仓）或主博客 `eval/YYYY-MM-DD` 分支族；`BLOG_REMOTE_URL` 覆盖 origin
- 专用 mails mailbox：`eval-sentix@mails.dev` + 独立 API key；`MAILS_CONFIG` 指向独立 config
- 专用 Telegram bot + 测试群；`TELEGRAM_BOT_TOKEN` / `CC_NOTIFY_CHAT_ID` 覆盖
- 真 codex token 复用主账号；`CODEX_BIN` 指回真实 codex（不读 replay）
- Track B 专属 fixture：取真实最近一天（当前候选 2026-04-17），**不共享** Track A 的 `typical-day`
- 资源清单集中：`~/.claude/.tasks/eval-b-env.sh` 导出全部覆盖变量

## 真实调用验证（每次 Track B 触发都跑）

- [ ] 真 `git push` blog ref 成功 + `gh api` 查 GitHub Pages URL 200（允许 5min 渲染延迟，轮询探测）
- [ ] facets submodule 真实 push 成功 + 主仓 submodule ref 更新可 `git ls-tree` 确认
- [ ] 真邮件投测试 mailbox → 5 分钟内 mails.dev API 查到，subject / attach 匹配
- [ ] 真 Telegram `sendMessage` 返回 `ok=true`，`chat.id` 匹配测试群
- [ ] 真 cc-connect 通知到达测试 DM（bot getUpdates 或人工确认）
- [ ] 真 codex 返回非空反方观点

## 后发 smoke（每天正式日报发完触发）

- [ ] 挂 `03.4 verify-published.sh` 之后，不阻塞正式通知流程
- [ ] smoke 失败单独告警到主 DM，**不重跑日报**（避免双发）
- [ ] 失败落 `~/.claude/.tasks/eval-b.db`

## 周 smoke（cron）

- [ ] 每周一次 cron，跑完整真实调用验证
- [ ] cron 通过 cc-connect 的 cron 配置注册，不写 system crontab
- [ ] 连续 3 次失败推告警到主 DM；单次失败只记录
- [ ] 失败截取：`raw response + stderr` 落 `~/.claude/.tasks/eval-b-failures/<ts>/`，保留 30 天
- [ ] 失败分类：`api_breaking` / `rate_limit` / `transient_network` / `content_reject` / `unknown`
- [ ] 连续 2 次 `api_breaking` + `content_reject` → 触发 `09-regression-loop.md` 的回灌管道

## 失败形态分工

- 能真实触发 → 本 step 记录 + 告警
- 不能真实触发（push protection / bounce / 特殊 API error）→ 归 `03-mock-layer.md` 补

## 不做的事

- 内容断言（留给 `04-deterministic.md`）
- Fault 注入（留给 `03-mock-layer.md`）
- 版本 A/B 对照（留给 `07-paired-eval.md`）
- Outcome 长期基线（留给 `09-regression-loop.md`）

## 备注

Track B 失败的三种原因互不可混：代码 bug（L1 该抓）/ API 漂移（追踪上游）/ 环境 rate_limit 或网络。失败分类就是为拆清这三者，分类错会把"我们代码的 bug"污染到"上游坏了"的统计里。
