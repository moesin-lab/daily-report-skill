# Step 01 — Trigger eval（20 条 CI 子集）

前置：`shared.md` 的 schema 契约。CI gate，最高杠杆点：skill description 决定是否触发。

## 数据集

20 条，分布：10 正样本 + 10 负样本（含至少 5 条 near-miss）。

### 正样本 10 条（`should_trigger=true`）

覆盖四类，每类 2–3 条：

- **Explicit**：直接点名。例："写今天的日报"、"生成 2026-04-17 的日报"、"daily report for today"。
- **Implicit**：描述场景不点名。例："今天干了啥整理一下发博客"、"总结我今天的 Claude Code 会话并推"。
- **Contextual**：带真实上下文噪声。例长度 2–5 行，含文件路径、具体会话主题、用户个人情境。
- **Uncommon**：罕见但合法入口。例："`WINDOW_END=1745251200` 跑一份"、"把昨天的补一份"。

### 负样本 10 条（`should_trigger=false`）

- **Near-miss**（≥5 条）：语义相邻但不该触发。例："总结一下刚才这个会话"（单会话 handoff 不是日报）、"帮我写一份周报"、"复盘一下 cc-connect 那个 bug"、"/memory 加一条"、"把今天的 PR 列表发邮件"。
- **Irrelevant**（≤5 条）：硬负样本。例："把这段代码改成 ts"、"解释一下 go 的 channel"。硬负样本占比不超过一半，主力是 near-miss。

## 数据集文件

位置：`~/.claude/skills/daily-report/evals/trigger-eval.json`，schema 见 `tests/schemas/trigger-eval.v1.json`。

```json
[
  {"id": "t01", "query": "...", "should_trigger": true, "class": "explicit"},
  ...
]
```

查询必须真实，含文件路径 / 日期 / 个人语境 / 口语 / 偶见 typo，禁止抽象化（对齐 skill-creator `SKILL.md` 里 description-optimization 的建议）。

## 执行

用 skill-creator `run_loop.py` 的 eval 子命令（不跑优化 loop，只跑 eval）：

```bash
python -m scripts.run_eval \
  --eval-set ~/.claude/skills/daily-report/evals/trigger-eval.json \
  --skill-path ~/.claude/skills/daily-report \
  --model claude-opus-4-7 \
  --trials 3
```

每条跑 3 trial，取多数票（对齐 Schmid 的 3–5 trial 原则）。

## 目标指标（四维 → process）

- Precision ≥ 0.95（正样本被触发率）
- Recall ≥ 0.90（负样本中 false-positive ≤ 10%）
- Near-miss 类 false-positive ≤ 15%
- 单 trial 与多 trial 多数票一致率 ≥ 80%

不达标视为 L1 失败，阻塞合入。

## Description 优化回路（非 CI）

改 `SKILL.md` description 时手动触发：

```bash
python -m scripts.run_loop \
  --eval-set ~/.claude/skills/daily-report/evals/trigger-eval.json \
  --skill-path ~/.claude/skills/daily-report \
  --model claude-opus-4-7 \
  --max-iterations 5 \
  --verbose
```

取 `best_description`（按 test score 选，避免 train 过拟合），人工审后回写 frontmatter。

## 扩展集（延后）

20 条跑稳 2 周后再扩到 80 条，不进 CI gate，手动跑；正负样本比例、分类分布保持一致。
