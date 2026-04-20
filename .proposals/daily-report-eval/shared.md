# 共用契约

所有 step 文件默认遵守本文；冲突以本文为准。

## 四维目标

每条断言必须挂在其中一维，否则不写。

### Outcome

- blog 主仓 ref / facets submodule ref 推送成功（Track B 真实、Track A mock 验证）
- markdown / facets / cards / memory 落盘且 schema 合法
- 邮件投递成功、cc-connect 通知送达
- 隐私 canary 零泄漏（fixture 埋点不出现在任一产物）

### Process

- 11 阶段按顺序跑：`bootstrap · session-pipeline · main-body · privacy1 · opposing · neutral · candidates · final-assembly · privacy2 · tldr · publish`
- essential tool call 覆盖：`publish-blog.sh` / `publish-artifacts.sh` / `send-email.sh` / `send-telegram-opposing.sh` / `send-cc-notification.sh` / `apply-memory-candidates.py` / `session-reader` / `session-merger` 全部至少一次
- sub-agent 模型策略合规：`privacy1/privacy2/tldr-validator/candidate-validator` = Haiku；`main-body/candidate-generator/neutral/final-assembly` = Opus；`session-reader` 默认 Sonnet（允许显式降级到 Haiku + 显式升级拒绝到 Opus）；`session-merger` = Sonnet，可升 Opus
- 主 agent 在 session pipeline 后不读 raw jsonl（负向断言）
- workflow 文档读取顺序：00→01→02→03→99（跟当前 SKILL.md `References` 对齐）

### Style

- TL;DR 100–400 字 / 无 session id / 无文件路径 / 无口癖词表命中
- 思考段每句抽象词 ≤ 2（`feedback_daily_report_jargon.md` 规则）
- 署名与模板段落顺序与 `reference/templates/` 一致
- 日报正文 emoji 计数 = 0
- 具体度下限：PR 号 + 文件路径 + commit hash 出现次数 ≥ fixture 约定 `min_specificity`

### Efficiency

- 总 token ≤ fixture `max_tokens`
- 每阶段耗时 P50 不超基线 + 2σ
- TL;DR 重试次数 ≤ 1（三次降级路径另测）
- candidate 生成条数 ≤ 10
- 工具调用总数与 baseline 相比不超 +20%（防 thrashing）

## Fixture 契约

```
tests/fixtures/<name>/
  raw/*.jsonl             # Claude Code session jsonl 替身（真实格式）
  github-events.jsonl     # GitHub 事件快照
  memory-snapshot/        # memory 目录快照（供 privacy canary 与 apply 验证）
  expected.json           # 元数据 + 必含 section + schema 期望 + 四维阈值
  expected-trajectory.json # L1 trajectory 断言（阶段顺序 / essential tool call / 负向断言）
  codex-replay.txt        # 反方路径回放（Track A 用）
  schema_version          # 文件，单行整数
```

`expected.json` 必含字段：`target_date` / `window_end_epoch` / `must_have_sections[]` / `min_specificity` / `max_tokens` / `privacy_canaries[]` / `facet_cache_hint`（none / miss / hit）。

Fixture 分集：
- Track A = `tests/fixtures/pipeline/<name>/`
- Regression 回灌 = `tests/fixtures/regressions/<ts>/`
- Track B 不共用 Track A fixture

Schema 不兼容变更必须同步 bump `schema_version` 并写 migration test；回放测试：取历史 session-reader 产出用当前 `aggregate-facet.py` 消费一遍。

## Schema 契约

```
tests/schemas/facet.v1.json
tests/schemas/card.v1.json
tests/schemas/candidate.v1.json         # thinking / suggestion / memory 三变体
tests/schemas/judge-verdict.v1.json     # L2 judge 输出
tests/schemas/pairwise-verdict.v1.json  # L3 盲比输出
tests/schemas/trigger-eval.v1.json      # 01-trigger 用例结构
tests/schemas/expected-trajectory.v2.json   # v2 把 negative_assertions 从字符串数组升为四类对象（bypass/phase_overstep/model_policy/thrashing）；角色字段从 subagent_type 改为 agent_prompt_role
tests/prompts/role-registry.json            # 10 个角色 + prompt md 路径 + sha256（Stage 0 交付）
tests/prompts/banlist-exceptions.json       # L1 style banlist 历史豁免清单
```

