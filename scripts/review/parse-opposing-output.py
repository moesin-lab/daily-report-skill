#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract opposing-reviewer assistant text from a backend raw dump.

Accepted raw formats:

1. ``codex-companion.mjs task --json`` JSON payload (the default backend). Shape::

       {"status": 0, "rawOutput": "...", "touchedFiles": [...], ...}

   ``status == 0`` ⇒ ok; any other status ⇒ failure, `rawOutput` is surfaced
   as the failure reason.

2. Legacy / fallback plain text (left for other backends or self-authored
   error payloads like ``CODEX_TIMEOUT:`` / ``CODEX_ERROR:``). In this case
   we first look for those sentinels; otherwise we strip the old ``codex
   exec`` banner.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _parse_json_payload(raw: str) -> tuple[bool, str] | None:
    stripped = raw.lstrip()
    if not stripped.startswith("{"):
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or "rawOutput" not in payload:
        return None
    body = str(payload.get("rawOutput", "")).strip()
    status = payload.get("status", 0)
    if status == 0 and body:
        return True, body
    snippet = body[:500] if body else "(empty rawOutput)"
    return False, f"**本次反方视角生成失败**：backend exit={status}；{snippet}"


def _parse_plain_text(raw: str) -> tuple[bool, str]:
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


def parse(raw: str) -> tuple[bool, str]:
    json_result = _parse_json_payload(raw)
    if json_result is not None:
        return json_result
    return _parse_plain_text(raw)


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
