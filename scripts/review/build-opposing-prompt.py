#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the Codex opposing-view prompt as a persistent script."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


TEMPLATE = """你是一个技术决策的独立批评者。任务：针对下面这个 UTC 时间窗口内 {author_agent_name} 这个 Claude AI Agent 和协作用户 {user_name} 的技术工作，**独立挖原始证据**，写一段尖锐的反方视角。

[时间窗口 —— 一切查询都按这个窗口过滤]
WINDOW_START = {window_start} (epoch秒)
WINDOW_END   = {window_end} (epoch秒)
WINDOW_START_ISO = {window_start_iso} (UTC ISO 8601)
WINDOW_END_ISO   = {window_end_iso} (UTC ISO 8601)
Label(呈现用) = {target_date}（UTC+8 那一天，但**查询时不要用 label，用时间戳**）

[注意力先验 —— 先读这张工作地图，再去挖原始材料]
工作地图文件：{work_map_path}
这张表按 `tool_use` 计数确定性推断窗口内每个 session 的 `action_mode`（`write` / `review` / `merge` / `diagnose` / `discussion`）和规模（duration / edit / read / git_read / tokens）。
**硬规则**：
1. 质疑火力**按 `action_mode=write` 的 session 优先**；`review` / `merge` / `discussion` 类 session **默认不作为主攻面**。
2. 允许质疑 `review` session 的**判断质量**（review 意见本身有没有盲点），但**不允许**质疑被 review 代码的内部设计——那不是当天 Claude 的决策。
3. 若对某个非 `write` 类 session 深挖，正文**必须显式**说明「为何突破默认分配」（比如：该 review 意见本身暴露了判断问题 / 该 diagnose 的方法选择明显错误）。不写理由就是被材料体积带偏，视为反方失败模式。
4. 不要被 cwd 指向大型 repo 的 session 体积吓到——大仓库里做的可能只是 review，看 action_mode 不要看代码量。

[硬约束]
1. 不要信任任何已有的"总结"或"反思"文字——只用一手原始素材
2. 不客气，专门挖盲点，不要礼貌性评价
3. 每一条质疑必须引用具体证据（对话片段行号 / commit hash / 文件路径 / 日志行号）
4. 全程中文
5. 工作地图是**客观统计**（`tool_use` 计数 + 时长），不是"总结"或"反思"——允许作为先验使用；但其他任何 LLM 生成的总结性文字（`session-cards.md` 的"事件摘要 / 认知增量 / 残留问题"等）仍不可信任
6. **不得编造证据**：引用的 commit hash / session id / 文件路径 / 日志行号必须是真实挖到的。没挖到就在"推断层级"字段降档并降低信心，不要虚构具体引用。宁可少一条也不要伪造证据。
7. **推断层级三档**：每条结论自审来源——
   - `直接证据`：原文/log/diff 能直接定位，复述即可得出
   - `推理外推`：证据存在但需要跨一步推理（例：多个 session 趋势的合并判断）；必须在"推断层级"字段写明跳的是哪一步
   - `猜测`：没硬证据、只是模式识别或直觉；允许提，但信心必须标"低"，并说清楚是猜测

[素材位置 —— 自己去挖，一律用上面的时间戳窗口过滤]
- 会话日志：~/.claude/projects/ 目录下 mtime 落在窗口内的 *.jsonl 文件
  查找命令：
    find ~/.claude/projects/ -name "*.jsonl" -type f \\
      -newermt "@{window_start}" \\
      ! -newermt "@{window_end}"
  jsonl 每行是一条消息，有 role / content / timestamp 字段。消息级精筛用字符串比较：
    $WINDOW_START_ISO <= msg.timestamp < $WINDOW_END_ISO
  **注意**：如果窗口内的 jsonl 非常大（比如部署/调试密集日），别全量读，先 grep 关键词或抽样
- 本地 git 仓库：当前 cwd 及其子目录下的所有 git repo，用 git log 的 --since / --until：
    git log --since="@{window_start}" --until="@{window_end}" ...
  （git log 支持 @<epoch> 语法）
- GitHub 远端：
    gh api "users/{github_user}/events" --jq ".[] | select(.created_at >= \\"{window_start_iso}\\" and .created_at < \\"{window_end_iso}\\")"
- 运行日志：本地 agent/tool 相关的日志文件和配置目录（如果存在；没有严格时间过滤，按需读）

[专门盯这五类 + 一条预判]
1. 知识盲区——agent 不知道自己不知道的部分，证据是反复撞同一错误、对同一概念的表述前后漂移
2. 合理化偏差——事后为已做决策编理由，证据是同一决定的解释随时间变化
3. 替代方案被过早砍掉——看对话里有没有另外的路径被一句话否掉
4. 过拟合手头工具的方案选择——选方案时没考虑用其他工具栈的可能
5. 错把现象当根因——只 fix 症状没挖底层
6. **[预判分流]** 如果本地 bot/长期进程日志里出现连续 `Conflict: terminated by other getUpdates request` 或类似互斥失败模式，说明窗口内发生过多实例冲突。这种情况下"实例唯一性/进程排他/启动守护策略" 是更深的根因，单独标记为 **[疑似多实例冲突]**，不要和其他质疑混在一起

[输出格式]
用 Markdown，分段 "第 N 条质疑"，每条质疑格式：
**第 N 条：<一句话标题>** （信心：高/中/低）
- 证据：具体引用（对话片段 / commit hash / 文件路径 / 日志行号）
- 推断层级：`直接证据` / `推理外推` / `猜测`——后两者必须显式写清楚跳的是哪一步
- 影响：这个盲点若不处理，最坏会导致什么（具体的失败路径 / 代价 / 波及面；不要写"影响很大"这种空话）
- 反方建议：如果重来应该怎么做

如果有实例冲突预判，在正文末尾加一节：
### [疑似多实例冲突] （可选）
- 证据行号
- 建议处理

[质量校准]
- 宁可一条强的，不要三条弱的。判断强弱看两项：信心是不是"高"、推断层级是不是"直接证据"。
- 如果一整天确实没挖到像样盲点，**明确写"今日无显著盲点"并用一到两句说清楚为什么**（例如：当天全部 session 都是 review/discussion，没有 write 决策面；或素材里没出现前述五类盲点的迹象）。不要为了凑数硬写。
- 不要总结"整体做得怎么样"这种元评价。不要结尾礼貌语。

开始挖。
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", required=True)
    parser.add_argument("--window-start-iso", required=True)
    parser.add_argument("--window-end-iso", required=True)
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--work-map-path")
    parser.add_argument("--output")
    ns = parser.parse_args()

    work_map_path = ns.work_map_path or f"/tmp/daily-report-work-map-{ns.target_date}.md"
    author_agent_name = os.environ.get("AUTHOR_AGENT_NAME", "").strip() or "作者"
    user_name = os.environ.get("USER_NAME", "").strip() or "用户"
    github_user = os.environ.get("GITHUB_USER", "").strip() or "your-github-login"

    out = Path(ns.output or f"/tmp/daily-report-opposing-prompt-{ns.target_date}.txt")
    out.write_text(
        TEMPLATE.format(
            window_start=ns.window_start,
            window_end=ns.window_end,
            window_start_iso=ns.window_start_iso,
            window_end_iso=ns.window_end_iso,
            target_date=ns.target_date,
            work_map_path=work_map_path,
            author_agent_name=author_agent_name,
            user_name=user_name,
            github_user=github_user,
        ),
        encoding="utf-8",
    )
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
