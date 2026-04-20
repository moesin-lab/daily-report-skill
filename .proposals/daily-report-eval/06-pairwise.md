# Step 06 — L3 Pairwise Blind

前置：`05-structured-judge.md` 稳定跑过 2 周。月粒度 / 改模型策略 / 改 skill 主体结构时手动触发。

目标：排除 rubric 漂移带来的分数错觉，直接让 judge 盲看 "A 更好还是 B 更好"。借 skill-creator `agents/comparator.md` + `agents/analyzer.md` 的基建，不重造。

## 触发场景

- 改 `SKILL.md` 主体章节或 workflow 阶段顺序
- 改 Opus / Sonnet 用量（main-body / neutral / final-assembly）
- 月度回归体检
- 任何 L2 判定"维度方差增大但 overall 没动"的可疑情况

## Baseline

冻结 3 份真实一天日报，落 `tests/baselines/`；每份含完整产物（markdown / facets / cards）。季度刷新，旧 baseline 降级为历史对比集不删。

## 流程

1. 同一 fixture（以 baseline 当天为准）跑当前版产出 B
2. 随机打乱 A/B 标签，喂给 comparator（走 `skill-creator/agents/comparator.md`）
3. Comparator 输出 `comparison.json`，schema 已由 skill-creator 定义（`winner` / `reasoning` / `rubric` / `expectation_results`）
4. Analyzer 读 transcript + comparator 结论，产 `analysis.json`：winner_strengths / loser_weaknesses / improvement_suggestions

## Judge 配置

- 模型：Opus 4.7
- 温度 0；ensemble N=3 取多数（3 个 judge 对 winner 投票）
- 严格只判 **winner / tie / B_better**，不做绝对评分
- 每轮 3 对对比（3 份 baseline 各一对）

## 判定规则

- 3 对中 ≥ 2 对 B 赢 → 合入
- ≥ 2 对 A 赢 → 阻塞，回 `05-structured-judge.md` 定位差在哪一维
- 1 赢 1 平 1 输 → 看 analyzer 细节决定

## 稳定性自检

- 随机再做一次全盲（A/B label 再随机一次），3 judge 多数结果翻转率 ≤ 15%
- 月度抽一对人工复核，和 judge 结论对比记一致率（非门槛，是趋势监测）

## 输出

- `tests/eval-mock/pairwise/<ts>/comparison-*.json`
- `tests/eval-mock/pairwise/<ts>/analysis.json`
- 聚合报告喂 `07-paired-eval.md` 的 harness 一起展示

## 不在本 step

- 版本合入与否的最终判定归 `07-paired-eval.md`（综合 L1 / L2 / L3 + Hake g）
- Judge 本身的稳定性验证归 `05-structured-judge.md`
