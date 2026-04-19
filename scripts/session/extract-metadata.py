#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract-metadata.py — 从单个 Claude Code jsonl session 文件提取机械指标。

严格按 Daily Report Refactor 冻结文档 Schema 1 产出 metadata-<sid>.json。
零 LLM 调用；stdlib only；幂等（覆盖写）。

CLI:
    RUN_DIR=/tmp/dr-2026-04-15 python3 extract-metadata.py \
        --session-file /abs/path/<sid>.jsonl \
        --window-start 2026-04-14T16:00:00Z \
        --window-end 2026-04-15T16:00:00Z \
        --target-date 2026-04-15
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = 1

# 冻结文档规定的后缀 → 语言映射表；未知后缀忽略，不硬猜
EXT_LANG: Dict[str, str] = {
    "py": "python", "pyi": "python",
    "js": "javascript", "mjs": "javascript", "cjs": "javascript",
    "ts": "typescript", "tsx": "typescript",
    "jsx": "javascript",
    "go": "go",
    "rs": "rust",
    "java": "java",
    "c": "c", "h": "c",
    "cpp": "cpp", "cc": "cpp", "hpp": "cpp", "hh": "cpp",
    "rb": "ruby",
    "php": "php",
    "sh": "bash", "bash": "bash", "zsh": "bash",
    "md": "markdown",
    "yml": "yaml", "yaml": "yaml",
    "toml": "toml",
    "json": "json",
    "html": "html", "htm": "html",
    "css": "css", "scss": "css",
    "sql": "sql",
    "lua": "lua",
    "vim": "vimscript",
    "dockerfile": "docker",
    "tf": "terraform",
}

GIT_COMMIT_RE = re.compile(r"\bgit\s+commit\b", re.IGNORECASE)
GIT_PUSH_RE = re.compile(r"\bgit\s+push\b", re.IGNORECASE)
INTERRUPT_MARK = "[Request interrupted by user]"


# ------------------------- 工具函数 -------------------------

def _parse_iso(ts: str) -> Optional[datetime]:
    """解析 Claude Code jsonl 中的 ISO 时间戳（末尾 Z 或 +00:00）。

    失败返回 None。不抛异常，便于扫描容错。
    """
    if not isinstance(ts, str) or not ts:
        return None
    s = ts
    # Python 3.8 的 fromisoformat 不认 Z
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _in_window(ts: str, start: datetime, end: datetime) -> bool:
    """半开区间 [start, end)（冻结文档 v1.1）。

    start 边界处保留（>=），end 边界处剔除（<）。与 filter-sessions.py 及
    SKILL.md 第一步消息级精筛 `<` 保持一致，保证相邻天窗口拼接零重复。
    """
    dt = _parse_iso(ts)
    if dt is None:
        return False
    return start <= dt < end


def _ext_of(path: str) -> Optional[str]:
    """取路径最后一个 `.` 后的小写后缀；无后缀返回 None。

    特殊：basename 为 `Dockerfile`（无后缀）时返回 `dockerfile`。
    """
    if not isinstance(path, str) or not path:
        return None
    name = os.path.basename(path)
    if not name:
        return None
    # 处理 Dockerfile / dockerfile 之类无后缀文件
    if "." not in name:
        low = name.lower()
        if low == "dockerfile":
            return "dockerfile"
        return None
    ext = name.rsplit(".", 1)[1].lower()
    if not ext:
        return None
    return ext


def _collect_paths_from_tool_input(tool_input: Any) -> List[str]:
    """从 tool_use.input 里收集候选文件路径。

    覆盖冻结文档要求：input.file_path / input.path / input.files[]
    容错：非 dict 输入返回空列表。
    """
    paths: List[str] = []
    if not isinstance(tool_input, dict):
        return paths
    for key in ("file_path", "path"):
        v = tool_input.get(key)
        if isinstance(v, str) and v:
            paths.append(v)
    files = tool_input.get("files")
    if isinstance(files, list):
        for item in files:
            if isinstance(item, str) and item:
                paths.append(item)
    return paths


