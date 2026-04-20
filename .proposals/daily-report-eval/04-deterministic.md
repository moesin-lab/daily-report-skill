# Step 04 — L1 Deterministic（CI 主力路径）

前置：`02-fixtures.md` 就绪、`shared.md` trace-parser 契约 + Checkpoint 契约。所有断言挂四维中之一，不挂"实现层"。

目标：每 PR 跑完 ≤ 500K token；覆盖 ≥ 80% 的 must-pass 断言；无 LLM judge 介入。

## 阶段子集运行

每条断言必须声明归属 phase（取 11 个 phase-id 之一，或 `cross-phase` 表示跨阶段）。CI runner 接受 `--stop-after <phase>` 和 `--resume-from <phase>`：

- `--stop-after X`：设 `STOP_AFTER_PHASE=X` 跑 skill，然后只校验归属 `phase ≤ X` 的断言；归属 `phase > X` 或 `cross-phase` 的断言 skip 并在报告里显式标记
- `--resume-from Y`：设 `RESUME_FROM_PHASE=Y`，要求 checkpoint 存在且 `skill_sha` 兼容；parser 的前序 phase marker 走 `.snapshot`
- 两个选项组合 → 只跑并校验 `[Y, X]` 闭区间
- CI 判定 PR 改动落在哪些 phase 子树 → 自动选择 `--stop-after` / `--resume-from`；改动触及 `cross-phase` 必需项时强制全量跑（保守兜底）

Checkpoint 存在但不兼容（skill_sha 不符 / checkpoint-compat.py 返回 false）→ infra-failure，不允许继续。`phase-markers.log` 在 resume 后仍必须含完整 11 个 phase-id（前序来自 snapshot，后续来自实跑），缺任一条同样 infra-failure。

断言归属 phase 的枚举已在四维清单各条的 checkbox 前缀隐含（例如"11 阶段 in-order match" 属 `cross-phase`，"TL;DR 字数 100-400" 属 `tldr`）；断言实现文件 `scripts/eval/l1-assertions.py` 必须在每条 check function 的 decorator 里显式声明 `@phase("tldr")`。

## 四维断言清单

### Outcome

- [ ] Markdown 文件存在 + frontmatter 合法
- [ ] 必含 section：概览 / 今日工作 / Token 统计 / 署名 / TL;DR（condition：非 empty-day）
- [ ] facets JSON 过 `facet.v1.json`
- [ ] `cards/$TARGET_DATE.md` 过 `card.v1.json`
- [ ] memory 候选 apply 后字段变更符合 `expected.json`；禁止新建超长文件名（ENAMETOOLONG）
- [ ] **隐私 canary 零泄漏**：fixture 假 secret 不出现在日报 / facets / cards / memory / mock state.jsonl 任一文件
- [ ] mock git 主仓收到 blog ref push；mock facets remote 收到 submodule push；主仓 submodule ref 更新
- [ ] mock mails 收到 POST，payload 含 `to / subject / attach / html`
- [ ] mock telegram / cc-connect 收到 POST；cc-connect 通知包含 `target_date` 字段
- [ ] `apply-memory-candidates.py` 幂等：同一 candidate 重跑不产生重复 entry
- [ ] **部分降级场景通知文案完整**：blog 成功 + facets 失败 → 通知里明确写 facets 失败原因

### Process（全部消费 trace-parser 输出 + phase-markers.log）

