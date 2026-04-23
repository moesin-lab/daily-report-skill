# Step 02 — Pipeline fixture 实例化（6 份）

前置：`shared.md` 的 fixture 契约、schema 契约、trace-parser 契约。

## 六份 fixture

| 名称 | 目的 | 关键点 |
|---|---|---|
| `typical-day` | 正常 CI 主力 | ~10 session，中等 GitHub 活动，typical token 预算 |
| `empty-day` | 空日降级 | 0 session，强制走 empty branch；expected 不含"今日工作" |
| `heavy-day` | 不 OOM / 不超预算 | 20+ session + 大量 GitHub 活动；`max_tokens` 硬上限 |
| `boundary-tz` | 跨 UTC+8 天边界 | 00:05 / 23:55 session 各一；验证窗口语义 |
| `privacy-canary` | 隐私零泄漏 | 埋假 `AKIA…TESTCANARY` / 假 ghp token / 假邮箱 / 假 telegram chat_id |
| `facet-cache-hit` | 缓存命中路径 | 两次跑同一天；第二次期望 `prepare-session-run.py` 命中 facet 缓存（跳过 facet 重写）、session-reader 降 Haiku 只产 phase1 卡片、总 token 下降 |

## 每份必含文件

对齐 `shared.md` 的 fixture 契约：

- `raw/*.jsonl`：Claude Code 官方 transcript 格式；真实脱敏（替真实人名 / 仓库名 / secret）
- `github-events.jsonl`：事件快照
- `memory-snapshot/`：测试用 memory 目录（含 canary 时期望 canary 不被写入 apply 后的 memory）
- `expected.json`
- `expected-trajectory.json`
- `codex-replay.txt`（`empty-day` 允许空占位）
- `schema_version`

## 可选：预制 checkpoint

`heavy-day` 和 `typical-day` 的 session-pipeline 阶段耗时占整条 pipeline 40% 以上。允许 fixture 附带 `checkpoints/` 子目录，预制到指定 phase 为止的快照：

```
tests/fixtures/pipeline/heavy-day/
  raw/*.jsonl                           # 原始输入（L1 session-pipeline 测试仍用）
  github-events.jsonl
  expected.json
  expected-trajectory.json
  checkpoints/                          # 可选
    session-pipeline/
      run-dir.tar.zst
      env.json
      phase-markers.log.snapshot
      meta.json                         # skill_sha + fixture_sha 锁定
```

CI 按改动范围选择是否用预制 checkpoint：

- 改动不触及 session-pipeline 及其前序 → 可直接 `RESUME_FROM_PHASE=main-body` 从预制 checkpoint 起跑，跳过 session-reader/merger 的 LLM 调用
- 改动触及 session-pipeline → 必须忽略预制 checkpoint，从头跑

预制 checkpoint 的 `meta.skill_sha` 每月刷新一次，刷新脚本 `scripts/eval/refresh-fixture-checkpoints.sh` 跑完整 skill 一次产出新快照。skill_sha 过期的预制 checkpoint 由 `checkpoint-compat.py` 直接拒绝使用，不静默回退。

## `expected-trajectory.json` 内容

L1 trajectory 断言直接消费：

