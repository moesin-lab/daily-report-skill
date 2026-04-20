# Step 03 — Mock 层（窄，按时序分两批）

**原则倒置**：成功路径和常规错误由真实 Track B 验证；mock 只实现真实环境**不好复现**的失败形态。mock 层做得越少越好。

## 覆盖判断流程

- 一个失败形态先问：Track B 能不能复现？能 → 不写 mock，写进 `08-track-b.md` 的场景表
- 只有 Track B 无法手动触发或触发会污染生产资源时，才在本 step 覆盖

## 两批交付

### Stage 1 前置 mock（阻塞 `04-deterministic.md` 上线）

这批 mock 是 L1 失败降级断言的锚点，不做 → 这些断言要么残缺要么静默 skip：

- **git remote pre-receive 拒收**：真实 GitHub push protection / branch protection 临时不好触发，mock bare repo + pre-receive hook 复现
- **邮件投递 `bounce` / `spam_filtered` / `quota_exceeded`**：真实 mailbox 不能稳定复现，mock HTTP 服务（`scripts/eval/mock-mails.py`）
- **Telegram `bot_blocked` / `chat_not_found` / `message_too_long`**：配错群或拉黑 bot 会污染资源，mock 触发
- **cc-connect relay 离线**：真实 relay 摘掉会影响生产通知，mock relay 替代
- **codex replay**：Track A 反方路径 deterministic 回放；真实 Track B 直接跑 codex
- **session jsonl 格式异常 / 截断**：故意造畸形 jsonl 触发 trace-parser 降级

### Stage 4 后置 mock（Track B 跑稳后补盲点）

Track B 真实环境跑过一段时间后，对仍未覆盖的特殊失败形态补：

- **facet submodule push 冲突**：远端 submodule 的并发冲突复现
- **apply-memory-candidates ENAMETOOLONG**：文件系统边界错误
- 周 smoke 失败分类里出现 > 1 次的其他新形态

## 明确排除（交给 Track B 验证）

- Blog push 成功路径
- 邮件成功投递
- Telegram 成功发送
- cc-connect 通知成功
- facets submodule push 成功
- 真实 codex 正常返回反方观点

这些形态不在本 step 补 mock。

## Mock 服务契约

每个 mock 必须实现：

- `GET /_state` → 请求数组（含 ts / method / path / headers / body）
- `POST /_fault` → 打开/关闭某一种 fault 模式（按失败形态命名）
- `trap` 清理：`scripts/eval/mock-env.sh` 一键拉起 + 一键拆除

stdlib 优先；需要 `http.server` 起端口时随机取避冲突。

## 时间与项目路径注入

mock 脱不掉两个外部注入点：

- `CC_PROJECTS_DIR` 注入 bootstrap（`find ~/.claude/projects` 改读该变量）
- 时间钩子：bootstrap 所有时钟取 `$WINDOW_END` / `$TARGET_DATE`，不直接 `date`

这两条在**所有 CI run** 都生效，不只是 mock 模式。

## Smoke 自测

每个 mock 必须带：

- 启停 test：`mock-env.sh up && curl .../_state && mock-env.sh down`
- 请求捕获 test：POST 一条假请求验 `_state` 能读到
- Fault 注入 test：`_fault` 切换前后响应状态码不同

无 mock smoke 通过，不允许挂进 L1。

## 不在本 step

- 真实 Track B 场景表在 `08-track-b.md`
- L1 针对 mock state 的断言消费在 `04-deterministic.md`