所有改动联动改下游 + 迁移测试；不用 git 历史推断版本。**`expected-trajectory` v1→v2 迁移脚本列为 Stage 1 必交付物**（老 fixture 按 v1 写的要一键转 v2，或在 Stage 1 期间重写成 v2 格式，不允许 v1/v2 并存）。

## Trace-parser 契约

外部 parser（非主 agent 自报）：

- 位置：`scripts/eval/trace-parser.py`，stdlib only
- 输入：`~/.claude/projects/<proj>/<session-id>.jsonl`（官方 transcript 格式）
- 输出（stdout JSONL，一行一 span）：
  ```
  {ts, span_type, name, model, subagent_type,
   agent_prompt_sha256, agent_prompt_role,
   tool_name, tool_input_sha256, tool_output_sha256,
   status, input_tokens, output_tokens, duration_ms,
   parent_span_id, span_id, phase}
  ```
- 能识别：
  - 主 agent 自身的 tool_use / tool_result、模型字段、每段 token
  - sub-agent dispatch（`Agent` tool 调用 + 回传）；**所有 Claude 子 agent 的 `subagent_type` 均为 `general-purpose`**（见 `reference/workflows/02-write-review/README.md:9`），角色不能从 `subagent_type` 推断
  - 阶段边界（由 pipeline 写入 `$RUN_DIR/phase-markers.log`，见 Stage 0 契约）

### 角色识别（prompt 指纹 + 阶段锚定）

因为 `subagent_type` 无区分力，L1 所有涉及"子 agent 角色"的断言统一走两路并存的识别策略：

1. **prompt_sha256 白名单**：parser 抓每次 Agent 调用的 prompt 文本中**第一次出现的 workflow/prompt md 引用路径**（例如 `reference/workflows/02-write-review/00-main-body.md`、`reference/prompts/privacy-review.md`），按规范化路径算 sha256；与 `tests/prompts/role-registry.json` 做白名单匹配得到 `agent_prompt_role`。
2. **阶段锚定**：对落在某 phase 内的 Agent 调用，结合 `phase-markers.log` 边界作为冗余识别（例如 phase=privacy1 内的 Agent 调用默认角色 `privacy1`）。两路不一致时报 infra-warning（不直接判 fail，但在报告里必须显示）。

`role-registry.json` 至少登记 10 个角色：
`main-body / privacy1 / privacy2 / opposing-script / neutral / candidate-generator / candidate-validator / final-assembly / tldr-generator / script-exec`，每个角色绑 ≥1 个 workflow/prompt md 的规范化路径 + sha256；未登记路径视为"未知角色"。

### 阶段边界采集

走**磁盘 marker 文件**而不是 log 扫描：pipeline 每个阶段进入前执行：

```
printf '%s|%s\n' "<phase-id>" "$(date +%s.%N)" >> "$RUN_DIR/phase-markers.log"
```

`<phase-id>` 取 11 个固定值：`bootstrap / session-pipeline / main-body / privacy1 / opposing / neutral / candidates / final-assembly / privacy2 / tldr / publish`。

parser 合并 marker 和 span 得到 11 阶段 `begin_ts`/`end_ts`，并为每个 span 反查归属 `phase` 字段。

### Stage 0 前置交付（阻塞 Stage 1）

以下在 Stage 1 开始前必须完成，否则 parser 拿不到锚点，L1 Process/Efficiency 断言会大面积 skip 或假绿：

