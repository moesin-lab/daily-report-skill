#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble validated reflection/suggestion/memory candidates."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_validations(path: Path) -> list[dict[str, Any]]:
    vals: list[dict[str, Any]] = []
    if not path.exists():
        return vals
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            obj = {"pass": False, "reason": "validator output is not JSON"}
        vals.append(obj if isinstance(obj, dict) else {"pass": False, "reason": "not object"})
    return vals


def _bullet(c: dict[str, Any]) -> str:
    text = str(c.get("text", "")).strip()
    anchor = str(c.get("锚点", "")).strip()
    return f"- {text}（{anchor}）" if anchor and anchor not in text else f"- {text}"


def _thought_bullet(c: dict[str, Any]) -> str:
    """思考章节两行式：主句独立一行，锚点作为嵌套 bullet 子行。"""
    text = str(c.get("text", "")).strip()
    anchor = str(c.get("锚点", "")).strip()
    if anchor and anchor not in text:
        return f"- **{text}**\n  - 锚点：{anchor}"
    return f"- **{text}**"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--validations", required=True, help="JSONL, one validator result per candidate")
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--output-dir", required=True)
    ns = parser.parse_args()

    out_dir = Path(ns.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates = _read_json(Path(ns.candidates))
    if not isinstance(candidates, list):
        candidates = []
    validations = _read_validations(Path(ns.validations))

    passed: list[dict[str, Any]] = []
    for idx, cand in enumerate(candidates):
        if not isinstance(cand, dict):
            continue
        verdict = validations[idx] if idx < len(validations) else {"pass": False}
        if verdict.get("pass") is True:
            passed.append(cand)

    thoughts = [c for c in passed if c.get("category") == "思考"][:3]
    self_suggestions = [c for c in passed if c.get("category") == "建议-给自己"][:3]
    user_suggestions = [c for c in passed if c.get("category") == "建议-给用户"][:3]
    memories = [c for c in passed if c.get("category") == "memory"][:5]

    reflection_lines: list[str] = []
    if thoughts:
        reflection_lines = ["## 思考", ""] + [_thought_bullet(c) for c in thoughts]
    (out_dir / f"dr-{ns.target_date}-new-reflection.md").write_text(
        "\n".join(reflection_lines).rstrip() + ("\n" if reflection_lines else ""),
        encoding="utf-8",
    )

    suggestion_lines: list[str] = []
    if self_suggestions or user_suggestions:
        suggestion_lines.extend(["## 建议", ""])
        author_label = os.environ.get("AUTHOR_AGENT_NAME", "").strip() or "作者"
        user_label = os.environ.get("USER_NAME", "").strip() or "用户"
        if self_suggestions:
            suggestion_lines.extend([f"### 给自己（{author_label}）", ""])
            suggestion_lines.extend(_bullet(c) for c in self_suggestions)
            suggestion_lines.append("")
        if user_suggestions:
            suggestion_lines.extend([f"### 给用户（{user_label}）", ""])
            suggestion_lines.extend(_bullet(c) for c in user_suggestions)
    (out_dir / f"dr-{ns.target_date}-suggestions.md").write_text(
        "\n".join(suggestion_lines).rstrip() + ("\n" if suggestion_lines else ""),
        encoding="utf-8",
    )

    memory_out: list[dict[str, str]] = []
    for c in memories:
        meta = c.get("memory_meta")
        if not isinstance(meta, dict):
            continue
        memory_out.append(
            {
                "type": str(meta.get("type", "")),
                "name": str(meta.get("name", "")),
                "filename": str(meta.get("filename", "")),
                "description": str(meta.get("description", "")),
                "body": str(c.get("text", "")),
                "rationale": str(c.get("新增认知", "")),
            }
        )
    (out_dir / f"dr-{ns.target_date}-memory-candidates.json").write_text(
        json.dumps(memory_out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "[assemble-candidates] thoughts={} self_suggestions={} user_suggestions={} memory={}".format(
            len(thoughts), len(self_suggestions), len(user_suggestions), len(memory_out)
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
