#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a metadata-only "work map" for the daily-report opposing stage.

Purpose
-------
反方 Codex 面对时间窗口内的 raw jsonl / git log / GitHub events，
会被"材料体积 + 代码复杂度"带偏（比如把当天只是 code-review 的 session
误当主动开发深挖内部设计）。这个脚本扫窗口内的 session jsonl，产出一张
**纯 metadata** 表（action_mode 按 tool_use 计数确定性推断，不走 LLM），
作为反方 prompt 的"注意力先验"。

**不写观点字段**（事件摘要/认知增量/残留问题都不读也不输出），
这是维持反方独立性的硬边界——对齐 build-opposing-prompt.py L20 的约束。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

PROJECTS_ROOT = Path.home() / ".claude" / "projects"


def parse_iso(ts: str) -> float | None:
    if not ts:
        return None
    try:
        # jsonl 里是 '2026-04-10T07:29:33.980Z'
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts).timestamp()
    except Exception:
        return None


def iter_top_level_jsonl(window_start: float, window_end: float) -> Iterable[Path]:
    """Yield non-subagent jsonl whose mtime falls in window.

    对齐 session-pipeline 的纪律：subagents/ 子目录不作为独立 session。
    """
    if not PROJECTS_ROOT.exists():
        return
    for path in PROJECTS_ROOT.rglob("*.jsonl"):
        if "subagents" in path.parts:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        # mtime 代表最后一条消息时间——只要 mtime >= window_start
        # 就可能有消息落在窗口里；mtime < window_start 就一定整体早于窗口
        if mtime < window_start:
            continue
        # 文件创建可能晚于 window_end，但其中仍可能有窗口内消息？
        # 不可能：jsonl 只 append，mtime 必 >= 最后消息时间
        # 但允许 mtime > window_end，因为它可能横跨窗口（开始在窗口前，结束在窗口后）
        yield path


def extract_bash_prefix(cmd: str) -> str:
    cmd = (cmd or "").strip()
    if not cmd:
        return ""
    # 取第一个 token；git/gh 再取子命令
    parts = cmd.split()
    first = parts[0]
    if first in ("git", "gh") and len(parts) > 1:
        return f"{first} {parts[1]}"
    return first


@dataclass
class SessionStat:
    session_id: str
    path: Path
    cwd: str | None = None
    msg_count: int = 0  # 窗口内消息数
    first_ts: float | None = None
    last_ts: float | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    edit_count: int = 0  # Edit + Write + NotebookEdit
    read_count: int = 0  # Read + Grep + Glob
    git_read_count: int = 0  # git log/show/diff/blame/status/merge-base/branch/ls-*
    bash_commit_count: int = 0  # git commit / gh pr create
    bash_merge_count: int = 0  # gh pr merge
    bash_total: int = 0
    bash_readonly_nongit: int = 0  # ls/cat/tail/head/find/grep/curl 等，不含 git
    tool_total: int = 0
    bash_prefix_samples: dict[str, int] = field(default_factory=dict)

    @property
    def duration_min(self) -> int:
        if self.first_ts is None or self.last_ts is None:
            return 0
        return max(0, int((self.last_ts - self.first_ts) / 60))

    def repo(self) -> str:
        """从 cwd 推 repo 名。默认假设 cwd 形如 `/<WORKSPACE_SEGMENT>/<repo>/...`。

        可通过 env `DR_WORKSPACE_SEGMENT` 覆盖目录段名（默认 `workspace`）。
        裸根或 None 时返回 unknown / workspace-root。
        """
        if not self.cwd:
            return "unknown"
        parts = Path(self.cwd).parts
        segment = os.environ.get("DR_WORKSPACE_SEGMENT", "workspace")
        try:
            ws = parts.index(segment)
        except ValueError:
            return "unknown"
        if ws + 1 < len(parts):
            return parts[ws + 1]
        return f"{segment}-root"

    def action_mode(self) -> str:
        """五档互斥分类；同分按优先级 write > merge > review > diagnose > discussion。

        分类要点：
        - git 只读命令（git log/show/diff/blame/status 等）计入 review 的"读代码"，
          不计入 diagnose 的"运维查询"——code review 会大量用这类命令。
        - diagnose 只认非 git 的只读 Bash（curl/cat/ls/tail/find 等）。
        """
        read_total = self.read_count + self.git_read_count
        if self.edit_count >= 5 or self.bash_commit_count >= 1:
            return "write"
        if self.bash_merge_count >= 1 and self.edit_count < 3:
            return "merge"
        if self.edit_count < 3 and read_total >= 5:
            return "review"
        if self.edit_count < 3 and self.bash_readonly_nongit >= 5:
            return "diagnose"
        if self.tool_total <= 2:
            return "discussion"
        # 兜底：有 edit 但不满 5 也没 commit——归 write（量小但确实在改）
        if self.edit_count >= 1:
            return "write"
        return "discussion"


