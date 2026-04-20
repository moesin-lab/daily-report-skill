# Step 09 — 自动失败回灌 + outcome 采集 + retirement 检测

常驻管道，不是一次性。三件事一起管：Track B 失败沉淀为 Track A fixture、长期 outcome 采集、skill 淘汰检测。

人工反馈路径（用户显式反馈、post-publish diff、memory 新增）归 `10-user-feedback-loop.md`，不在本 step。两条路径共用 `tests/fixtures/regressions/` 存储，不共用触发器。

## 失败回灌管道

### 触发条件

`08-track-b.md` 五类分类中：
- `api_breaking` 连续 ≥ 2 次 → 触发
- `content_reject` 连续 ≥ 2 次 → 触发
- `rate_limit` / `transient_network` → 不触发（外部因素，不是 skill bug）
- `unknown` 连续 ≥ 3 次 → 触发（升级为需要人工分类）

### 回灌步骤

1. `scripts/eval/regression-draft.py` 读 `~/.claude/.tasks/eval-b-failures/<ts>/` 原始响应 + 日报产物
2. 自动生成 `tests/fixtures/regressions/<ts>/` 草稿：
   - `raw/*.jsonl`：取失败当天的 session（脱敏）
   - `expected.json`：从失败模式反推必过断言（例如：若失败是 TL;DR 重试超限，`expected.json` 要求 TL;DR 三次降级路径正确）
   - `expected-trajectory.json`：同上
3. 自动推 issue draft 到 `~/.claude/.tasks/eval-b-issue-drafts/<ts>.md`
4. 人工审 → 合入 CI 集 → 以后 L1 永久覆盖这一失败形态

### 永不删除

Regression fixture 一旦合入就冻结，不删只降级；保证老问题不回归。

## Outcome 采集（四维长期基线）

每次 CI run 与每次 Track B run 都采集，落两处：

- Track A → `tests/eval-mock/metrics.jsonl`（append）
- Track B → `~/.claude/.tasks/eval-b.db`（sqlite）

共用字段（对齐四维）：

```
ts, track, run_id, skill_version (git sha), fixture_name,
outcome_pass_rate, process_trajectory_match, style_pass_rate,
total_tokens, phase_durations_p50_json,
judge_scores_json (L2 跑了才有),
pairwise_winner (L3 跑了才有),
notes
```

### 基线建立与漂移监控

- 连续 14 天（Track B）或 50 次 run（Track A）后算各维 P50 / P90
- 偏离基线 2σ 告警
- 月度出一份趋势图（简单 `matplotlib` 脚本，单文件）

### Retention

- `metrics.jsonl` 按月 rotate，旧月份 gzip 后归档到 `tests/eval-mock/metrics-archive/`
- `eval-b.db` 不 rotate，100MB 触发告警（人工决定是否 vacuum）
- `eval-b-failures/` 保留 30 天，过期自动清（cron 单独 job）

## Post-publish diff watchdog（Track B 独占）

- 正式日报发布 24h 内，markdown git diff 行数 > 30 → 告警到主 DM
- 这是"事后修改量"的隐含质量信号，反映 L1/L2 没抓到的问题
- 连续 3 周触发 → 说明 L1 / L2 rubric 有盲区，回 `04` / `05` 加断言

## Skill retirement 检测（Schmid 独家方法）

季度一次，验证"这 skill 是否还有存在价值"：

1. 临时把 `SKILL.md` 的 description 改成"停用"（或卸掉 skill）
2. 用主力模型直接跑 trigger eval + typical-day fixture 的生成任务
3. 如果**无 skill 时也能全过**：说明底层模型已经学会这套 SOP，考虑退役
4. 如果**掉分严重**：skill 仍是刚需
5. 结论落 `~/.claude/.tasks/eval-b-retirement/<quarter>.md`，不自动删 skill

## 预算与异常

- Regression 回灌每次消耗 < 5K token（纯文件操作 + LLM 只用于草稿注释）
- Outcome 采集 0 额外 token（从现有 run 落盘就够）
- Retirement 季度检测 ≈ 一次 Track B 的量，计入季度预算

## 不在本 step

- 分类本身归 `08-track-b.md`
- 回灌进 fixture 后的断言形式归 `02-fixtures.md` / `04-deterministic.md`
- pairwise A/B 对照归 `07-paired-eval.md`
