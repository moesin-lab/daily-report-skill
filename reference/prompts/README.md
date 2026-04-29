# daily-report prompts

本目录存放 daily-report workflow 内部使用的 Claude sub-agent prompt。workflow 文档只负责说明调用时机和占位符，不再内联长 prompt。

| Prompt | 阶段 | 模型策略 | 用途 |
| --- | --- | --- | --- |
| `privacy-review.md` | 2.1 / 2.6 | Haiku | 日报发布前隐私审查与全文复审 |
| `neutral-analysis.md` | 2.3 | Opus | Claude sub-agent 中立辨析 |
| `candidate-generator.md` | 2.4a | Opus | 生成思考、建议、memory 候选 |
| `candidate-validator.md` | 2.4b | deepseek-chat（via `proxy-agent`） | 对单条候选做独立准入复核 |
| `tldr-generator.md` | 2.7 | Opus | 生成日报顶部 TL;DR 段落，校验与重试由 `scripts/review/insert-tldr.py` 兜底 |

约束：

- 修改 prompt 后同步检查 `reference/workflows/02-write-review/README.md` 及其子阶段文件里的占位符说明。
- Prompt 文件内只放可复用模板，不写某次运行的具体变量值。
- 需要持久化生成文件或解析输出时，优先放到 `scripts/`，不要塞回 prompt。
- 轻量审查和验证 prompt 默认用 Haiku；涉及写作、辨析和候选生成的 prompt 使用 Opus。
