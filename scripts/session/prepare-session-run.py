#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepare daily-report session pipeline run directory.

This script replaces the workflow's ad hoc shell blocks for:
- RUN_DIR creation when bootstrap was not used
- primary session discovery when bootstrap was not used
- short-session filtering
- facet cache copy
- metadata extraction
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _date_parts(target_date: str) -> tuple[str, str, str]:
    parts = target_date.split("-")
    if len(parts) != 3:
        raise ValueError("target date must be YYYY-MM-DD")
    return parts[0], parts[1], parts[2]


def _read_paths(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return [Path(line.strip()) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-start", type=int, required=True)
    parser.add_argument("--window-end", type=int, required=True)
    parser.add_argument("--window-start-iso", required=True)
    parser.add_argument("--window-end-iso", required=True)
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--run-dir")
    parser.add_argument("--session-files", help="Existing session-files.txt from bootstrap")
    parser.add_argument(
        "--projects-root",
        default=os.environ.get("CLAUDE_PROJECTS_ROOT", "~/.claude/projects"),
    )
    # Default derived from BLOG_FACETS_ROOT / BLOG_DIR; pass explicit flag to override.
    default_blog_facets = (
        os.environ.get("BLOG_FACETS_ROOT")
        or (os.path.join(os.environ["BLOG_DIR"], "facets", "facets") if os.environ.get("BLOG_DIR") else None)
    )
    parser.add_argument(
        "--blog-facets-root",
        default=default_blog_facets,
        required=default_blog_facets is None,
    )
    parser.add_argument(
        "--skill-dir",
        default=str(Path(__file__).resolve().parents[2]),
        help="daily-report skill directory",
    )
    ns = parser.parse_args()

    skill_dir = Path(ns.skill_dir).expanduser().resolve()
    scripts_dir = skill_dir / "scripts"
    run_dir = Path(ns.run_dir or f"/tmp/dr-{ns.target_date}")
    if run_dir.exists() and not ns.session_files:
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    session_files = run_dir / "session-files.txt"
    if ns.session_files:
        source_session_files = Path(ns.session_files).expanduser()
        if source_session_files.resolve() != session_files.resolve():
            shutil.copy2(source_session_files, session_files)
    else:
        subprocess.run(
            [
                sys.executable,
                str(scripts_dir / "collect" / "find-sessions.py"),
                "--projects-root",
                ns.projects_root,
                "--window-start",
                str(ns.window_start),
                "--window-end",
                str(ns.window_end),
                "--exclude-subagents",
                "--output",
                str(session_files),
            ],
            check=True,
        )

    subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "session" / "filter-sessions.py"),
            "--input",
            str(session_files),
            "--window-start",
            ns.window_start_iso,
            "--window-end",
            ns.window_end_iso,
        ],
        check=True,
        stdout=sys.stderr,
        env={**os.environ, "RUN_DIR": str(run_dir)},
    )

    kept = _read_paths(run_dir / "kept-sessions.txt")
    yyyy, mm, dd = _date_parts(ns.target_date)
    blog_day = Path(ns.blog_facets_root) / yyyy / mm / dd
    cached = 0
    for jsonl_path in kept:
        sid = jsonl_path.stem
        cached_facet = blog_day / f"{sid}.json"
        if not cached_facet.exists():
            continue
        try:
            if cached_facet.stat().st_mtime >= jsonl_path.stat().st_mtime:
                shutil.copy2(cached_facet, run_dir / f"facet-{sid}.json")
                cached += 1
        except OSError:
            continue

    for jsonl_path in kept:
        subprocess.run(
            [
                sys.executable,
                str(scripts_dir / "session" / "extract-metadata.py"),
                "--session-file",
                str(jsonl_path),
                "--window-start",
                ns.window_start_iso,
                "--window-end",
                ns.window_end_iso,
                "--target-date",
                ns.target_date,
            ],
            check=True,
            stdout=sys.stderr,
            env={**os.environ, "RUN_DIR": str(run_dir)},
        )

    print(f"export RUN_DIR='{run_dir}'")
    print(f"export SESSION_FILES_FILE='{session_files}'")
    print(f"[prepare-session-run] sessions={len(_read_paths(session_files))} kept={len(kept)} cached_facets={cached}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