- [ ] `reference/workflows/00-bootstrap.md` / `01-session-pipeline/*.md` / `02-write-review/*.md` / `03-publish-notify.md` 每个阶段入口加一行 `printf` marker 指令；共 ≥ 11 处
- [ ] 跑一次真实 skill 产出 `phase-markers.log` 并人工验证 11 行齐全、时序正确
- [ ] `tests/prompts/role-registry.json` 落盘，覆盖上述 10 个角色 + 每角色 prompt md 路径 + sha256
- [ ] parser infra-failure sanity check：`phase-markers.log` 行数 < 11 或缺任一 phase-id，整次 run Process 维度直接判 `infra-failure`，不跑后续断言、不给 pass
- [ ] **Checkpoint 基建**（见下节）：workflow 每阶段入口判 `STOP_AFTER_PHASE`、结束时判 `CHECKPOINT_EVERY` 存档；bootstrap 支持 `RESUME_FROM_PHASE` 解包复用；`scripts/eval/checkpoint-{snapshot,restore,list,compat}.sh` 落盘
- [ ] **Recap 基建**（见 Recap 契约节）：每阶段文档末尾加"写 phase-notes"约束；`scripts/eval/emit-resume-brief.sh` 落盘；bootstrap 的 resume 分支加读 recap-brief + 产物清单的动作

所有 L1 过程断言（11 阶段顺序、essential tool call、模型策略、阶段越界、负向断言）都消费 parser 输出，不消费主 agent 自报。

## Checkpoint & Stop-at 契约

评测 harness 的核心降耗机制。目标三件事：调某阶段断言时不用跑完整 pipeline、paired-eval 共享未改动阶段的产物、出 bug 时能精确停在断点看中间态。

### 环境变量

| 变量 | 语义 | 默认 |
|---|---|---|
| `STOP_AFTER_PHASE` | 跑完这个 phase 后立即 `exit 0`（不走后续 phase），11 个 phase-id 任一 | 空 = 跑完全流程 |
| `RESUME_FROM_PHASE` | 从这个 phase 开始；bootstrap 负责把对应 checkpoint 解包到 `$RUN_DIR`，前置 phase 的 marker 也要回填到 `phase-markers.log` | 空 = 从头开始 |
| `CHECKPOINT_DIR` | checkpoint 存档根目录 | `$RUN_DIR/checkpoints/` |
| `CHECKPOINT_EVERY` | `1` = 每阶段结束自动 snapshot；`0` = 仅 `STOP_AFTER_PHASE` 命中时 snapshot | CI 默认 `1`，生产默认 `0` |
| `CHECKPOINT_SOURCE` | resume 时指向外部 checkpoint 目录（跨 run 复用）；与 `CHECKPOINT_DIR` 互斥 | 空 |

### 存档布局

`$CHECKPOINT_DIR/<phase-id>/` 每阶段一目录，含：

- `run-dir.tar.zst`：该阶段结束时 `$RUN_DIR` 的完整快照（排除 `raw/*.jsonl` 这类超大输入，排除清单走 `scripts/eval/checkpoint-exclude.txt`）
- `env.json`：该阶段结束时所有 `$WINDOW_*` / `$SESSION_*` / `$MAIN_BODY` / `$OPPOSING_OK` 等导出变量的快照
- `phase-markers.log.snapshot`：该阶段前所有 marker 的追加拷贝（resume 时回填用）
- `meta.json`：`{phase, ended_at_epoch, skill_sha, fixture_name, parent_checkpoint_sha}`
- `resume-brief.md`：**主 agent 对话 context 的替代品**，见下节

目录名与 11 个 phase-id 一一对应；同一 phase 重复 snapshot 覆盖前者。

### Recap 契约（对话 context 的轻量替代）

Anthropic 原生不支持 Claude 对话从任意中点分叉 resume（`claude --resume <sid>` 只能从 session 末尾继续且不支持跨 skill 版本复用）。因此 checkpoint 不追求字节级 context 还原，改用 **recap 文件 + 产物清单 + prompt caching** 让 resume 后的主 agent "读完就能接着干"。