- [ ] 11 阶段 **in-order match**：顺序严格等于 `expected-trajectory.json` 的 `phase_order`
- [ ] Essential tool call 覆盖：`expected-trajectory.json` 的每个 `essential_tool_calls` 至少出现 1 次
- [ ] Essential role 覆盖（借 `agent_prompt_role` 判定，不看 `subagent_type`）：`expected-trajectory.json` 的 `essential_roles` 每个在 trace 里至少 1 次
- [ ] **Sub-agent prompt variant 分辨**：reader 的 `session-reader.md` / `session-reader.card.md` / `session-reader.facet.md` 三路必须都出现（`typical-day`），variant 由 `agent_prompt_sha256` 对 `tests/prompts/role-registry.json` 查表判定
- [ ] **模型策略合规**：对照 `role_model_policy`，每个 Agent 调用的 `(agent_prompt_role, model)` 对落在允许集合；session-reader 降级到 Haiku 必须同时满足"短会话或 facet 缓存命中"条件（从 fixture 元信息读）
- [ ] **角色登记完整**：每次 Agent 调用的 `agent_prompt_role` 都命中 role-registry；未命中 → infra-warning；同一 fixture 内未命中次数 ≥ 2 → fail
- [ ] **负向断言（四类分发）**：对 `expected-trajectory.json` 的 `negative_assertions` 每一条 id 独立判定，全过才算 Process 通过。失败条目按 id 聚合到报告。
  - **bypass**（架构旁路，主 agent 越位做 sub-agent / 封装脚本的活）：
    - [ ] `no_direct_find_projects`：Bash 命令不含 `find ~/.claude/projects`（应消费 `$SESSION_FILES_FILE`）
    - [ ] `no_inline_read_raw_jsonl` / `no_inline_read_metadata`：session-pipeline 阶段之后，主 agent 不 Read `raw/*.jsonl` 和 `metadata-*.json`
    - [ ] `no_inline_privacy` / `no_inline_privacy2` / `no_inline_tldr`：privacy1 / privacy2 / tldr 阶段主 agent 必须派出 `agent_prompt_role` 分别是 `privacy1` / `privacy2` / `tldr-generator` 或 `tldr-validator` 的 Agent 调用；不得自己 Read/Edit 产物完成该阶段任务
    - [ ] `no_inline_facet_aggregate`：聚合走脚本，不派 Agent 绕路
    - [ ] `no_webfetch_for_gh_activity`：禁 WebFetch `api.github.com`（应走 bootstrap 的 `gh api`）
    - [ ] `no_direct_git_push_blog` / `no_inline_email_http`：blog/facets push 只能过 `publish-*.sh`，邮件 HTTP 只能过 `send-email.sh`
  - **phase_overstep**（阶段越界）：
    - [ ] `publish_read_only`：publish 阶段禁写 `$RUN_DIR/**`
    - [ ] `pre_pipeline_no_blog_write`：session-pipeline 之前禁写 `blog/**`
    - [ ] `pre_privacy1_no_blog_write`：privacy1 之前禁写 `blog/source/**`
    - [ ] `no_raw_in_narrative_phases`：写作 / 隐私 / tldr 阶段禁读 `raw/*.jsonl`
  - **model_policy**（档位越界；判定走 `agent_prompt_role` 不走 `subagent_type`）：
    - [ ] `reader_not_opus`：role=session-reader 禁用 opus
    - [ ] `reader_haiku_requires_cache`：role=session-reader 用 Haiku 必须满足 facet 缓存命中或短会话（与 fixture `facet_cache_hint` 交叉验证）
    - [ ] `privacy_not_above_haiku`：role ∈ {privacy1, privacy2, tldr-validator, candidate-validator} 禁用 sonnet/opus
    - [ ] `writing_not_below_opus`：role ∈ {main-body, candidate-generator, neutral, final-assembly, tldr-generator} 禁用 haiku/sonnet
    - [ ] `merger_not_haiku`：role=session-merger 禁用 haiku
  - **thrashing**（无必要调用）：
    - [ ] `no_duplicate_read`：同一 `tool_input_sha256` 的 Read 在非循环语境 ≤ 2 次
    - [ ] `no_infinite_retry`：同参数连续失败 ≥ 3 次即标记
    - [ ] `no_glob_projects_root`：禁 Glob `~/.claude/projects/*`（应只消费清单）
    - [ ] `no_trivial_subagent_dispatch`：派 Agent 后内部 tool_call == 0 **且** `agent_prompt_role` 未登记 → 冗余。privacy / tldr-validator / candidate-validator 等登记角色返纯文本属合法行为，不判冗余。
