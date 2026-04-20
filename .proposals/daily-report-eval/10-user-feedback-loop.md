# Step 10 — 用户反馈闭环

日报发出后用户经常会给反馈："这段写废话了"、"TL;DR 漏了今天最重要那件事"、"思考段又堆黑话了"、"别再提 XX 系列 PR"。这些反馈是 L1/L2/L3 抓不到但又确凿存在的质量信号，必须入库而不是沉在对话里。

方法学锚点：Phil Schmid 的 "every user-reported wrong output becomes a new test case"、skill-creator 的 iteration feedback.json、Databricks 的 human-in-loop review flow。

## 反馈入口（与 09 的分工）

| 维度 | `09-regression-loop.md` | 本 step |
|---|---|---|
| 来源 | Track B 失败分类器自动触发 | 用户显式反馈 / post-publish diff 提示 / feedback memory 新增 |
| 判定 | 二值失败 + 分类 | 自由文本 + 人工分类 |
| 证据 | raw response / stderr | 日报原文 + 用户批注 |
| 回灌产物 | fixture 草稿 | fixture / assertion / rubric / banlist 四类 |

两条路径共用 `tests/fixtures/regressions/` 存储；不共用触发器。

## Inbox 契约

位置：`~/.claude/skills/daily-report/evals/feedback-inbox/`

每条反馈一个 json，文件名 `<YYYY-MM-DD>-<slug>.json`：

```json
{
  "id": "fb-2026-04-18-jargon-in-thinking",
  "received_at": "2026-04-18T14:02:00+08:00",
  "report_date": "2026-04-17",
  "source": "chat | diff-watchdog | memory-new | email-reply",
  "user_verbatim": "思考段第二段全是 meta 词，读完没看到具体事实",
  "evidence_refs": [
    "blog/source/_posts/daily-report-2026-04-17.md#L88-L104"
  ],
  "triage": {
    "status": "pending | accepted | rejected | dup | deferred",
    "classification": null,
    "target": null,
    "assigned_iteration": null,
    "notes": ""
  },
  "closeout": {
    "fixed_in_skill_sha": null,
    "paired_eval_ref": null,
    "verified": false
  }
}
```

`user_verbatim` 原文不改写。triage / closeout 随生命周期更新。

## 反馈四分类与转换路径

Triage 时必须归类为以下四类之一。不落到任一类 → 反馈内容太泛，reject 并回复用户要更具体的例子。

### A. Fixture case（"这种情况又错了"）

- 特征：反馈关联某天的具体产物，反映一个可复现的失败模式
- 转换：当天 session 脱敏后落 `tests/fixtures/regressions/<fb-id>/`，`expected.json` 记录这次反馈下的正确行为
- 挂 L1（`04-deterministic.md`）
- 永不删除

### B. Style banlist / regex（"不要再说/带出 X"）

- 特征：用户要求避免某个词、格式、实体出现在某段
- 转换：加到 `tests/prompts/style-banlist.txt` 或独立 regex 规则文件
- L1 Style 维度里新增一条 regex 断言
- **回扫前置**：新增 banlist 条目必须先在 `tests/baselines/` 全部历史冻结日报上 dry-run：
  - 命中次数 = 0 → 允许入库
  - 命中次数 > 0 → 命中的历史样本要么被豁免（加入 `banlist-exceptions.json` 带豁免原因），要么该条 banlist 重写到不误伤为止
  - 豁免比例 > 30% → 这条 banlist 设计太粗，拒入库，回复反馈者要更精确描述
- 回扫脚本 `scripts/eval/banlist-backscan.py`，结果落 PR，评审时可见
- banlist 条目带 `source_fb: <fb-id>` 注释，便于反查

### C. Rubric 维度调整（"整体读感不对"）

- 特征：反馈定性、跨句跨段、单句 regex 抓不住
- 转换：改 `tests/prompts/judge-rubric.md`（`05-structured-judge.md`）里对应维度的"常见扣分点"或 score 锚点
- 强制：每次 rubric 改动必须跑 L2 稳定性自检（两次一致率、维度方差、判决翻转率），过关才合入
- 如果现有六维度装不下 → 这是 rubric 结构扩展，走 L2 schema bump，而不是在 notes 里 workaround

### D. 硬规则 / 流程约束（"这种情况必须 X"）

- 特征：不是审美问题，是业务规则（例如"敏感项目 X 禁止进日报任何段落"）
- 转换：加入 `reference/workflows/99-rules.md` + 对应阶段的硬约束
- 同步加 L1 outcome 断言（强制 assert）

## 生命周期状态机

```
pending  (刚入 inbox，未分类)
  ↓ triage
accepted (分到 A/B/C/D 之一) ─┐
rejected (重复/不可复现/越权)  │
deferred (下个迭代再处理)      │
dup      (已有同类 fb)         │
                               ↓
                         in-progress (对应 testify / skill 改动 PR 进行中)
                               ↓
                         testified (测试/规则已合入，未 paired-eval 验证)
                               ↓
                         closed   (paired-eval 验证修复，verified=true)
```

`closed` 前禁止从 inbox 移出；inbox 只在 `closed` 或 `rejected/dup` 后归档到 `feedback-archive/<quarter>/`。

## Post-publish diff watchdog 自动入口

`09-regression-loop.md` 已有 24h diff > 30 行告警。额外动作：

- Watchdog 触发时自动生成 inbox 条目，`source: diff-watchdog`，`user_verbatim` 填 diff summary
- 状态默认 `pending`，等人工 triage
- 避免用户既要手改日报又要手写 feedback

## feedback memory 同步

用户新增 `~/.claude/projects/-workspace/memory/feedback_*.md` 也算一种反馈信号（但这种已经是被用户提炼过的规则，跳过 triage 直接 `accepted + classification=B/C/D`）。

同步脚本 `scripts/eval/sync-feedback-memory.py`：扫 memory 新增，对比上次快照，新条目自动起 inbox 条目，classification 预判（memory 里的 "Why:" 多是 rubric 类、"硬规则" 多是 D 类）。

## 效果评测

每条 `accepted` 的反馈闭合前必须回答：**这次改动是否真的让反馈描述的问题不再发生？**

强制走 `07-paired-eval.md`：

- A = 反馈发生时的 skill 版本
- B = 修复后的 skill 版本
- Fixture：该反馈对应的 regression fixture（A 类）或该反馈所在原始日期的 fixture（B/C/D 类）
- 判定：
  - A 类（fixture case）：B 版该 fixture L1 pass，A 版该 fixture L1 fail → 通过
  - B 类（banlist）：B 版 banlist regex 命中 0，A 版命中 ≥ 1 → 通过
  - C 类（rubric）：B 版对应维度 judge score ≥ A 版 + 10 分且稳定性自检不漂移 → 通过
  - D 类（硬规则）：B 版该约束断言 pass，A 版 fail → 通过

没跑 paired-eval → 禁止 `closed`。

## Inbox 健康度（月度看一次）

- 积压 > 10 条 pending → 排会 triage
- 同一 classification 内重复 ≥ 3 条 → 抽公共模式升级为 rubric 或 fixture family
- `rejected` 占比 > 30% → 说明反馈收集方式有问题（用户给的太泛），反观入口 prompt

## 不在本 step

- Track B 自动失败分类与回灌归 `09-regression-loop.md`
- 具体 L1 / L2 断言写法归 `04` / `05`
- 配对评估执行归 `07`
- 反馈本身在 skill 侧如何生成（"写完日报后主动问用户"之类）是 skill 主体的设计，不在 eval 计划里定义
