#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aggregate Claude Code token usage for a window."""
from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
from typing import Any


def _load_session_files(input_file: Path) -> list[str]:
    if not input_file.exists():
        return []
    return [line.strip() for line in input_file.read_text().splitlines() if line.strip()]


def _with_subagents(paths: list[str]) -> list[str]:
    out = list(paths)
    for f in paths:
        parent = os.path.splitext(f)[0]
        subdir = os.path.join(parent, "subagents")
        if os.path.isdir(subdir):
            out.extend(glob.glob(os.path.join(subdir, "*.jsonl")))
    return out


def aggregate(paths: list[str], window_start_iso: str, window_end_iso: str) -> dict[str, int]:
    stats = {
        "sessions": 0,
        "turns": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    for fpath in paths:
        if not fpath or not os.path.isfile(fpath):
            continue
        session_has_turn = False
        with open(fpath, "r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj: dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "assistant":
                    continue
                msg = obj.get("message")
                if not isinstance(msg, dict) or "usage" not in msg:
                    continue
                ts = obj.get("timestamp", "")
                if ts and not (window_start_iso <= ts < window_end_iso):
                    continue
                usage = msg.get("usage") or {}
                if not isinstance(usage, dict):
                    continue
                stats["input_tokens"] += int(usage.get("input_tokens", 0) or 0)
                stats["output_tokens"] += int(usage.get("output_tokens", 0) or 0)
                stats["cache_creation_input_tokens"] += int(
                    usage.get("cache_creation_input_tokens", 0) or 0
                )
                stats["cache_read_input_tokens"] += int(
                    usage.get("cache_read_input_tokens", 0) or 0
                )
                session_has_turn = True
                stats["turns"] += 1
        if session_has_turn:
            stats["sessions"] += 1
    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="session-files.txt")
    parser.add_argument("--window-start", required=True, help="UTC ISO start")
    parser.add_argument("--window-end", required=True, help="UTC ISO end")
    parser.add_argument("--include-subagents", action="store_true")
    ns = parser.parse_args()

    paths = _load_session_files(Path(ns.input))
    if ns.include_subagents:
        paths = _with_subagents(paths)
    print(json.dumps(aggregate(paths, ns.window_start, ns.window_end), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