def _content_list(message: Any) -> List[Any]:
    """安全取 message.content 作为 list（字符串或 None 时返回空 list）。"""
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, list):
        return content
    return []


def _has_user_text(message: Any) -> bool:
    """冻结文档：排除 tool_use_result/tool_result 伪装的 user 消息。

    必须存在 `type == "text"` 且 `text` 非空，或 content 是非空字符串。
    """
    if not isinstance(message, dict):
        return False
    content = message.get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                txt = item.get("text")
                if isinstance(txt, str) and txt.strip():
                    return True
    return False


def _user_has_interrupt_mark(message: Any) -> bool:
    """扫 user message.content[].text 或字符串 content 是否含中断标记。"""
    if not isinstance(message, dict):
        return False
    content = message.get("content")
    if isinstance(content, str):
        return INTERRUPT_MARK in content
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                txt = item.get("text")
                if isinstance(txt, str) and INTERRUPT_MARK in txt:
                    return True
    return False


# ------------------------- 核心扫描 -------------------------

def iter_jsonl(path: str):
    """逐行 yield 解析后的 dict；json 失败跳过 + stderr warning，不 exit。"""
    with open(path, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                print(
                    f"[extract-metadata] WARN {path}:{lineno} json parse failed: {e}",
                    file=sys.stderr,
                )
                continue
            if not isinstance(obj, dict):
                continue
            yield obj


def compute_metadata(
    session_file: str,
    window_start_iso: str,
    window_end_iso: str,
    target_date: str,
) -> Dict[str, Any]:
    """主扫描逻辑；返回完整 metadata dict。

    拆出独立函数便于单测 import。
    """
    sid = os.path.basename(session_file)
    if sid.endswith(".jsonl"):
        sid = sid[: -len(".jsonl")]

    start_dt = _parse_iso(window_start_iso)
    end_dt = _parse_iso(window_end_iso)
    if start_dt is None or end_dt is None:
        raise ValueError(
            f"invalid window iso: start={window_start_iso!r} end={window_end_iso!r}"
        )

    # 累加器
    first_ts: Optional[str] = None
    last_ts: Optional[str] = None
    first_dt: Optional[datetime] = None
    last_dt: Optional[datetime] = None
    user_message_count = 0
    turn_count = 0
    tools_used: Dict[str, int] = {}
    languages_set = set()
    input_tokens = 0
    output_tokens = 0
    cache_creation = 0
    cache_read = 0
    tool_errors = 0
    user_interruptions = 0
    git_commits = 0
    git_pushes = 0

    for obj in iter_jsonl(session_file):
        ts = obj.get("timestamp")
        if not isinstance(ts, str):
            continue
        if not _in_window(ts, start_dt, end_dt):
            continue
        dt = _parse_iso(ts)
        if dt is None:
            continue

        # 窗口内首尾消息时间戳（不限类型）
        if first_dt is None or dt < first_dt:
            first_dt = dt
            first_ts = ts
        if last_dt is None or dt > last_dt:
            last_dt = dt
            last_ts = ts

        mtype = obj.get("type")
        message = obj.get("message")

        if mtype == "user":
            if _has_user_text(message):
                user_message_count += 1
            if _user_has_interrupt_mark(message):
                user_interruptions += 1
            # tool_result (is_error) 计数
            for item in _content_list(message):
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "tool_result" and item.get("is_error") is True:
                    tool_errors += 1

        elif mtype == "assistant":
            turn_count += 1
            # usage 累加
            if isinstance(message, dict):
                usage = message.get("usage")
                if isinstance(usage, dict):
                    input_tokens += int(usage.get("input_tokens") or 0)
                    output_tokens += int(usage.get("output_tokens") or 0)
                    cache_creation += int(usage.get("cache_creation_input_tokens") or 0)
                    cache_read += int(usage.get("cache_read_input_tokens") or 0)
            # tool_use 扫描
            for item in _content_list(message):
                if not isinstance(item, dict):
                    continue
                if item.get("type") != "tool_use":
                    continue
                name = item.get("name")
                if not isinstance(name, str) or not name:
                    continue  # 冻结文档：排除空工具名
                tools_used[name] = tools_used.get(name, 0) + 1

                tool_input = item.get("input")
                # 路径 → 语言
                for p in _collect_paths_from_tool_input(tool_input):
                    ext = _ext_of(p)
                    if ext and ext in EXT_LANG:
                        languages_set.add(EXT_LANG[ext])
                # Bash command 正则统计
                if name == "Bash" and isinstance(tool_input, dict):
                    cmd = tool_input.get("command")
                    if isinstance(cmd, str) and cmd:
                        git_commits += len(GIT_COMMIT_RE.findall(cmd))
                        git_pushes += len(GIT_PUSH_RE.findall(cmd))

    if first_dt is not None and last_dt is not None:
        duration_minutes = int((last_dt - first_dt).total_seconds() / 60)
        start_ts_out: Optional[str] = first_ts
        end_ts_out: Optional[str] = last_ts
    else:
        duration_minutes = 0
        start_ts_out = None
        end_ts_out = None

    result: Dict[str, Any] = {
        "session_id": sid,
        "target_date": target_date,
        "window_start_iso": window_start_iso,
        "window_end_iso": window_end_iso,
        "start_ts": start_ts_out,
        "end_ts": end_ts_out,
        "duration_minutes": duration_minutes,
        "user_message_count": user_message_count,
        "turn_count": turn_count,
        "tools_used": tools_used,
        "languages": sorted(languages_set),
        "raw_stats": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": cache_creation,
            "cache_read_input_tokens": cache_read,
            "tool_errors": tool_errors,
            "user_interruptions": user_interruptions,
            "git_commits": git_commits,
            "git_pushes": git_pushes,
        },
        "schema_version": SCHEMA_VERSION,
    }
    return result


