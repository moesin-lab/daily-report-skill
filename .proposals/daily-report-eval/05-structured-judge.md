# Step 05 — L2 Structured Judge

前置：`04-deterministic.md` 全绿。手动触发类：改 prompt / rubric / 模型策略才跑。

目标：把"日报读起来怎么样"变成可 diff 的结构化分数，避免 judge 自由文本漂移。

## Judge 输出 schema（Pydantic 平铺式）

采纳 Phil Schmid 范式，每个维度独立字段，便于时序 diff。位置 `tests/schemas/judge-verdict.v1.json`，对应 Pydantic：

```python
class DimensionResult(BaseModel):
    passed: bool
    score: int              # 0-100
    notes: str              # 1-3 句，要点式

class JudgeVerdict(BaseModel):
    overall_pass: bool
    overall_score: int      # 0-100
    narrative: DimensionResult
    opposing: DimensionResult
    thinking: DimensionResult
    tldr: DimensionResult
    privacy_residual: DimensionResult   # 补 L1 canary 之外的隐式识别
    style_coherence: DimensionResult    # 模板 / 口癖 / 署名连贯
    schema_version: int = 1
```

Judge 走 **Anthropic SDK 的 tool-use 强制输出**（不是 OpenAI 的 `response_format`）：

- 定义一个虚拟 tool `submit_judge_verdict`，`input_schema` = `JudgeVerdict.model_json_schema()`
- 调用 `client.messages.create(tool_choice={"type": "tool", "name": "submit_judge_verdict"}, tools=[...])` 强制模型只能通过 tool-use 回答
- 解析 `response.content[0].input` 即为严格 schema JSON
- 任何非 tool-use 回答或 schema validation 失败都直接算 judge 失败，不重试

Judge 端实现 stub 放 `scripts/eval/run-judge.py`，每次 rubric 改动跑一次 dry-run 验证 tool-use 路径不回退。

## Rubric 文本

落 `tests/prompts/judge-rubric.md`，每维度一节。节内结构固定：
- **目的**：这一维度追什么
- **pass 条件**：若干 bullet，完全可操作
- **常见扣分点**：3–5 条
- **score 锚点**：90+ / 70-89 / 50-69 / <50 的行为描述

禁止在 rubric 里写"质量好坏"这种空词；必须用具体行为描述。

## 模型与采样

- Judge 模型：Claude Opus 4.7（与生产 main-body 同档，避免 judge 比 generator 弱）
- Ensemble N=3，同 prompt 跑 3 次，`overall_score` 取中位，各维 `passed` 取多数票
- 温度：0

## 稳定性自检（门槛硬规则）

每次 rubric 改动后必须跑一遍自检，不过关禁止合入：

- **同样本两次一致率 ≥ 80%**：抽 10 份 baseline 产物，N=3 ensemble 跑两轮，比 overall_pass 一致率
- **维度方差 ≤ 阈值**：每维度 N=3 内部分数 stddev ≤ 8 分
- **判决稳定性回归**：新 rubric vs 旧 rubric 在 baseline 上对比，overall_pass 翻转率 < 15%，否则要在 PR 里解释

阈值不达标 → rubric 收紧（加具体行为描述），不是重跑 judge。

## 输出落盘

- 每次 run 产 `tests/eval-mock/judge-verdicts/<run-id>.json`（严格 schema）
- `scripts/eval/judge-diff.py` 对比任意两次 run，按维度画出 score 差

## 触发条件

- `SKILL.md` 或 `reference/prompts/` 修改
- 模型策略调整（session-reader 升降级、main-body 换模型）
- Rubric 文件本身改动
- 手动触发：`run paired-eval --with-judge`

不改 prompt 的 PR 不跑。

## 不在本 step

- 盲 A/B 对比归 `06-pairwise.md`
- Judge 采集到的分数如何汇总成"这次改动是否回归"归 `07-paired-eval.md`
