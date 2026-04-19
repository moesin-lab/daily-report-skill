#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build merge-groups.json from phase1 card anchors.

The heuristic is deliberately conservative. It only groups sessions when
structured anchors point to the same work item.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path


NULLS = {"", "null", "none", "无", "(无)", "`null`", "`(无)`"}


@dataclass
class Card:
    sid: str
    path: Path
    work_type: str
    repo: str | None
    branch_or_pr: str | None
    issue_or_bug: str | None
    target_object: str | None
    files: set[str]
    related_event: str


def clean_value(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip().strip("`").strip()
    if value.lower() in NULLS:
        return None
    return value or None


def parse_card(path: Path) -> Card:
    text = path.read_text(encoding="utf-8", errors="replace")
    sid = path.stem[len("phase1-"):]

    def m(pattern: str) -> str | None:
        match = re.search(pattern, text, re.MULTILINE)
        return match.group(1).strip() if match else None

    work_type = clean_value(m(r"^- \*\*工作类型\*\*:\s*(.+)$")) or "其他"
    repo = clean_value(m(r"^  - repo:\s*(.+)$"))
    branch_or_pr = clean_value(m(r"^  - branch_or_pr:\s*(.+)$"))
    issue_or_bug = clean_value(m(r"^  - issue_or_bug:\s*(.+)$"))
    target_object = clean_value(m(r"^  - target_object:\s*(.+)$"))
    related_event = clean_value(m(r"^- \*\*关联事件\*\*:\s*(.+)$")) or ""

    files: set[str] = set()
    in_files = False
    for line in text.splitlines():
        if re.match(r"^  - files:\s*$", line):
            in_files = True
            continue
        if in_files:
            if line.startswith("    - "):
                value = clean_value(line[len("    - "):])
                if value:
                    files.add(value)
                continue
            if line.startswith("  - "):
                in_files = False

    return Card(
        sid=sid,
        path=path,
        work_type=work_type,
        repo=repo,
        branch_or_pr=branch_or_pr,
        issue_or_bug=issue_or_bug,
        target_object=target_object,
        files=files,
        related_event=related_event,
    )


def same_repo_or_unknown(a: Card, b: Card) -> bool:
    return a.repo is None or b.repo is None or a.repo == b.repo


def edge_reason(a: Card, b: Card) -> str | None:
    if a.branch_or_pr and a.branch_or_pr == b.branch_or_pr and same_repo_or_unknown(a, b):
        return f"branch_or_pr={a.branch_or_pr}"
    if a.issue_or_bug and a.issue_or_bug == b.issue_or_bug and same_repo_or_unknown(a, b):
        return f"issue_or_bug={a.issue_or_bug}"
    if a.repo and a.repo == b.repo and a.target_object and a.target_object == b.target_object:
        return f"repo={a.repo} target_object={a.target_object}"
    common_files = sorted(a.files & b.files)
    if a.repo and a.repo == b.repo and common_files:
        return f"repo={a.repo} files={', '.join(common_files[:3])}"
    return None


def connected_components(cards: list[Card]) -> list[tuple[list[Card], list[str]]]:
    parent = {c.sid: c.sid for c in cards}
    reasons: dict[str, list[str]] = {c.sid: [] for c in cards}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: Card, b: Card, reason: str) -> None:
        ra, rb = find(a.sid), find(b.sid)
        if ra != rb:
            parent[rb] = ra
            reasons[ra].extend(reasons.pop(rb, []))
        reasons[find(a.sid)].append(f"{a.sid}+{b.sid}: {reason}")

    for i, a in enumerate(cards):
        for b in cards[i + 1:]:
            reason = edge_reason(a, b)
            if reason:
                union(a, b, reason)

    grouped: dict[str, list[Card]] = {}
    for c in cards:
        grouped.setdefault(find(c.sid), []).append(c)

    out: list[tuple[list[Card], list[str]]] = []
    for root, members in grouped.items():
        if len(members) > 1:
            out.append((sorted(members, key=lambda c: c.sid), reasons.get(root, [])))
    return out


def build_groups(run_dir: Path) -> list[dict[str, object]]:
    cards = [parse_card(p) for p in sorted(run_dir.glob("phase1-*.md")) if p.stat().st_size > 0]
    groups: list[dict[str, object]] = []
    gid = 1
    for members, reasons in connected_components(cards):
        if len(members) > 5:
            continue
        groups.append(
            {
                "group_id": f"g{gid}",
                "session_ids": [c.sid for c in members],
                "merge_reason": "；".join(reasons[:4]),
            }
        )
        gid += 1
    return groups


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", default=os.environ.get("RUN_DIR"))
    parser.add_argument("--output")
    ns = parser.parse_args()

    if not ns.run_dir:
        parser.error("--run-dir or RUN_DIR is required")
    run_dir = Path(ns.run_dir).expanduser().resolve()
    if not run_dir.is_dir():
        parser.error(f"run dir does not exist: {run_dir}")

    output = Path(ns.output).expanduser().resolve() if ns.output else run_dir / "merge-groups.json"
    groups = build_groups(run_dir)
    output.write_text(json.dumps(groups, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[build-merge-groups] groups={len(groups)} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
