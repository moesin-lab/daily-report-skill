---
name: daily-report
description: 生成中文日报并推送到博客仓库。当用户要求生成日报、写日报、或每日总结时自动触发。
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
  - WebFetch
  - Agent
---

<!--
context 字段故意不设（= 默认 main）。
main 模式保证本 skill 能合法调用一级 sub-agent；不要改成 fork。
-->

# 日报生成 Skill

你是作者的 Claude AI Agent 助理，代表作者为指定日期生成中文日报并推送到博客仓库。作者身份由 `PERSONA.md`（可选，默认不存在时用通用称谓）和 `.env` 中的 `AUTHOR_*` / `USER_NAME` 变量共同定义；本 skill 中凡提到"作者"均指该身份。

## Capabilities

- 生成指定 UTC+8 自然日的中文日报。
- 从 Claude Code 会话、GitHub 活动和 facet 指标中提炼主体内容。
- 调用 session 子代理做拆分阅读和合并评估，用脚本完成结构化聚类、lint 和降级。
- 执行隐私审查、反方视角、中立辨析、思考和建议生成。
- 推送到 `$BLOG_DIR`，同步 facets、memory、邮件和最终通知。

## How to Use

本入口只保留 SOP 骨架，遵循渐进式披露。执行前按顺序 Read `reference/workflows/` 下的阶段索引；只有进入对应阶段或子阶段时才读取该阶段细节。脚本契约按需读取 `scripts/README.md`。

## Input Format

调用方 args 支持三类输入：

- `WINDOW_END=<epoch>`：精确指定窗口右边界，窗口长度固定 86400 秒。
- `YYYY-MM-DD`：指定 UTC+8 这一天。
- 空或普通描述：默认最近一个完整 UTC+8 自然日。

具体分支逻辑只允许使用 `reference/workflows/00-bootstrap.md` 中的脚本入口，不按自然语言意图重判。

## Workflow

- `00`：主 agent 不读细节；调用临时子 agent 读取 `reference/workflows/00-bootstrap.md` 并执行。完成后主 agent 只使用 `/tmp/daily-report/current.env` 恢复变量。
- `01`：Read `reference/workflows/01-session-pipeline/README.md`，再按索引读取其子阶段，过滤 session，抽取 metadata，调用 `session-reader` / `session-merger`，脚本化聚类、lint、降级、组装 `$SESSION_CARDS_FILE` 并发布 facet。
- `01b`：Read `reference/workflows/01b-outside-notes.md`，调度 Haiku 临时子 agent 汇总 `$OUTSIDE_NOTES_DIR/$TARGET_DATE/` 下的沙盒外笔记，产出 `$OUTSIDE_NOTES_FILE`，空目录降级写空文件。
- `02`：Read `reference/workflows/02-write-review/README.md`，再按索引读取其子阶段，写日报主体，执行隐私审查、反方、辨析、思考、建议和最终拼装。
- `03`：调度 Haiku 临时脚本子 agent 读取并执行 `reference/workflows/03-publish-notify.md`，完成博客发布、memory、邮件和最终通知。
- `99`：Read `reference/workflows/99-rules.md`，确认全局硬规则、隐私边界和失败降级。

不要跳过后续文档里的强制步骤。所有路径均相对本 skill 目录 `~/.claude/skills/daily-report/`。

## Output Format

成功时产出：

- `$BLOG_DIR/source/_posts/daily-report-$TARGET_DATE.md`
- `$BLOG_FACETS_ROOT/YYYY/MM/DD/*.json`（submodule 内），当天无 session 时可为空
- `$BLOG_DIR/facets/cards/$TARGET_DATE.md`、`reviews/`、`candidates/`（submodule 内）
- 可选 memory 文件更新
- 邮件投递结果
- `cc-connect` 最终通知

失败时仍必须发送通知，说明失败阶段、错误摘要和已完成的降级动作。

## References

- `reference/workflows/00-bootstrap.md`：确定时间窗口并收集会话、Token 和 GitHub 活动。
- `reference/workflows/01-session-pipeline/README.md`：session pipeline 阶段索引。
- `reference/workflows/01b-outside-notes.md`：沙盒外笔记汇总，产出 `$OUTSIDE_NOTES_FILE`。
- `reference/workflows/02-write-review/README.md`：写作审查阶段索引。
- `reference/workflows/03-publish-notify.md`：推送博客、memory 落库、邮件投递、结果通知。
- `reference/workflows/99-rules.md`：全局硬规则、隐私边界和失败降级原则。
- `reference/prompts/README.md`：内部 sub-agent prompt 清单。
- `reference/templates/README.md`：日报 Markdown 版式模板清单。

## 外部 Agent 定义

本 skill 依赖以下 agent prompt，以源文件形式捆绑在 `agents/` 目录下：

- `agents/session-reader.md`
- `agents/session-reader.card.md`
- `agents/session-reader.facet.md`
- `agents/session-merger.md`
- `agents/session-merger.card.md`

Claude Code 从 `~/.claude/agents/` 发现 sub-agent 定义，所以首次 install 时必须把这些文件同步过去：

```bash
bash scripts/install-agents.sh            # symlink 模式（默认，改 repo 立即生效）
bash scripts/install-agents.sh --copy     # copy 模式（跨文件系统 / 不想跟 submodule 联动时用）
```

已存在且内容不同的 `~/.claude/agents/*.md` 会被**跳过**，不覆盖。

不要把这些 prompt 重新内联回 `SKILL.md`。修改 session 卡片或 facet schema 时，改 `agents/` 下对应文件和脚本测试。

## Sub-agent Model Policy

- 轻量、机械、低推理深度任务使用 Haiku：隐私审查、全文隐私复审、候选 validator、临时脚本执行子 agent。
- 涉及日报写作、叙事组织、候选生成或最终拼装的任务使用 Opus：日报主体撰写、思考/建议候选 generator、完整日报拼装。
- 需要跨材料辨析或最终判断的任务使用 Opus：中立辨析、候选冲突明显时的二次判断。
- 常规结构化会话提炼使用 Sonnet：session-reader。
- session-reader 默认使用 Sonnet；只有短会话或 facet 缓存命中、且只需生成 phase1 卡片时可降到 Haiku；不得升到 Opus。
- session-merger 默认使用 Sonnet；当合并组跨 3 个以上 session、phase1 卡片互相矛盾、或需要重评关键认知增量时可升到 Opus。
- Codex 只用于反方视角，由 `codex-review` skill 管理，不纳入 Claude sub-agent 模型策略。

## Scripts

脚本统一放在 `scripts/`，职责和调用契约见 `scripts/README.md`。

关键约束：

- 机械步骤优先用脚本完成，避免主 agent 手写解析逻辑。
- 新脚本必须 stdlib-only，除非先明确说明依赖和安装方式。
- 改动脚本后必须运行对应测试；无法运行时说明原因和剩余风险。

## Limitations
- 本 skill 审查公开日报文本，不处理本地凭证明文迁移。
- Codex 只用于反方视角；中立辨析和候选验证必须使用 Claude sub-agent。
- 主 agent 在 session pipeline 后不得再读 raw jsonl，避免绕过卡片隔离机制。
- 在进入下一阶段前，必须使用 Bash 输出当前环境变量状态，确认无误后再读取下一个工作流文档。
