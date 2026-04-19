#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply daily-report memory candidates to auto-memory files."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


MERGE_PREFIX = "TO MERGE INTO existing file:"


def _load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", required=True)
    parser.add_argument(
        "--memory-dir",
        default=os.environ.get("MEMORY_DIR"),
        help="Memory directory (default from $MEMORY_DIR env; required if env unset)",
    )
    parser.add_argument("--summary-output")
    ns = parser.parse_args()

    if not ns.memory_dir:
        parser.error("--memory-dir (or MEMORY_DIR env) is required")
    memory_dir = Path(ns.memory_dir).expanduser()
    memory_dir.mkdir(parents=True, exist_ok=True)
    index = memory_dir / "MEMORY.md"
    if not index.exists():
        index.write_text("# Memory\n", encoding="utf-8")

    changes: list[str] = []
    for c in _load(Path(ns.candidates)):
        body = str(c.get("body", "")).strip()
        if not body:
            continue
        if body.startswith(MERGE_PREFIX):
            first, _, rest = body.partition("\n")
            target = first[len(MERGE_PREFIX) :].strip()
            target_path = Path(target).expanduser()
            if not target_path.is_absolute():
                target_path = memory_dir / target_path
            with target_path.open("a", encoding="utf-8") as f:
                f.write("\n\n" + rest.strip() + "\n")
            changes.append(f"更新：{target_path.name} — {c.get('description', '')}")
            continue

        filename = str(c.get("filename", "")).strip()
        if not filename:
            continue
        target_path = memory_dir / filename
        if target_path.exists():
            with target_path.open("a", encoding="utf-8") as f:
                f.write("\n\n" + body + "\n")
            changes.append(f"更新：{filename} — {c.get('description', '')}")
        else:
            target_path.write_text(
                "---\n"
                f"name: {c.get('name', '')}\n"
                f"description: {c.get('description', '')}\n"
                f"type: {c.get('type', '')}\n"
                "---\n\n"
                f"{body}\n",
                encoding="utf-8",
            )
            with index.open("a", encoding="utf-8") as f:
                f.write(f"- [{c.get('name', '')}]({filename}) — {c.get('description', '')}\n")
            changes.append(f"新增：{filename} — {c.get('description', '')}")

    summary = "\n".join(changes)
    if ns.summary_output:
        Path(ns.summary_output).write_text(summary + ("\n" if summary else ""), encoding="utf-8")
    else:
        print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