**`resume-brief.md` 结构**（phase 出口时由 skill 侧 `scripts/eval/emit-resume-brief.sh <phase>` 生成，≤ 200 行）：

```markdown
# Resume Brief — <phase> 阶段已完成

## 关键结论
<3-5 条主 agent 本阶段得出的口头性判断，例如"今天主题是 cc-connect cron bug 复盘"、"empty-day 分支已命中"；脚本从 `$RUN_DIR/phase-notes/<phase>.md` 读取，该文件由阶段文档要求主 agent 在阶段末尾写 1-3 段要点>

## 下个阶段必读输入
- `$RUN_DIR/main-body.md`（上个阶段产物）
- `$RUN_DIR/phase-markers.log`（含前序阶段时间戳）
- `$OPPOSING_CONTENT`（如存在）
- `$SESSION_CARDS_FILE`

## 环境变量快照
见同目录 `env.json`；source 后就地可用。

## 下一个该做什么
读 `reference/workflows/<next-phase>.md` 并按该文档执行。
```

**Skill 侧的配合动作**（Stage 0 前置交付）：

- 每个 workflow 阶段文档末尾加一句约束："本阶段结束前必须把本阶段的关键判断 append 到 `$RUN_DIR/phase-notes/<phase>.md`（1-3 段要点，仅口头结论，不复述产物）"
- `phase-exit.sh` 除了跑 `checkpoint-snapshot.sh`，也跑 `emit-resume-brief.sh` 生成该 phase 的 recap
- 如果 `phase-notes/<phase>.md` 缺失 → recap 退化为只含产物清单，不阻塞 checkpoint（但在 `meta.json` 里标 `recap_degraded: true`）

**Resume 时主 agent 的动作**：

`00-bootstrap.md` 在 `RESUME_FROM_PHASE` 分支下，除了解包 checkpoint，还必须：

1. Read `$RUN_DIR/../checkpoints/<prev-phase>/resume-brief.md`
2. Read `env.json` 中列出的关键产物（通常 3-5 个文件）
3. 跳到 `$RESUME_FROM_PHASE` 对应 workflow 文档继续

因为这些文档在 prompt caching TTL 内会命中 cache，重播 prefix 的代价接近零。非 cache 命中时也就是一次完整 SKILL.md + workflow 文档的 input token（~10-20K），比整条 pipeline 小两个数量级。

### 不完整 context 的已知损失

- 主 agent 之前对 session 内容的"未落盘的判断"会丢失（这正是 `phase-notes/` 要捕获的部分）
- 主 agent 对用户对话历史的感知丢失（但 daily-report 本就不应依赖这个，此前已有 feedback 明确"日报读者只是 SentixA 本人"）
- 如果 skill 中途改了 `SKILL.md` 或 workflow 文档 → resume 后主 agent 读的是新版，与 checkpoint 时的 context 不一致；这正是 `checkpoint-compat.py` 要拦住的场景，不兼容 → infra-failure

上述损失评测层面可接受：`07-paired-eval.md` 在 checkpoint 共享前序阶段时会跑一次 "无 checkpoint 对照 run" 作为 spot-check（抽样 20% 的 fixture），对比 L1 断言结果，若共享 checkpoint 导致的 pass 差异 > 5% 则禁用 checkpoint 加速。

### Skill 侧配合

workflow 每个阶段的入口与出口各加一行：

```
# 入口（写 marker 之后）
if [ -n "$STOP_AFTER_PHASE" ] && [ "$(python3 -c 'import sys; ph=sys.argv[1:];print(ph.index(sys.argv[1]))' "<phase>" <phase-list>)" -gt "$(python3 -c '...' "$STOP_AFTER_PHASE" <phase-list>)" ]; then exit 0; fi

# 出口
if [ "$CHECKPOINT_EVERY" = "1" ] || [ "$STOP_AFTER_PHASE" = "<phase>" ]; then
  bash scripts/eval/checkpoint-snapshot.sh "<phase>"
fi
```

