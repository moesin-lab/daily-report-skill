# daily-report scripts

本目录存放日报 pipeline 的机械脚本。脚本用于稳定数据结构、lint 和发布，不承载 LLM 判断。

## 目录结构

```text
scripts/
  window/    # 窗口解析
  collect/   # 会话/GitHub/Token 采集
  session/   # 第 1 步 session pipeline 与 facet
  review/    # 反方、候选组装
  publish/   # 博客、memory、邮件、通知
  tests/     # 脚本测试
```

## 脚本契约

| 脚本 | 阶段 | 输入 | 输出 |
| --- | --- | --- | --- |
| `bootstrap.py` | 0 | raw args、projects root、GitHub user | shell exports、`$RUN_DIR/bootstrap.env`、`/tmp/daily-report/current.env`、session files、token stats、GitHub events、bootstrap summary |
| `window/resolve-window.py` | 0 | raw args | shell exports 或 JSON 窗口变量 |
| `collect/find-sessions.py` | 0 helper | epoch 窗口、projects root | session path 列表 |
| `collect/token-stats.py` | 0 helper | `session-files.txt`、ISO 窗口 | token stats JSON |
| `collect/github-events.sh` | 0 helper | `WINDOW_START_ISO`、`WINDOW_END_ISO` | GitHub events JSON stream |
| `session/prepare-session-run.py` | 1.0 | 窗口变量、`TARGET_DATE`、可选 `SESSION_FILES_FILE` | `$RUN_DIR`、kept、metadata、facet cache |
| `session/filter-sessions.py` | 1.0 | `--input`、`--window-start`、`--window-end`、`RUN_DIR` | `kept-sessions.txt`、`filtered-sessions.json` |
| `session/extract-metadata.py` | 1.0 | `--session-file`、窗口、`--target-date`、`RUN_DIR` | `metadata-<sid>.json` |
| `session/slice-session.py` | 1.1 / 1.4 | `--session-file`、窗口、`--output`、可选 `--chunk-dir` | Read-safe slice index + chunk files |
| `session/fallback-session-artifacts.py` | 1.1 / 1.3 | `RUN_DIR`、kept/lint/metadata | 缺失或失败的 md/facet 降级文件 |
| `session/lint-phase1.py` | 1.3 | `RUN_DIR` | 覆盖写 `lint-report.json` |
| `session/lint-facet.py` | 1.3 | `RUN_DIR` | 追加写 `lint-report.json` |
| `session/build-merge-groups.py` | 1.4 | `RUN_DIR`、phase1 cards | `merge-groups.json` |
| `session/assemble-session-cards.py` | 1.5 | `RUN_DIR` | `session-cards.md` |
| `session/publish-facet.py` | 1.5 | `RUN_DIR`、`TARGET_DATE`、`BLOG_FACETS_ROOT` | `$BLOG_FACETS_ROOT/YYYY/MM/DD/<sid>.json` |
| `review/run-opposing-agent.py` | 2.2 | 窗口变量、`TARGET_DATE`、`RUN_DIR`、可选 `OPPOSING_BACKEND`/`--opposing-backend`、`--opposing-timeout` | `opposing.env` + work-map/prompt/raw/clean/status files |
| `review/build-opposing-prompt.py` | 2.2 | 窗口变量 | opposing prompt 文件路径 |
| `review/parse-opposing-output.py` | 2.2 | backend raw stdout（JSON payload 或兜底纯文本） | cleaned content + ok status |
| `publish/send-telegram-opposing.sh` | 2.2 | `TARGET_DATE`、content file | Telegram API send result |
| `review/assemble-candidates.py` | 2.4 | candidates JSON、validations JSONL | reflection/suggestions/memory candidate files |
| `session/aggregate-facet.py` | 2.5 | `RUN_DIR` | stdout Markdown `## Session 指标`，无 facet 时为空 |
| `review/insert-tldr.py` | 2.7 | Markdown path、TL;DR 文本 path | 校验并把 TL;DR 插入 frontmatter 之后、`## 概览` 之前；失败 exit 2 + stderr 错误清单 |
| `publish/publish-blog.sh` | 3.0 | `TARGET_DATE`、blog repo | git pull/add/commit/push |
| `publish/publish-artifacts.sh` | 3.1 | `TARGET_DATE`、`RUN_DIR` | submodule commit/push + blog submodule ref update |
| `publish/apply-memory-candidates.py` | 3.2 | memory candidates JSON | memory files + summary |
| `publish/render-email.py` | 3.3 | Markdown path | standalone HTML |
| `publish/send-email.sh` | 3.3 | `TARGET_DATE`、Markdown path | mails send + status text |
| `publish/verify-published.sh` | 3.4 | `TARGET_DATE` | GitHub content verification |
| `publish/send-cc-notification.sh` | 3.4 | message | cc-connect notification |

## 约束

- Python 脚本默认保持 stdlib-only；`render-email.py` 例外，依赖 `markdown` 包。
- 失败边界优先返回可诊断错误，不要静默吞掉全局失败。
- LLM 产物必须经 lint；lint 不评价语义质量，只做结构闸门。
- `lint-phase1.py` 必须先于 `lint-facet.py` 运行，因为前者覆盖写报告、后者追加。
- `publish-facet.py` 只对语义无序字段做 canonical 比较，不改磁盘原文。

## 反方 reviewer backend（第 2.2 步）

`run-opposing-agent.py` 抽了一层 `OPPOSING_BACKEND`，把"用哪个异构模型做反方视角"从 pipeline 里解耦出来。接口契约：

- 输入：`build-opposing-prompt.py` 生成的 prompt 文本文件。
- 输出：写到 `raw_file` 的 stdout 字节流，可以是 JSON payload（含 `status`/`rawOutput`）或纯文本；`parse-opposing-output.py` 会自动识别两种形态。
- 退出码：0 成功，124 超时，126/127 环境错误，其它非 0 走统一 fallback 路径。
- 超时：由 runner 侧 `--opposing-timeout` 控制（默认 600s），backend 不自负责。

当前实现的 backend：

| 名称 | 实现 | 说明 |
|---|---|---|
| `codex-plugin`（默认） | `node <plugin_root>/scripts/codex-companion.mjs task --json --prompt-file <prompt>` | 走 Claude Code `openai-codex` 插件的 shared runtime，自动探测 `~/.claude/plugins/cache/openai-codex/codex/*` 下最新版本；approval/sandbox 走 `~/.codex/config.toml` |

接新 backend（例如 `kimi-code` 或自建 HTTP reviewer）只需在 `run_backend()` 里加一个 branch + 对应子进程；parser 层无需改（会走兜底纯文本分支），除非新 backend 也提供机读 JSON。

选择方式：
- `OPPOSING_BACKEND=<name>` 环境变量
- `--opposing-backend <name>` CLI 参数（后者覆盖前者）

Codex 独家走 plugin，不再保留直接 `codex exec` 兜底——如果 plugin 缺失，请重装 plugin 或临时切到其它 backend。

## 验证

脚本改动后优先运行：

```bash
python3 -m pytest skills/daily-report/scripts/tests
```

如果环境缺少 `pytest`，至少运行受影响脚本的 `--help` 或构造最小输入做手动验证，并在最终说明剩余风险。
