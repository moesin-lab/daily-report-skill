# daily-report skill 评测计划 v2

方法论基线参照：OpenAI *Testing Agent Skills Systematically with Evals*、LangChain *Evaluating Skills*、Phil Schmid *Practical Guide to Evaluating and Testing Agent Skills*、Databricks *AI Agent Evaluation*、arxiv 2602.12670 *SkillsBench*、本仓 skill-creator plugin。

## 设计锚点

- **四维目标**：outcome / process / style / efficiency。所有 check 挂这四维，不按"实现层"组织。
- **Trajectory 为一等公民**：主评估单元是一次完整 run 的 span/tool call 序列，不是 final markdown。
- **Trace 外部捕获**：靠 harness 吃 `~/.claude/projects/<proj>/*.jsonl` session 日志 parse，不依赖主 agent 自报 dispatch-log。
- **判分分三层**：L1 deterministic 每 PR 跑；L2 structured judge 改 prompt/rubric 跑；L3 pairwise blind 改大动作手动跑。
- **配对评估手动统一**：版本 A/B 对照不进 PR gate，集中批跑。
- **失败回灌**：真实环境失败分类后自动生成 regression fixture 草稿。
- **Mock 收窄**：只覆盖 Track B 真实环境打不到的失败形态，成功路径由真实调用验证。

## 文件索引

| 文件 | 角色 | 触发 |
|---|---|---|
| `shared.md` | 四维目标 / fixture 契约 / schema 契约 / trace-parser 契约 / 全局规则 | 全局 |
| `01-trigger.md` | 20 条 trigger eval + description 优化 | CI gate |
| `02-fixtures.md` | 6 份 pipeline fixture 实例化 | CI gate |
| `03-mock-layer.md` | 只补真实环境打不到的失败形态 mock | CI gate（窄） |
| `04-deterministic.md` | L1：trajectory + schema + regex + canary | CI gate |
| `05-structured-judge.md` | L2：Pydantic 平铺 schema + ensemble + 稳定性自检 | 改 prompt / rubric 手动触发 |
| `06-pairwise.md` | L3：baseline 冻结 + 盲 comparator + analyzer | 月粒度 / 改模型策略手动触发 |
| `07-paired-eval.md` | 版本 A/B 配对 + Δabs + Hake g + 负增益硬警告 | 手动统一跑 |
| `08-track-b.md` | 真实环境 smoke + 后发 watchdog + 周漂移 | 真实调用 / 周 cron |
| `09-regression-loop.md` | 自动失败回灌 + 长期 outcome + retirement 检测 | 常驻管道 |
| `10-user-feedback-loop.md` | 人工反馈 inbox + 四分类转换 + 效果评测 | 常驻管道 |

## 推进顺序

**Stage 0 前置锚点**（阻塞 Stage 1，不做后面全塌）：
- workflow 11 阶段入口插 `phase-markers.log` marker 指令
- 跑一次真实 run 人工验证 marker.log 齐全
- `tests/prompts/role-registry.json` 登记 10 个角色 + prompt md sha256
- trace-parser 的 prompt 指纹抓取与阶段锚定双路识别基建
- schema v2 迁移脚本（`expected-trajectory` v1→v2）
- **checkpoint 基建**：`phase-enter.sh` / `phase-exit.sh` 助手脚本、`checkpoint-{snapshot,restore,list,compat}` 四件套；workflow 每阶段的入口与出口都只调这两个助手脚本，不在阶段文档里散写判停/存档逻辑
详见 `shared.md` 的"Stage 0 前置交付"小节、"角色识别"小节、"Checkpoint & Stop-at 契约"小节。

**Stage 1 契约冻结**（并行）：`shared.md` 四维目标与契约 → `01-trigger.md` 数据集、`02-fixtures.md` 数据集、`03-mock-layer.md` 前置 mock 子集（见下）、trace-parser 实现。

**Stage 2 主 CI 路径**：`04-deterministic.md`（L1 主力）。前置依赖 Stage 0 + Stage 1 全部就绪，尤其是 `03-mock-layer.md` 的前置 fault 子集——失败降级断言每条都依赖 mock `_fault` 注入，这部分不能延后。支持 `STOP_AFTER_PHASE` 阶段子集运行：CI 可按改动范围只跑到某 phase，节省预算。

**Stage 3 手动扩展**：`05-structured-judge.md`、`06-pairwise.md`、`07-paired-eval.md`。paired-eval 默认用 checkpoint 共享未改动前序阶段，A/B 都从首个改动阶段 resume，预算约按改动范围线性摊薄。

**Stage 4 真实环境 + 盲点补漏**：`08-track-b.md` 真实调用跑通后，对仍未覆盖的失败形态（主要是远端 conflict 类真实可触发但会污染资源的）补剩余 mock。

**Stage 5 生产闭环**：`09-regression-loop.md` + `10-user-feedback-loop.md`。

## 预算

- CI gate 单次 PR ≤ 500K token（L1 + trigger）
- 手动配对评估 ≈ 1.5M token（每 PR 不跑，版本合入主干前集中跑）
- Track B 周 smoke ≈ 当量一次正式日报

## Workspace 位置

- 测试实现与 fixture 落 `~/.claude/skills/daily-report/tests/` 和 `~/.claude/skills/daily-report/evals/`
- 迭代工作区（iteration-N / eval-viewer 产物）落 `~/.claude/skills/daily-report/evals/workspace/`，对齐 skill-creator 生态
- 本目录 `.tasks/daily-report-eval/` 只放计划文档，不含代码

本目录仅计划，未实施。