GIT_READ_SUBCMDS = {
    "log", "show", "diff", "blame", "status", "branch", "remote",
    "merge-base", "ls-files", "ls-tree", "rev-parse", "rev-list",
    "config", "describe", "name-rev", "reflog",
}
# 非 git 的只读 shell 命令（一级 token 判断）
NONGIT_READONLY_BASH = {
    "ls", "cat", "head", "tail", "pwd", "find", "grep", "rg",
    "wc", "file", "stat", "tree", "curl", "wget", "which", "whereis",
    "echo", "printf", "env",
}


def process_jsonl(
    path: Path, window_start: float, window_end: float
) -> SessionStat | None:
    stat = SessionStat(session_id=path.stem, path=path)
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = parse_iso(msg.get("timestamp", ""))
                if ts is None:
                    continue
                if not (window_start <= ts < window_end):
                    continue
                # cwd 用第一条有 cwd 的消息（消息级 cwd 可能为 None，比如 queue-operation）
                if stat.cwd is None:
                    c = msg.get("cwd")
                    if c:
                        stat.cwd = c
                stat.msg_count += 1
                if stat.first_ts is None or ts < stat.first_ts:
                    stat.first_ts = ts
                if stat.last_ts is None or ts > stat.last_ts:
                    stat.last_ts = ts

                if msg.get("type") != "assistant":
                    continue
                inner = msg.get("message", {}) or {}
                usage = inner.get("usage") or {}
                # 累加 token；cache_* 不计入"新增 token"，只看 input_tokens / output_tokens
                stat.tokens_in += int(usage.get("input_tokens") or 0)
                stat.tokens_out += int(usage.get("output_tokens") or 0)

                content = inner.get("content", [])
                if not isinstance(content, list):
                    continue
                for c in content:
                    if not (isinstance(c, dict) and c.get("type") == "tool_use"):
                        continue
                    stat.tool_total += 1
                    name = c.get("name") or ""
                    if name in ("Edit", "Write", "NotebookEdit"):
                        stat.edit_count += 1
                    elif name in ("Read", "Grep", "Glob"):
                        stat.read_count += 1
                    elif name == "Bash":
                        stat.bash_total += 1
                        cmd = (c.get("input") or {}).get("command", "") or ""
                        prefix = extract_bash_prefix(cmd)
                        stat.bash_prefix_samples[prefix] = (
                            stat.bash_prefix_samples.get(prefix, 0) + 1
                        )
                        first_tok = cmd.strip().split()[0] if cmd.strip() else ""
                        second_tok = (
                            cmd.strip().split()[1]
                            if len(cmd.strip().split()) > 1
                            else ""
                        )
                        # write 类 Bash
                        if first_tok == "git" and second_tok == "commit":
                            stat.bash_commit_count += 1
                        elif first_tok == "gh" and second_tok == "pr" and "create" in cmd:
                            stat.bash_commit_count += 1
                        elif first_tok == "gh" and second_tok == "pr" and "merge" in cmd:
                            stat.bash_merge_count += 1
                        # 只读分类：git 只读 vs 非 git 只读
                        if first_tok == "git" and second_tok in GIT_READ_SUBCMDS:
                            stat.git_read_count += 1
                        elif first_tok == "gh" and second_tok == "api":
                            # gh api 默认当 readonly（外部查询类）
                            stat.bash_readonly_nongit += 1
                        elif first_tok in NONGIT_READONLY_BASH:
                            stat.bash_readonly_nongit += 1
    except OSError as e:
        print(f"[build-work-map] WARN: unable to read {path}: {e}", file=sys.stderr)
        return None

    if stat.msg_count == 0:
        return None
    return stat