```json
{
  "phase_order": ["bootstrap", "session-pipeline", "main-body", "privacy1",
                  "opposing", "neutral", "candidates", "final-assembly",
                  "privacy2", "tldr", "publish"],
  "essential_tool_calls": [
    "publish-blog.sh", "publish-artifacts.sh", "send-email.sh",
    "send-telegram-opposing.sh", "send-cc-notification.sh",
    "apply-memory-candidates.py"
  ],
  "essential_roles": [
    "session-reader", "session-merger",
    "main-body", "privacy1", "privacy2",
    "opposing-script", "neutral",
    "candidate-generator", "candidate-validator",
    "final-assembly", "tldr-generator"
  ],
  "role_model_policy": {
    "_comment": "所有子 agent 的 subagent_type 都是 general-purpose；角色由 agent_prompt_role（prompt_sha256 白名单）判定。策略对照 reference/workflows/02-write-review/README.md:9-14 的分工。",
    "privacy1":            {"required_model": "haiku"},
    "privacy2":            {"required_model": "haiku"},
    "candidate-validator": {"required_model": "haiku"},
    "tldr-validator":      {"required_model": "haiku"},
    "opposing-script":     {"required_model": "haiku"},
    "script-exec":         {"required_model": "haiku"},
    "main-body":           {"required_model": "opus"},
    "candidate-generator": {"required_model": "opus"},
    "neutral":             {"required_model": "opus"},
    "final-assembly":      {"required_model": "opus"},
    "tldr-generator":      {"required_model": "opus"},
    "session-reader":      {"default_model": "sonnet", "allowed_downgrade": "haiku", "forbid_upgrade": "opus"},
    "session-merger":      {"default_model": "sonnet", "allowed_upgrade": "opus", "forbid_downgrade": "haiku"}
  },
  "negative_assertions": {
    "bypass": [
      {"id": "no_direct_find_projects",
       "pattern": "Bash:find\\s+~?/\\.claude/projects"},
      {"id": "no_inline_read_raw_jsonl",
       "after_phase": "session-pipeline",
       "tool": "Read", "path_glob": "**/raw/*.jsonl"},
      {"id": "no_inline_read_metadata",
       "after_phase": "session-pipeline",
       "tool": "Read", "path_glob": "**/metadata-*.json"},
      {"id": "no_inline_privacy",
       "phase": "privacy1", "require_agent_role": "privacy1"},
      {"id": "no_inline_privacy2",
       "phase": "privacy2", "require_agent_role": "privacy2"},
      {"id": "no_inline_tldr",
       "phase": "tldr", "require_agent_role_in": ["tldr-generator", "tldr-validator"]},
      {"id": "no_inline_facet_aggregate",
       "phase": "session-pipeline",
       "forbid_tool": "Agent",
       "scope": "聚合必须跑 aggregate-facet.py，禁止内联 Agent 做"},
      {"id": "no_webfetch_for_gh_activity",
       "tool": "WebFetch",
       "url_pattern": "api\\.github\\.com"},
      {"id": "no_direct_git_push_blog",
       "pattern": "Bash:git\\s+push.*(blog|facets)",
       "allowed_via": ["publish-blog.sh", "publish-artifacts.sh"]},
      {"id": "no_inline_email_http",
       "pattern": "Bash:curl.*mails",
       "allowed_via": ["send-email.sh"]}
    ],
    "phase_overstep": [
      {"id": "publish_read_only",
       "phase": "publish",
       "forbid_write_glob": "$RUN_DIR/**"},
      {"id": "pre_pipeline_no_blog_write",
       "before_phase": "session-pipeline",
       "forbid_write_glob": "blog/**"},
      {"id": "pre_privacy1_no_blog_write",
       "before_phase": "privacy1",
       "forbid_write_glob": "blog/source/**"},
      {"id": "no_raw_in_narrative_phases",
       "phase_in": ["main-body", "neutral", "final-assembly",
                    "privacy1", "privacy2", "tldr"],
       "forbid_tool": "Read",
       "path_glob": "**/raw/*.jsonl"}
    ],
    "model_policy": [
      {"_comment": "所有判定走 agent_prompt_role（prompt_sha256 白名单），不走 subagent_type",
       "id": "reader_not_opus",
       "role": "session-reader", "forbid_model": "opus"},
      {"id": "reader_haiku_requires_cache",
       "role": "session-reader", "model": "haiku",
       "requires": "facet_cache_hint == 'hit' OR session_length < SHORT_THRESHOLD"},
      {"id": "privacy_not_above_haiku",
       "role_in": ["privacy1", "privacy2",
                   "tldr-validator", "candidate-validator"],
       "forbid_model_in": ["sonnet", "opus"]},
      {"id": "writing_not_below_opus",
       "role_in": ["main-body", "candidate-generator",
                   "neutral", "final-assembly", "tldr-generator"],
       "forbid_model_in": ["haiku", "sonnet"]},
      {"id": "merger_not_haiku",
       "role": "session-merger", "forbid_model": "haiku"},
      {"id": "role_must_be_registered",
       "scope": "每个 Agent 调用的 agent_prompt_role 必须命中 role-registry.json；未知角色视为 infra-warning，连续 2 次升级为 fail"}
    ],
    "thrashing": [
      {"id": "no_duplicate_read",
       "tool": "Read",
       "same_input_sha256_threshold": 3,
       "scope": "非循环语境；循环由 fixture 元信息标注白名单"},
      {"id": "no_infinite_retry",
       "consecutive_same_input_fail_threshold": 3},
      {"id": "no_glob_projects_root",
       "tool": "Glob", "path_pattern": "~?/\\.claude/projects/\\*"},
      {"id": "no_trivial_subagent_dispatch",
       "tool": "Agent",
       "forbid_if": "inner_tool_calls == 0 AND agent_prompt_role NOT IN role-registry",
       "_rationale": "privacy / tldr-validator 等角色合法返纯文本结论；只禁'未登记角色 + 零工具'的真正冗余派发"}
    ]
  }
}
```

Fixture 可在各自 `expected-trajectory.json` 里追加条目但不得删除 base 条目；删除一条 base 必须在 PR 里解释。

部分 fixture 可覆写：

- `empty-day`：`essential_tool_calls` 去掉 `apply-memory-candidates.py`；opposing 仍跑（codex 在空日也走一遍），故 `send-telegram-opposing.sh` 保留在 essential 集
- `facet-cache-hit`：第二次运行的期望不是 reader 调用数下降（phase1 卡片仍然每个 session 要跑一次），而是：
  - `prepare-session-run.py` stderr 含 `cached_facets=N`，N ≥ fixture session 总数 × 0.8
  - `$RUN_DIR/facet-<sid>.json` 的 mtime 与 blog 缓存文件相等（`shutil.copy2` 保留 mtime）
  - 每次 `session-reader` 调用的 `model` 字段 == `haiku`
  - 第二次 run 的 session-reader 总 input+output token ≤ 第一次的 50%

## 刷新策略

- 每季度基于真实一天回填新 `typical-day`；旧的降级为冻结 regression，不删
- 真实日志脱敏走 `scripts/eval/fixture-sanitize.py`（项目 name / 人名 / token / 路径全替换映射）
- `privacy-canary` 的假 secret 模式每次更新必须与当前 privacy 审查规则同步

## 不在本步

- Regression 目录（`tests/fixtures/regressions/`）由 `09-regression-loop.md` 管理
- Track B 专属 fixture 在 `08-track-b.md`
