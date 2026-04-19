#!/usr/bin/env python3
"""filter-sessions.py — Wave 1 Worker A

读 $RUN_DIR/session-files.txt（每行一个 jsonl 绝对路径），对每个 jsonl：
  1. 按 [WINDOW_START, WINDOW_END) 精筛窗口内消息
  2. 算 user_message_count（type=="user" + 非空 + 排除纯 tool_result 伪装）
  3. 算 duration_seconds = 窗口内首尾消息 timestamp 差
  4. 应用三条过滤规则（reason 固定词表）：
       subagents_path_leak  -> 路径含 /subagents/
       too_few_user_messages -> user_message_count < 2
       too_short_duration    -> duration_seconds < 60

输出：
  $RUN_DIR/kept-sessions.txt       每行一个保留 jsonl 绝对路径
  $RUN_DIR/filtered-sessions.json  被筛 session 数组（Schema 3）

stdout:
  [filter-sessions] kept=N filtered=M (too_few_user_messages=X too_short_duration=Y subagents_path_leak=Z)

边界：
  - --input 文件不存在 -> exit 2
  - jsonl 自身不存在 / 完全无法 parse 任何行 -> 视为 too_few_user_messages（user_message_count=0, duration_seconds=0）
  - 窗口内无消息 -> duration=0 -> too_short_duration
  - 单行 json parse 失败 -> 跳过该行继续
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------- 时间解析 ----------

def _parse_iso(ts: str) -> Optional[datetime]:
    """解析 ISO 8601 UTC 字符串。支持 'Z' 后缀和 '+00:00'。失败返回 None。"""
    if not isinstance(ts, str) or not ts:
        return None
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------- user_message_count 判定（对齐 Schema 1）----------

def _is_real_user_message(msg: Dict[str, Any]) -> bool:
    """判断一条 type=='user' 的消息是否为用户真实文本输入。

    规则（Schema 1）：
      - content 非空
      - 若 content 是字符串：非空 -> 真实
      - 若 content 是 list：必须存在至少一个 type=='text' 且 text 非空；
        单纯 tool_result / tool_use_result 不算
    """
    if msg.get("type") != "user":
        return False
    message = msg.get("message") or {}
    content = message.get("content")
    if content is None:
        return False
    if isinstance(content, str):
        return content.strip() != ""
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type")
            if ptype == "text":
                text = part.get("text")
                if isinstance(text, str) and text.strip() != "":
                    return True
        return False
    # 其他类型保守判定为非用户真实输入
    return False


# ---------- 单 session 分析 ----------

def analyze_session(jsonl_path: str, window_start: datetime, window_end: datetime) -> Tuple[int, int]:
    """分析单个 jsonl，返回 (user_message_count, duration_seconds)。

    窗口语义：start <= ts < end。
    jsonl 打不开 / 完全无可解析行 -> (0, 0)。
    """
    path = Path(jsonl_path)
    if not path.is_file():
        return 0, 0

    user_count = 0
    first_ts: Optional[datetime] = None
    last_ts: Optional[datetime] = None

    try:
        fp = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return 0, 0

    with fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(msg, dict):
                continue
            ts_raw = msg.get("timestamp")
            ts = _parse_iso(ts_raw) if isinstance(ts_raw, str) else None
            if ts is None:
                continue
            if not (window_start <= ts < window_end):
                continue
            # 首尾时间（消息类型不限，与 Schema 1 对齐：首/末条消息）
            if first_ts is None or ts < first_ts:
                first_ts = ts
            if last_ts is None or ts > last_ts:
                last_ts = ts
            if _is_real_user_message(msg):
                user_count += 1

    if first_ts is None or last_ts is None:
        duration_seconds = 0
    else:
        duration_seconds = int((last_ts - first_ts).total_seconds())
        if duration_seconds < 0:
            duration_seconds = 0

    return user_count, duration_seconds


# ---------- 过滤裁决 ----------

def decide_reason(path: str, user_count: int, duration_seconds: int) -> Optional[str]:
    """返回过滤 reason；None 表示保留。优先级：subagents_path_leak > too_few_user_messages > too_short_duration。"""
    # subagents 路径 sanity check：路径中包含 /subagents/ 片段
    # 用 normpath 防御末尾斜杠 / 相对路径干扰
    norm = os.path.normpath(path).replace(os.sep, "/")
    if "/subagents/" in norm:
        return "subagents_path_leak"
    if user_count < 2:
        return "too_few_user_messages"
    if duration_seconds < 60:
        return "too_short_duration"
    return None


def _session_id_from_path(path: str) -> str:
    """jsonl 文件名去 .jsonl 后缀作 sid。"""
    name = os.path.basename(path)
    if name.endswith(".jsonl"):
        return name[:-len(".jsonl")]
    return name


# ---------- 主流程 ----------

def run_filter(input_file: str, window_start_iso: str, window_end_iso: str, run_dir: str) -> int:
    """核心逻辑。返回 exit code。"""
    input_path = Path(input_file)
    if not input_path.is_file():
        print(f"[filter-sessions] ERROR: input file not found: {input_file}", file=sys.stderr)
        return 2

    window_start = _parse_iso(window_start_iso)
    window_end = _parse_iso(window_end_iso)
    if window_start is None or window_end is None:
        print(
            f"[filter-sessions] ERROR: invalid window iso "
            f"(start={window_start_iso!r}, end={window_end_iso!r})",
            file=sys.stderr,
        )
        return 2

    run_dir_path = Path(run_dir)
    run_dir_path.mkdir(parents=True, exist_ok=True)

    try:
        raw_lines = input_path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        print(f"[filter-sessions] ERROR: cannot read input: {e}", file=sys.stderr)
        return 2

    session_paths: List[str] = [line.strip() for line in raw_lines if line.strip()]

    kept: List[str] = []
    filtered: List[Dict[str, Any]] = []
    reason_counts = {
        "too_few_user_messages": 0,
        "too_short_duration": 0,
        "subagents_path_leak": 0,
    }

    for sp in session_paths:
        user_count, duration_seconds = analyze_session(sp, window_start, window_end)
        reason = decide_reason(sp, user_count, duration_seconds)
        if reason is None:
            kept.append(sp)
            continue
        filtered.append({
            "sid": _session_id_from_path(sp),
            "path": sp,
            "reason": reason,
            "user_message_count": user_count,
            "duration_seconds": duration_seconds,
        })
        reason_counts[reason] += 1

    # 落盘 kept-sessions.txt（每行一个路径，尾部留一个换行）
    kept_path = run_dir_path / "kept-sessions.txt"
    if kept:
        kept_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    else:
        kept_path.write_text("", encoding="utf-8")

    # 落盘 filtered-sessions.json
    filtered_path = run_dir_path / "filtered-sessions.json"
    filtered_path.write_text(
        json.dumps(filtered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        f"[filter-sessions] kept={len(kept)} filtered={len(filtered)} "
        f"(too_few_user_messages={reason_counts['too_few_user_messages']} "
        f"too_short_duration={reason_counts['too_short_duration']} "
        f"subagents_path_leak={reason_counts['subagents_path_leak']})"
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Filter Claude Code session jsonl files by window / activity rules.",
    )
    parser.add_argument("--input", required=True, help="Path to session-files.txt (one jsonl per line).")
    parser.add_argument("--window-start", required=True, help="ISO8601 UTC, inclusive lower bound.")
    parser.add_argument("--window-end", required=True, help="ISO8601 UTC, exclusive upper bound.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    run_dir = os.environ.get("RUN_DIR")
    if not run_dir:
        print("[filter-sessions] ERROR: RUN_DIR env var is required", file=sys.stderr)
        return 2
    return run_filter(
        input_file=args.input,
        window_start_iso=args.window_start,
        window_end_iso=args.window_end,
        run_dir=run_dir,
    )


if __name__ == "__main__":
    sys.exit(main())