def format_k(n: int) -> str:
    if n >= 1000:
        return f"{n // 1000}k"
    return str(n)


def render(stats: list[SessionStat]) -> str:
    lines: list[str] = []
    lines.append("# 工作地图（窗口内 Claude session 活动分布）")
    lines.append("")
    lines.append(
        "**用途**：此表是反方的注意力先验。按 `action_mode` 权重分配火力；"
        "不要被大体积但 `action_mode=review/merge` 的 session 带偏。"
    )
    lines.append("")
    lines.append(
        "**`action_mode` 定义**（按 tool_use 确定性计数得出，非 LLM 判断）："
    )
    lines.append(
        "- `write`：`Edit`/`Write` ≥ 5，或出现 `git commit` / `gh pr create`。当天主动开发。"
    )
    lines.append(
        "- `merge`：出现 `gh pr merge` 且几乎无 `Edit`。按之前决策执行合并动作。"
    )
    lines.append(
        "- `review`：`Read`/`Grep`/`Glob` 为主，`Edit` < 3 且无 commit。只读代码给意见，**不是当天新决策**。"
    )
    lines.append(
        "- `diagnose`：`Bash(ls/cat/grep/tail/curl/gh api)` 多但 `Edit` < 3。运维/诊断。"
    )
    lines.append(
        "- `discussion`：几乎无 tool_use。纯对话。"
    )
    lines.append("")
    lines.append(
        "| session_id | repo | action_mode | dur_min | edit | read | git_read | bash_ro | commit | merge | tok_in | tok_out |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    # 按 action_mode 权重排序：write 优先，discussion 垫底
    weight = {"write": 0, "diagnose": 1, "review": 2, "merge": 3, "discussion": 4}
    stats_sorted = sorted(
        stats,
        key=lambda s: (weight.get(s.action_mode(), 9), -s.tokens_out, s.session_id),
    )
    for s in stats_sorted:
        sid = s.session_id[:12]
        lines.append(
            f"| `{sid}` | {s.repo()} | **{s.action_mode()}** | {s.duration_min} | "
            f"{s.edit_count} | {s.read_count} | {s.git_read_count} | "
            f"{s.bash_readonly_nongit} | {s.bash_commit_count} | {s.bash_merge_count} | "
            f"{format_k(s.tokens_in)} | {format_k(s.tokens_out)} |"
        )
    lines.append("")
    lines.append("## 读法（硬规则）")
    lines.append("")
    lines.append(
        "1. 质疑火力**按 `action_mode=write` 的 session 优先**；"
        "`review`/`merge`/`discussion` 类 session 默认不作为主攻面。"
    )
    lines.append(
        "2. 允许质疑 `review` session 的**判断质量**（review 意见本身有没有盲点），"
        "但**不允许质疑被 review 代码的内部设计**——那不是当天 Claude 的决策。"
    )
    lines.append(
        "3. 若对某个非 `write` 类 session 深挖，正文必须显式说明"
        "「为何突破默认分配」，否则视为被材料体积带偏（反方失败模式）。"
    )
    lines.append(
        "4. 工作地图是**客观统计**（`tool_use` 计数 + 时长），不是"
        "「总结」或「反思」——可作为先验使用；但其他任何 LLM 生成的总结性文字"
        "（`session-cards.md` 的「事件摘要 / 认知增量 / 残留问题」）仍不可信任。"
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-start", required=True, type=float)
    parser.add_argument("--window-end", required=True, type=float)
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--output")
    ns = parser.parse_args()

    out_path = Path(
        ns.output or f"/tmp/daily-report-work-map-{ns.target_date}.md"
    )

    stats: list[SessionStat] = []
    for jsonl in iter_top_level_jsonl(ns.window_start, ns.window_end):
        s = process_jsonl(jsonl, ns.window_start, ns.window_end)
        if s is not None:
            stats.append(s)

    if not stats:
        out_path.write_text(
            "# 工作地图\n\n窗口内无 session 活动。\n",
            encoding="utf-8",
        )
        print(str(out_path))
        return 0

    out_path.write_text(render(stats), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
