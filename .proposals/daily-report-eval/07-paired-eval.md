# Step 07 — 版本 A/B 配对评估（手动统一跑）

前置：`04` / `05` / `06` 都已建立。**不进 PR gate**，由人工在版本合入主干前集中批跑。

方法学锚点：SkillsBench 的 paired evaluation（with/without skill）范式改造——daily-report 没有 "no skill" baseline，改为**版本配对**（main 版 vs 本 PR 版），同时报 `Δabs`（绝对差）和 Hake `g = (B − A) / (1 − A)`（归一增益）。

## 为何独立一步

- 手动统一跑避免每 PR 重复烧 1.5M token
- Δabs 单看会被 ceiling 蒙蔽（A 已经 0.95，B 升到 0.97 的含金量 ≠ 0.50 升到 0.52）；g 单看又会被 0/1 边界放大；两者必须并列
- 多 trial（N=3）给方差而非点估计，对齐 Schmid 的"3–5 trial 看分布"

## 执行入口

单命令收口，`scripts/eval/paired-run.sh`：

```bash
paired-run.sh \
  --a-ref main \
  --b-ref HEAD \
  --fixtures typical-day,heavy-day,boundary-tz,privacy-canary,facet-cache-hit,empty-day \
  --trials 3 \
  --layers L1,L2 \
  --resume-from-unchanged \
  --out workspace/paired-<ts>/
```

内部：两 ref 各自 checkout 到隔离 worktree → 共用 fixture + seed + trace-parser → 各跑 N=3 trial → 同一份 judge 配置评 L2 → 汇总。

### Checkpoint 加速（`--resume-from-unchanged` 默认开）

paired-run 调 `scripts/eval/checkpoint-compat.py` 比对 A 与 B 的 git diff：

1. 算出 B 相对 A 改动的文件集合
2. 查每个文件落在哪些 phase 子树（`tests/prompts/phase-ownership.json` 维护映射，例如 `reference/workflows/02-write-review/00-main-body.md` 属 `main-body`；脚本 `scripts/session/*` 属 `session-pipeline`；等等）
3. 找到改动触及的**最早 phase** `P_first`
4. A 先从头跑到结束，`CHECKPOINT_EVERY=1` 产出完整 checkpoint 链
5. 同 fixture 的 B 全部 trial 都 `RESUME_FROM_PHASE=P_first` 起跑，共享 A 的前序 checkpoint（通过 `CHECKPOINT_SOURCE=<A-run>/checkpoints/`）
6. 若改动触及 `cross-phase` 资源（`shared.md` / trace-parser / role-registry）→ 禁用 checkpoint 加速，B 也从头跑

预算估算对比：

- 无 checkpoint：A + B 各 N trial × 全流程，约 2N × 单次日报成本
- 有 checkpoint、改动在 `main-body` 之后：A 全流程 N + B N trial × (main-body..publish)；session-pipeline 占典型日报 ~40% token，节省约 20–35%
- 改动在 `tldr` 末端：节省约 50–60%

若 B 的 L1 Process 断言在共享前序阶段失败 → 说明 checkpoint 兼容性判断有误（A 某 phase 产物对 B 不再合法），本次自动退到无 checkpoint 模式重跑并在报告标记。

### Recap spot-check（对齐 `shared.md` Recap 契约）

因为 recap 不是字节级 context 还原，paired-run 每次额外抽 **20% 的 fixture** 做对照：

- 正常组：B 按 `--resume-from-unchanged` 走 recap 路径
- 对照组：同 B 从头跑（无 checkpoint）
- 两组 L1 pass_rate / Process 断言逐条比较
- 差异 > 5% → 本次 paired-run 禁用 checkpoint 加速、所有 B trial 重跑；差异持续 2 次 → 在 `shared.md` Recap 契约下标 warning，可能需要补 `phase-notes` 的覆盖度

spot-check 的额外预算计入 paired-run 总预算，约抵消 checkpoint 节省的 1/5。

## 采集指标

每一维度独立成表，不混合求总分：

| 维度 | 指标 |
|---|---|
| Outcome | pass_rate（L1 outcome 子集通过率） |
| Process | trajectory_match_rate（阶段顺序 + essential tool call + 模型策略全过的 run 占比） |
| Style | style_pass_rate + rubric style 维度 score |
| Efficiency | `total_tokens` mean ± stddev、阶段耗时 P50 |
| 主观 | L2 rubric 6 维 score；L3 winner ratio（若跑了 L3） |

## 报告格式（借 skill-creator benchmark.json schema）

落 `workspace/paired-<ts>/benchmark.json`，直接复用 skill-creator `aggregate_benchmark.py` 的 schema。`configuration` 两档：`version_a` / `version_b`。

额外 `delta` 块里并列两字段：

```json
"delta": {
  "pass_rate": {"abs": "+0.05", "hake_g": "+0.25"},
  "tokens":    {"abs": "+12000", "hake_g": null},
  "latency":   {"abs": "-8s",    "hake_g": null}
}
```

Hake g 只对 `[0,1]` 区间的指标（pass_rate / trajectory_match_rate / style_pass_rate）计算，其他指标 `hake_g: null`。

## 负增益硬警告

对每个 fixture、每个维度独立判：

- B 比 A 低 > 10pp → PR 描述必须有显式解释；没有解释 → 阻塞合入
- B 比 A 低 > 5pp 且没 fixture 侧解释 → warning，不阻塞但标注

和 SkillsBench 观察一致：skill 对部分任务可能是负作用，配对评估就是要把这个暴露出来。

## Viewer 复用

走 skill-creator `eval-viewer/generate_review.py`：

```bash
nohup python ~/.claude/plugins/marketplaces/claude-plugins-official/plugins/skill-creator/skills/skill-creator/eval-viewer/generate_review.py \
  workspace/paired-<ts>/ \
  --skill-name daily-report \
  --benchmark workspace/paired-<ts>/benchmark.json \
  --static workspace/paired-<ts>/review.html
```

人工对照两版产物 + benchmark，有疑义时去 `06-pairwise.md` 的 analyzer 报告查因。

## 合入决策

综合三层，人工拍板但有默认规则：

- L1 四维都至少持平（任一 fixture 任一维度负增益 ≤ 10pp，且总和 Δabs ≥ 0） → 可合
- L1 任一维度 > 10pp 负增益 → 必须在 PR 正文写解释 + 补 fixture 或接受为 tradeoff
- L2 有维度 score 下降 > 10 分 → 看 analyzer，可能需要 rerun L3 盲比
- L3 B 赢不足 2 对 → 延期合入

## 频率

- 每个涉及 skill 主体改动的 PR 在合入前跑一次
- 月度体检跑一次（即便没改动，防止外部环境漂移）
- 换模型版本（Opus 升级等）跑一次

## 不在本 step

- L1 单版产物合法性校验归 `04`
- L2 rubric 稳定性自检归 `05`
- L3 盲判本身归 `06`
- 基线 P50 数据采集归 `09-regression-loop.md` 的 outcome 采集链
