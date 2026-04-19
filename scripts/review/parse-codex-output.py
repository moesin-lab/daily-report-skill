#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Strip Codex CLI wrapper text and emit assistant content."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse(raw: str) -> tuple[bool, str]:
    first = raw.splitlines()[0] if raw.splitlines() else ""
    if first.startswith("CODEX_TIMEOUT") or first.startswith("CODEX_ERROR"):
        return False, "**本次反方视角生成失败**：`{}`".format(
            "\n".join(raw.splitlines()[:3])
        )

    lines = raw.splitlines()
    started = False
    kept: list[str] = []
    for line in lines:
        if line == "codex" and not started:
            started = True
            continue
        if started and line.startswith("tokens used"):
            break
        if started:
            kept.append(line)
    content = "\n".join(kept).strip()
    if not content:
        content = raw.strip()
    return True, content


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Raw Codex stdout file; stdin if omitted")
    parser.add_argument("--output", help="Write parsed content to file")
    parser.add_argument("--status-output", help="Write 1/0 status to file")
    ns = parser.parse_args()

    raw = Path(ns.input).read_text(encoding="utf-8") if ns.input else sys.stdin.read()
    ok, content = parse(raw)
    if ns.output:
        Path(ns.output).write_text(content + "\n", encoding="utf-8")
    else:
        print(content)
    if ns.status_output:
        Path(ns.status_output).write_text(("1" if ok else "0") + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
