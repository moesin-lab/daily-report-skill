---
name: abagent
description: 把单轮、低判断深度、可批量并行的子任务（如 validator、privacy-scan、schema-fill、双视角 review）派给非 Anthropic 的便宜模型（DeepSeek / Codex），用来压 daily-report 等长 pipeline 的 token 成本。本 skill 是知识层 + 调用范例，**实际执行靠 `proxy-agent` subagent**，不要直接在 skill 里跑外部 CLI。
allowed-tools:
  - Bash
  - Read
  - Write
  - Agent
---

# abagent

"alternative-backend agent" 的缩写。当你判断一个任务**不需要 Claude 的写作 / 判断 / 跨材料推理**时，从这里查 backend 选型 + 调用范式 + 解析 wrapper，最终用 `Agent(subagent_type="proxy-agent", ...)` 落地。

## 何时用 / 何时不用

适合走 abagent 的任务（强信号）：

- **schema-constrained 输出**：JSON 单行验证、固定字段抽取（facet 卡片机械字段、validator 的 `{pass, reason}`）
- **checklist 扫描**：privacy review（API key/token/邮箱/IP 模式匹配）、lint 类规则检查
- **单轮重写**：把一段中文重新组织成另一种结构、轻度风格 pass、字符截断到长度
- **异构反方**：codex 的现有用途（已经在 daily-report 第 2.2 步用着）

**不适合**走 abagent 的任务（必须留在 Claude 主线）：

- 写作类：日报主体、TLDR、最终拼装、思考/建议候选 generator
- 跨材料判断：中立辨析、merger 的多 session 时间线重评
- 多轮 tool use 循环：session-reader 当前形态（要 slice + Read + Write + lint）
- 任何需要"理解作者风格 + 半年回看锚点"的输出

灰区：

- 短 session 的 phase1 卡片：理论上能用，但目前 reader 是端到端 LLM agentic loop，不是单轮，迁移成本高于收益。等做完"切成 deterministic + LLM"再考虑。

## Backend 选型

| Backend | 适合 | 不适合 | 单 call 成本量级 |
|---------|------|--------|------------------|
| `deepseek-chat` (V3) | validator / privacy / 单轮 schema 输出 | 复杂推理、长文 | $0.0003–0.001 |
| `deepseek-reasoner` (R1) | 需要思考链的 validator、双视角辨析 | 不需要思考链时浪费 | $0.001–0.005 |
| `codex` (gpt-5 系列) | 异构反方 / 架构挑错 / 需要不同模型家族 | 简单 schema 输出（杀鸡用牛刀） | $0.005–0.05 |

**默认偏好**：

1. 任务"对/错"型 → `deepseek-chat`
2. 任务需要"为什么"型 → `deepseek-reasoner`
3. 任务要"另一种眼光" → `codex`

不要试图组合多 backend（同 task 跑 2 个再仲裁）——目前 daily-report token 还远没到需要这种花活的程度。

## 调用范式

### 标准流程

1. **写 prompt 到文件**。不要 inline——尤其多行、含特殊字符、含示例 JSON 的，inline 走 `$ARGUMENTS` 文本替换链路在历史上踩过坑。
2. **派 proxy-agent**：

   ```
   Agent(
     subagent_type="proxy-agent",
     prompt="""
     BACKEND=deepseek-chat
     PROMPT_FILE=/tmp/your-prompt.txt
     TIMEOUT_S=120
     """,
     run_in_background=true   # 多个并发时设这个
   )
   ```

3. **等通知 / 接结果**：subagent 最终消息一定是 `<<<PROXY_BEGIN ...>>>` ... `<<<PROXY_END>>>` 包裹的 wrapper，剥出中间正文即可。

### Wrapper 解析

最简形式：

```bash
RESULT_FILE=$(mktemp /tmp/proxy-payload.XXXXXX)
awk '/^<<<PROXY_BEGIN/{flag=1;next} /^<<<PROXY_END>>>/{flag=0} flag' \
  <<< "$AGENT_RESULT_TEXT" > "$RESULT_FILE"
```

或纯 sed：

