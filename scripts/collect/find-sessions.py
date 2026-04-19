#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find Claude Code jsonl sessions by mtime window."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def find_sessions(
    root: Path, window_start: int, window_end: int, exclude_subagents: bool
) -> list[Path]:
    out: list[Path] = []
    if not root.exists():
        return out
    for path in root.rglob("*.jsonl"):
        if exclude_subagents and "subagents" in path.parts:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if window_start <= mtime < window_end:
            out.append(path)
    return sorted(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--projects-root",
        default=os.environ.get("CLAUDE_PROJECTS_ROOT", "~/.claude/projects"),
    )
    parser.add_argument("--window-start", type=int, required=True)
    parser.add_argument("--window-end", type=int, required=True)
    parser.add_argument("--exclude-subagents", action="store_true")
    parser.add_argument("--output", help="Write paths to file")
    ns = parser.parse_args()

    paths = find_sessions(
        Path(ns.projects_root).expanduser(),
        ns.window_start,
        ns.window_end,
        ns.exclude_subagents,
    )
    text = "\n".join(str(p) for p in paths)
    if text:
        text += "\n"
    if ns.output:
        Path(ns.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
