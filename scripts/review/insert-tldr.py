#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate and insert TL;DR section into a finalized daily-report markdown.

Exit codes:
  0  success — inserted markdown written to --output
  2  validation failed — errors printed to stderr (one per line)
  1  internal error (missing input, unparseable markdown)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Callable, List, Tuple


MAX_CHARS = 400
MIN_CHARS = 100

FRONTMATTER_PATTERN = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
SESSION_ID_PATTERN = re.compile(r"#[0-9a-f]{8}\b")
COMMIT_HASH_PATTERN = re.compile(r"\b[0-9a-f]{7,40}\b")
FILE_WITH_EXT_PATTERN = re.compile(
    r"(?<![\w/])[\w.-]+\.(sh|py|go|md|json|toml|yaml|yml|js|ts|rs|sql|tsx|jsx|mjs|cjs)\b"
)
ABS_PATH_PATTERN = re.compile(r"(?:^|[^\w])/(?:\w[\w.-]*/)+\w[\w.-]*")
TABLE_PIPE_PATTERN = re.compile(r"^\s*\|.*\|", re.MULTILINE)
BULLET_LINE_PATTERN = re.compile(r"^\s*(?:[-*]\s|\d+\.\s)", re.MULTILINE)
VERBAL_TICS = ["喵", "哈哈", "嗯,", "嗯，", "对了,", "对了，"]


def check_length(text: str) -> List[str]:
    stripped = text.strip()
    n = len(stripped)
    if n > MAX_CHARS:
        return [f"length {n} exceeds {MAX_CHARS} chars; trim {n - MAX_CHARS} chars"]
    if n < MIN_CHARS:
        return [f"length {n} below floor {MIN_CHARS}; content too thin"]
    return []


def check_verbal_tics(text: str) -> List[str]:
    errs = []
    for tic in VERBAL_TICS:
        if tic in text:
            errs.append(f"verbal tic {tic!r} forbidden; strip before submitting")
    return errs


def check_session_ids(text: str) -> List[str]:
    hits = SESSION_ID_PATTERN.findall(text)
    return [f"session id references forbidden: {sorted(set(hits))}"] if hits else []


def check_commit_hashes(text: str) -> List[str]:
    hits = [h for h in COMMIT_HASH_PATTERN.findall(text) if not h.isdigit()]
    return [f"commit hashes forbidden: {sorted(set(hits))}"] if hits else []


def check_file_paths(text: str) -> List[str]:
    hits = FILE_WITH_EXT_PATTERN.findall(text)
    abs_hits = ABS_PATH_PATTERN.findall(text)
    errs = []
    if hits:
        samples = sorted(set(FILE_WITH_EXT_PATTERN.findall(text)))
        errs.append(f"file names with extensions forbidden (found {len(hits)}): {samples[:5]}")
    if abs_hits:
        errs.append(f"absolute paths forbidden (found {len(abs_hits)})")
    return errs


def check_structural_markers(text: str) -> List[str]:
    errs = []
    if TABLE_PIPE_PATTERN.search(text):
        errs.append("markdown tables forbidden in TL;DR")
    if BULLET_LINE_PATTERN.search(text):
        errs.append("bullet / numbered lists forbidden in TL;DR")
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            errs.append("heading lines forbidden inside TL;DR body")
            break
    return errs


def check_meta_self_reference(text: str) -> List[str]:
    patterns = [
        "这份 TL;DR",
        "本 TL;DR",
        "以上总结",
        "综上所述",
        "总结一下",
    ]
    hits = [p for p in patterns if p in text]
    return [f"self-referential phrasing forbidden: {hits}"] if hits else []


VALIDATORS: List[Tuple[str, Callable[[str], List[str]]]] = [
    ("length", check_length),
    ("verbal_tics", check_verbal_tics),
    ("session_ids", check_session_ids),
    ("commit_hashes", check_commit_hashes),
    ("file_paths", check_file_paths),
    ("structural", check_structural_markers),
    ("meta_ref", check_meta_self_reference),
]


def validate(text: str) -> List[str]:
    out: List[str] = []
    for name, fn in VALIDATORS:
        for msg in fn(text):
            out.append(f"[{name}] {msg}")
    return out


def insert(markdown: str, tldr_body: str) -> str:
    m = FRONTMATTER_PATTERN.match(markdown)
    if not m:
        raise ValueError("markdown has no leading frontmatter block")
    before = markdown[: m.end()]
    after = markdown[m.end() :].lstrip("\n")
    block = f"\n## TL;DR\n\n{tldr_body.strip()}\n\n"
    return before + block + after


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markdown-path", required=True)
    parser.add_argument("--tldr-path", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--validate-only", action="store_true")
    ns = parser.parse_args()

    md_path = Path(ns.markdown_path)
    tldr_path = Path(ns.tldr_path)
    if not md_path.exists():
        print(f"markdown not found: {md_path}", file=sys.stderr)
        return 1
    if not tldr_path.exists():
        print(f"tldr not found: {tldr_path}", file=sys.stderr)
        return 1

    tldr_text = tldr_path.read_text(encoding="utf-8")
    errors = validate(tldr_text)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 2

    if ns.validate_only:
        return 0

    markdown = md_path.read_text(encoding="utf-8")
    try:
        updated = insert(markdown, tldr_text)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    out_path = Path(ns.output)
    out_path.write_text(updated, encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
