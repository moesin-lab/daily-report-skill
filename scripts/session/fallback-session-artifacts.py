#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create deterministic fallback session artifacts.

This script removes main-agent hand work from two mechanical cases:

- after session-reader calls, ensure every kept sid has phase1 md + facet json;
- after the single lint retry, overwrite failed md/facet targets with legal fallback files.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def sid_from_session_path(path: str) -> str:
    name = Path(path).name
    return name[:-6] if name.endswith(".jsonl") else Path(name).stem


def read_kept_sids(run_dir: Path) -> list[str]:
    kept = run_dir / "kept-sessions.txt"
    if not kept.exists():
        return []
    sids: list[str] = []
    for raw in kept.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line:
            sids.append(sid_from_session_path(line))
    return sids


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError(f"{path} is not a JSON object")
    return obj


def fallback_card(sid: str) -> str:
    return f"""## session {sid}

- **工作类型**: 其他
- **状态**: 无需交付
- **聚类锚点**:
  - repo: null
  - branch_or_pr: null
  - issue_or_bug: null
  - files:
    - (无)
  - target_object: null
- **关联事件**: 无

### 事件摘要

本 session 未能生成有效卡片，已使用机械降级模板。

### 认知增量

无

### 残留问题

无
"""


def fallback_facet(sid: str, metadata: dict[str, Any], reason: str) -> dict[str, Any]:
    facet = dict(metadata)
    facet.update(
        {
            "goal": "其他",
            "goal_detail": "session 读取失败",
            "satisfaction": "unsure",
            "friction_types": [],
            "anchors": {
                "repo": None,
                "branch_or_pr": None,
                "issue_or_bug": None,
                "target_object": None,
                "files": [],
            },
            "first_prompt_summary": "session 读取失败",
            "summary": "本 session 未能生成有效 facet，已使用机械降级模板。",
            "status": "无需交付",
            "runtime_warning": reason[:180],
        }
    )
    return facet


def write_card(run_dir: Path, sid: str, overwrite: bool) -> bool:
    path = run_dir / f"phase1-{sid}.md"
    if not overwrite and path.exists() and path.stat().st_size > 0:
        return False
    path.write_text(fallback_card(sid), encoding="utf-8")
    return True


def write_facet(run_dir: Path, sid: str, reason: str, overwrite: bool) -> bool:
    path = run_dir / f"facet-{sid}.json"
    if not overwrite and path.exists() and path.stat().st_size > 0:
        return False
    metadata_path = run_dir / f"metadata-{sid}.json"
    metadata = load_json(metadata_path)
    facet = fallback_facet(sid, metadata, reason)
    path.write_text(json.dumps(facet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def append_runtime_issue(run_dir: Path, text: str) -> None:
    path = run_dir / "runtime-issues.txt"
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    if text not in existing:
        existing.append(text)
        path.write_text("\n".join(existing) + "\n", encoding="utf-8")


def ensure_all(run_dir: Path) -> tuple[int, int]:
    cards = 0
    facets = 0
    for sid in read_kept_sids(run_dir):
        if write_card(run_dir, sid, overwrite=False):
            cards += 1
        if write_facet(run_dir, sid, "session-reader 缺失 facet，已机械降级", overwrite=False):
            facets += 1
    if cards or facets:
        append_runtime_issue(run_dir, f"session-reader 缺产物已机械降级: md {cards} / facet {facets}")
    return cards, facets


def fallback_lint_failures(run_dir: Path) -> tuple[int, int, list[str]]:
    report_path = run_dir / "lint-report.json"
    if not report_path.exists():
        return 0, 0, []
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, list):
        raise ValueError("lint-report.json must be a list")

    md_sids: set[str] = set()
    facet_sids: set[str] = set()
    for entry in report:
        if not isinstance(entry, dict):
            continue
        sid = entry.get("sid")
        target = entry.get("target")
        if not isinstance(sid, str):
            continue
        if target == "md":
            md_sids.add(sid)
        elif target == "facet":
            facet_sids.add(sid)

    for sid in sorted(md_sids):
        write_card(run_dir, sid, overwrite=True)
    for sid in sorted(facet_sids):
        write_facet(run_dir, sid, "phase1/facet lint 二次失败，已机械降级", overwrite=True)

    failed_sids = sorted(md_sids | facet_sids)
    if failed_sids:
        append_runtime_issue(run_dir, "phase1/facet lint 二次失败: " + ", ".join(failed_sids))
    return len(md_sids), len(facet_sids), failed_sids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", default=os.environ.get("RUN_DIR"))
    parser.add_argument("--ensure-all", action="store_true")
    parser.add_argument("--from-lint-report", action="store_true")
    ns = parser.parse_args()

    if not ns.run_dir:
        parser.error("--run-dir or RUN_DIR is required")
    run_dir = Path(ns.run_dir).expanduser().resolve()
    if not run_dir.is_dir():
        parser.error(f"run dir does not exist: {run_dir}")

    if not ns.ensure_all and not ns.from_lint_report:
        parser.error("choose --ensure-all and/or --from-lint-report")

    if ns.ensure_all:
        cards, facets = ensure_all(run_dir)
        print(f"[fallback-session-artifacts] ensured missing artifacts: md={cards} facet={facets}")
    if ns.from_lint_report:
        cards, facets, sids = fallback_lint_failures(run_dir)
        print(
            "[fallback-session-artifacts] lint fallback: "
            f"md={cards} facet={facets} sids={','.join(sids)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