- [ ] Workflow 文档读取顺序：从 trace 里 `Read` 事件提 path，按首次出现时间排序，应等于 `00→01→02→03→99`
- [ ] **隐私审查顺序语义**：privacy1 的输入 hash = main-body 输出 hash；privacy2 的输入 hash = final-assembly 输出 hash
- [ ] **窗口解析**：三路输入（`WINDOW_END=<epoch>` / `YYYY-MM-DD` / 空）断言 `BRANCH` / `WINDOW_START` / `WINDOW_END` / `WINDOW_START_ISO` / `WINDOW_END_ISO` / `TARGET_DATE`
- [ ] **环境变量 checkpoint**：每阶段进入前有 `env dump` 的 marker（SKILL.md Limitation 硬规则）

### Style

- [ ] TL;DR 字数 100–400
- [ ] TL;DR 无 session id / 无文件路径 / 无口癖词表命中（词表落 `tests/prompts/style-banlist.txt`）
- [ ] TL;DR 插入位置：frontmatter 之后、`## 概览` 之前
- [ ] TL;DR 重试三次失败降级：通知含错误清单；日报无 TL;DR 节；其他章节完整
- [ ] 思考段 jargon 检查：每句抽象词 ≤ 2（`scripts/eval/jargon-scan.py`，白名单走 `tests/prompts/jargon-allow.txt`）
- [ ] 正文 emoji 计数 = 0
- [ ] 具体度：PR 号 / 文件路径 / commit hash 合计出现 ≥ `min_specificity`
- [ ] 署名与模板段落顺序与 `reference/templates/` 对齐（diff 式比较 section 标题序列）

### Efficiency

- [ ] 总 token ≤ fixture `max_tokens`
- [ ] 每阶段耗时 P50 ≤ 基线 + 2σ（基线从历史 CI run 聚合，首次运行建立）
- [ ] TL;DR 重试次数 ≤ 1
- [ ] Candidate 生成数 ≤ 10
- [ ] 工具调用总数与历史 baseline 相比 ≤ +20%（防 thrashing）
- [ ] `facet-cache-hit` fixture 第二次运行（facet 缓存链路）：
  - [ ] `prepare-session-run.py` stderr 的 `cached_facets=` 计数 ≥ fixture session 总数 × 0.8
  - [ ] `$RUN_DIR/facet-<sid>.json` 存在且 mtime 等于 blog 缓存文件 mtime（验证走 `shutil.copy2` 路径）
  - [ ] session-reader 每次调用的 `model` 字段 == `haiku`（不是调用数下降，是档位下降）
  - [ ] session-reader 第二次 run 的 input+output token 总和 ≤ 第一次的 50%
  - [ ] phase1 卡片数量两次运行相同（验证 reader 仍产 phase1，只是 facet 不重写）

## 失败降级（从 mock `_fault` 注入）

- [ ] blog push 被 pre-receive 拒收 → 通知仍发、说明失败阶段
- [ ] facets mock remote conflict → 通知降级信息完整（"facets 推送失败 但 blog 已推"）
- [ ] codex replay timeout → 辨析降级路径，日报辨析段有 fallback 文案
- [ ] mock mails `spam_filtered` / `bounce` → 最终通知附 `$MAIL_STATUS` 原因
- [ ] apply-memory-candidates ENAMETOOLONG → 不阻塞发布，通知记录丢弃
- [ ] session jsonl 截断 → trace-parser 降级为 partial trajectory，L1 仍能判定

## Trajectory match 算法

- `exact match`：阶段顺序完全相同
- `in-order match`：所有 expected phase 都出现且相对顺序正确（允许额外 phase 插入，但不允许逆序）
- daily-report 采用 `in-order match`；额外 phase 必须在白名单内（`tests/prompts/phase-allow.txt`）

## Essential tool call 判定

- 对 tool call 的 `tool_input_sha256` 做白名单比对（同一命令不同参数视为不同 call）
- 参数签名生成：对规范化 JSON 取 sha256，路径 token 替换占位符（`${TARGET_DATE}` 等）

## 不在本 step

- LLM judge 的一切（narrative / opposing / thinking 质量打分）归 `05-structured-judge.md`
- 版本 A/B 对照归 `07-paired-eval.md`
- 基线 P50 数据采集归 `09-regression-loop.md`