```bash
sed -n '/^<<<PROXY_BEGIN/,/^<<<PROXY_END>>>/{//!p;}' <<< "$TEXT"
```

wrapper header 里的 `exit=N` 字段告诉你外部 CLI 退出码：

```bash
EXIT=$(grep -o 'exit=[0-9]*' <<< "$HEADER_LINE" | head -1 | sed 's/exit=//')
```

### 并发派发

N 个独立任务 → 主 agent 单条消息里发 N 个 Agent tool 调用 + `run_in_background: true`，等 task-notification 串行处理。比 skill 体系下手工拆 args 干净。

### 失败处理

| wrapper 内容 | 处理 |
|--------------|------|
| `PROXY_INVALID_INPUT: ...` | 调用方修 prompt（字段缺失/backend 拼错） |
| `PROXY_DEPENDENCY_MISSING: jq/opencode/codex` | 容器环境缺工具，记 runtime-issue，本次走原 Claude 兜底 |
| `exit=124` | 外部 CLI timeout，提高 `TIMEOUT_S` 或缩 prompt |
| `exit=0` 但内容空 | DeepSeek 偶发空 response，重试一次或转 backend |
| `exit=0` 内容存在但 schema 不合法 | 业务层报错，按需 fallback 到 Haiku/Sonnet |

总原则：**proxy-agent 不做降级、不做重试**，是单纯 transport。降级 / cascade / fallback 都在调用方业务层写。

## 已知 daily-report 接入点（建议优先级）

按性价比从高到低：

1. **Stage 2.4b validator × 4**：`deepseek-chat`，4 并发。当前 ~196k tokens / 跑 → 估算迁后 ~10k Anthropic（proxy-agent 包装层）+ 4×$0.0005 DeepSeek。
2. **Stage 2.1 / 2.6 privacy review × 2**：`deepseek-chat`，单 call。两次合计 ~93k → 5k 包装 + $0.001。
3. **Stage 2.2 反方** （已经走 codex）：可以保持现状不动，或者改成 abagent 路径统一管控；本身收益不大。
4. **Stage 1 短 session reader**：暂不用 abagent。等 reader 切成"机械字段提取 + LLM 写认知"后，narrative 子任务可以走 `deepseek-chat`。

## 反例 / 不要这么做

- ❌ 在 abagent skill 里直接跑 codex / opencode CLI——这套规则就是从老 codex-review 里学到的：args 文本替换 + skill 与 subagent 调度边界混合 = 两层语义坑互相放大。
- ❌ 让 proxy-agent 做 cascade（"deepseek 失败就转 codex"）——会让一次 dispatch 的语义不可观测，调用方应该按 wrapper 结果自己决定下一步。
- ❌ 把 wrapper 协议改成 JSON——bash 解析多行 JSON 比 awk 抽 wrapper 麻烦得多，得不偿失。
- ❌ 把 prompt inline 进 Agent prompt 体——`PROMPT_INLINE=` 路径只为应急保留；正常都走 `PROMPT_FILE=`。
- ❌ 在 abagent skill 里复制 proxy-agent 的执行细节文档——proxy-agent.md 就是 single source of truth。本 skill 只讲"何时用 / 怎么调用 / 怎么剥结果"。

## 兼容性 / 与现有 skill 关系

- **`codex-review` skill 仍可用**：单 prompt 一次性 codex review 的老调用方继续走那个 skill；本 skill 是新增物，不强制迁移。
- **`run-opposing-agent.py`**：daily-report 第 2.2 步的 codex-plugin runtime 不走本 skill；那是脚本直接调度 codex CLI 的另一条路径，正交。

## 参考实现位置

- 执行层：`~/.claude/agents/proxy-agent.md`
- DeepSeek 配置：`~/.config/opencode/opencode.json`（已配 API key），`~/.opencode/bin/opencode` 二进制
- Codex 配置：`~/.codex/config.toml`，`codex` 在 PATH
- 日报接入示例：`~/.claude/skills/daily-report/reference/workflows/02-write-review/04-candidates.md` 第 2.4b 步（迁移 PR 落地后回填本节）