实际实现封装到两个助手脚本：`phase-enter.sh <phase>`（写 marker + 判停）、`phase-exit.sh <phase>`（判存档）。每个阶段文档里只调这两个脚本，避免 11 份文档各写一版。

### Resume 路径

`00-bootstrap.md` 开头检测 `RESUME_FROM_PHASE`：

```
if [ -n "$RESUME_FROM_PHASE" ]; then
  bash scripts/eval/checkpoint-restore.sh "$RESUME_FROM_PHASE"
  # 该脚本：找到上一个 phase 的 checkpoint → 解包 run-dir.tar.zst 到 $RUN_DIR → source env.json → 追回 phase-markers.log.snapshot
fi
```

Resume 后 skill 继续从 `$RESUME_FROM_PHASE` 的入口走。Checkpoint 缺失或 `meta.skill_sha` 与当前不符 → `exit 1 (infra-failure)`，不静默回退。

### 不变量

- Checkpoint 只复用**前序未改动阶段**的产物。判定条件：`checkpoint.meta.skill_sha` 与当前 `skill_sha` 相同，或所有改动文件与 `<phase>` 所在子树不相交（由 `scripts/eval/checkpoint-compat.py` 判）。不满足 → 必须重跑前序阶段。
- `phase-markers.log` 在 resume 场景必须连续；断点前的 marker 来自 `.snapshot`，断点后由 skill 继续追加。parser 对此透明。
- `role-registry.json` 的 prompt sha256 在 resume 时重算一次并与 snapshot 里的比对；不一致 → infra-failure。

### 失败兜底

- `checkpoint-snapshot.sh` 失败不阻塞后续阶段（只记 warning），避免打断长 run
- `checkpoint-restore.sh` 失败必须 `exit 1`，不允许部分解包继续跑
- `STOP_AFTER_PHASE` 命中后即便 `checkpoint-snapshot.sh` 失败，进程也应退出码 0，避免 CI 误判 stop 为失败

## 回灌契约

两条路径共用 `tests/fixtures/regressions/` 存储，不共用触发器：

**自动路径**（`09-regression-loop.md`）：
- Track B 失败分类五类：`api_breaking` / `rate_limit` / `transient_network` / `content_reject` / `unknown`
- `api_breaking` + `content_reject` 连续 ≥ 2 次 → 自动生成 `tests/fixtures/regressions/<ts>/` 草稿 + 推 issue draft
- 人工审过 → 搬入 CI 集（挂 L1）

**人工反馈路径**（`10-user-feedback-loop.md`）：
- 用户显式反馈 / post-publish diff watchdog / feedback memory 新增 → 入 `evals/feedback-inbox/`
- 分类 A/B/C/D → 产 fixture / banlist / rubric / 硬规则
- 闭合前必须走 `07-paired-eval.md` 证明修复

Regression 永不删除，只降级（失败 → 修复 → 下沉为冻结 regression）。

## 全局规则

- stdlib only；pytest 是唯一外部依赖（容器已装 `python3-pytest`）
- 目录布局：`tests/` 与 `scripts/session/` `scripts/review/` `scripts/eval/` 并列；`tests/{fixtures,schemas,baselines,prompts,eval-mock}` 五个固定子目录
- CI gate 粒度：改 `~/.claude/skills/daily-report/**` 或 `~/.claude/agents/session-*.md` 触发；改 `scripts/eval/**` 或 `tests/**` 也触发
- 调用层 vs 产物层分离：调用层只验"是否被调用 + 参数签名"（消费 mock state 和 trace parser）；产物层只看 markdown / facets / cards / memory
- 工作目录默认 `~/.claude/skills/daily-report/`，CI 在 checkout 后 `rsync` 到该路径执行
- 失败信号严禁掩盖；L1 全绿不代表 L2/L3/Track B 合格
