#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bootstrap deterministic inputs for daily-report.

This is the single mechanical entry for:
- resolving the report window
- creating RUN_DIR
- finding primary Claude Code sessions
- aggregating token stats
- collecting optional GitHub events
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"


def _load_dotenv(path: Path) -> list[str]:
    """Load KEY=VALUE pairs from .env without overriding existing env vars.

    Returns list of keys set from this file. Supports: blank lines, `#`
    comments, optional `export` prefix, and values wrapped in single or
    double quotes. No variable interpolation. Stdlib-only by design.
    """
    loaded_keys: list[str] = []
    if not path.exists():
        return loaded_keys
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ[key] = value
        loaded_keys.append(key)
    return loaded_keys


DOTENV_KEYS = _load_dotenv(SKILL_DIR / ".env")


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


resolve_window = _load_module(SCRIPTS_DIR / "window" / "resolve-window.py", "resolve_window")
find_sessions = _load_module(SCRIPTS_DIR / "collect" / "find-sessions.py", "find_sessions")
token_stats = _load_module(SCRIPTS_DIR / "collect" / "token-stats.py", "token_stats")


def _shell_quote(value: str | int) -> str:
    s = str(value)
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _write_lines(path: Path, lines: list[str]) -> None:
    text = "\n".join(lines)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _format_exports(exports: dict[str, str | int | Path]) -> str:
    return "\n".join(f"export {key}={_shell_quote(value)}" for key, value in exports.items()) + "\n"


def _collect_github_events(
    window: dict[str, str | int],
    output: Path,
    runtime_issues: Path,
    github_user: str,
) -> int:
    env = os.environ.copy()
    env.update(
        {
            "WINDOW_START_ISO": str(window["WINDOW_START_ISO"]),
            "WINDOW_END_ISO": str(window["WINDOW_END_ISO"]),
            "GITHUB_USER": github_user,
        }
    )
    script = SCRIPTS_DIR / "collect" / "github-events.sh"
    try:
        result = subprocess.run(
            [str(script)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
    except OSError as exc:
        output.write_text("", encoding="utf-8")
        runtime_issues.write_text(
            f"github events collect failed: {exc}\n",
            encoding="utf-8",
        )
        return 0

    if result.returncode != 0:
        output.write_text("", encoding="utf-8")
        issue = result.stderr.strip() or f"exit={result.returncode}"
        runtime_issues.write_text(
            f"github events collect failed: {issue}\n",
            encoding="utf-8",
        )
        return 0

    output.write_text(result.stdout, encoding="utf-8")
    return len([line for line in result.stdout.splitlines() if line.strip()])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--args", default="", help="Raw args passed to the skill")
    parser.add_argument("--args-file", help="Read raw args from file")
    parser.add_argument("--now-epoch", type=int, help="Override current time for tests")
    parser.add_argument("--run-dir", help="Override RUN_DIR")
    parser.add_argument(
        "--projects-root",
        default=os.environ.get("CLAUDE_PROJECTS_ROOT", "~/.claude/projects"),
    )
    parser.add_argument("--github-user", default=os.environ.get("GITHUB_USER"))
    parser.add_argument("--state-dir", default="/tmp/daily-report")
    parser.add_argument("--skip-github", action="store_true")
    ns = parser.parse_args()

    if not ns.skip_github and not ns.github_user:
        parser.error("--github-user (or GITHUB_USER env) is required unless --skip-github is set")

    raw_args = ns.args
    if ns.args_file:
        raw_args = Path(ns.args_file).read_text(encoding="utf-8")

    window = resolve_window.resolve(raw_args, ns.now_epoch)
    run_dir = Path(ns.run_dir or f"/tmp/dr-{window['TARGET_DATE']}")
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    session_files_file = run_dir / "session-files.txt"
    token_stats_file = run_dir / "token-stats.json"
    github_events_file = run_dir / "github-events.jsonl"
    runtime_issues_file = run_dir / "runtime-issues.txt"
    bootstrap_summary_file = run_dir / "bootstrap-summary.json"
    bootstrap_env_file = run_dir / "bootstrap.env"
    state_dir = Path(ns.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    current_env_file = state_dir / "current.env"
    current_summary_file = state_dir / "current-summary.json"

    session_paths = find_sessions.find_sessions(
        Path(ns.projects_root).expanduser(),
        int(window["WINDOW_START"]),
        int(window["WINDOW_END"]),
        True,
    )
    session_path_strings = [str(path) for path in session_paths]
    _write_lines(session_files_file, session_path_strings)

    stats = token_stats.aggregate(
        token_stats._with_subagents(session_path_strings),
        str(window["WINDOW_START_ISO"]),
        str(window["WINDOW_END_ISO"]),
    )
    token_stats_text = json.dumps(stats, ensure_ascii=False)
    token_stats_file.write_text(token_stats_text + "\n", encoding="utf-8")

    github_event_count = 0
    if ns.skip_github:
        github_events_file.write_text("", encoding="utf-8")
    else:
        github_event_count = _collect_github_events(
            window,
            github_events_file,
            runtime_issues_file,
            ns.github_user,
        )

    summary = {
        **window,
        "RUN_DIR": str(run_dir),
        "SESSION_FILES_FILE": str(session_files_file),
        "TOKEN_STATS_FILE": str(token_stats_file),
        "GITHUB_EVENTS_FILE": str(github_events_file),
        "RUNTIME_ISSUES_FILE": str(runtime_issues_file),
        "BOOTSTRAP_ENV_FILE": str(bootstrap_env_file),
        "CURRENT_BOOTSTRAP_ENV_FILE": str(current_env_file),
        "CURRENT_BOOTSTRAP_SUMMARY_FILE": str(current_summary_file),
        "session_count": len(session_paths),
        "github_event_count": github_event_count,
        "token_stats": stats,
    }
    bootstrap_summary_file.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    exports: dict[str, str | int | Path] = {
        "BRANCH": window["BRANCH"],
        "WINDOW_START": window["WINDOW_START"],
        "WINDOW_END": window["WINDOW_END"],
        "WINDOW_START_ISO": window["WINDOW_START_ISO"],
        "WINDOW_END_ISO": window["WINDOW_END_ISO"],
        "TARGET_DATE": window["TARGET_DATE"],
        "RUN_DIR": run_dir,
        "SESSION_FILES_FILE": session_files_file,
        "TOKEN_STATS_FILE": token_stats_file,
        "GITHUB_EVENTS_FILE": github_events_file,
        "RUNTIME_ISSUES_FILE": runtime_issues_file,
        "BOOTSTRAP_SUMMARY_FILE": bootstrap_summary_file,
        "BOOTSTRAP_ENV_FILE": bootstrap_env_file,
        "CURRENT_BOOTSTRAP_ENV_FILE": current_env_file,
        "CURRENT_BOOTSTRAP_SUMMARY_FILE": current_summary_file,
        "TOKEN_STATS": token_stats_text,
    }
    env_text = _format_exports(exports)
    bootstrap_env_file.write_text(env_text, encoding="utf-8")
    current_env_file.write_text(env_text, encoding="utf-8")
    shutil.copy2(bootstrap_summary_file, current_summary_file)
    print(env_text, end="")

    print(
        "[daily-report] bootstrap window=[{}, {}) label={} branch={} sessions={} github_events={}".format(
            window["WINDOW_START_ISO"],
            window["WINDOW_END_ISO"],
            window["TARGET_DATE"],
            window["BRANCH"],
            len(session_paths),
            github_event_count,
        ),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