def write_metadata(run_dir: str, metadata: Dict[str, Any]) -> str:
    """幂等覆盖写 $RUN_DIR/metadata-<sid>.json；返回落盘路径。"""
    sid = metadata["session_id"]
    out_path = os.path.join(run_dir, f"metadata-{sid}.json")
    os.makedirs(run_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return out_path


# ------------------------- CLI 入口 -------------------------

def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract mechanical metadata from a Claude Code jsonl session.")
    p.add_argument("--session-file", required=True, help="Absolute path to <sid>.jsonl")
    p.add_argument("--window-start", required=True, help="Window start ISO, e.g. 2026-04-14T16:00:00Z")
    p.add_argument("--window-end", required=True, help="Window end ISO, e.g. 2026-04-15T16:00:00Z")
    p.add_argument("--target-date", required=True, help="YYYY-MM-DD")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)

    run_dir = os.environ.get("RUN_DIR")
    if not run_dir:
        print("[extract-metadata] ERROR: RUN_DIR env var is required", file=sys.stderr)
        return 2

    session_file = args.session_file
    if not os.path.isfile(session_file):
        print(
            f"[extract-metadata] ERROR: session file not found: {session_file}",
            file=sys.stderr,
        )
        return 2
    if not os.access(session_file, os.R_OK):
        print(
            f"[extract-metadata] ERROR: session file not readable: {session_file}",
            file=sys.stderr,
        )
        return 2

    try:
        metadata = compute_metadata(
            session_file=session_file,
            window_start_iso=args.window_start,
            window_end_iso=args.window_end,
            target_date=args.target_date,
        )
    except ValueError as e:
        print(f"[extract-metadata] ERROR: {e}", file=sys.stderr)
        return 2

    write_metadata(run_dir, metadata)
    print(
        f"[extract-metadata] {metadata['session_id']} "
        f"kept={metadata['user_message_count']} turns={metadata['turn_count']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
