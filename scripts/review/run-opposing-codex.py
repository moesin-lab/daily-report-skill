#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the daily-report opposing Codex stage end to end.

This script keeps the existing small scripts as the source of truth:
- build-work-map.py builds the metadata-only attention prior.
- build-opposing-prompt.py builds the actual Codex prompt.
- parse-codex-output.py strips Codex CLI wrapper text.

It only orchestrates the mechanical glue that used to live in workflow prose.
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parents[1]
PUBLISH_DIR = SKILL_DIR / "scripts" / "publish"


def run_python(script: Path, args: list[str]) -> str:
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"{script.name} failed with exit={proc.returncode}\n{proc.stderr.strip()}"
        )
    return proc.stdout.strip()


def tail_text(path: Path, lines: int = 20) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:])


def first_reason(raw: str, limit: int = 180) -> str:
    text = " ".join(line.strip() for line in raw.splitlines()[:6] if line.strip())
    if not text:
        return "empty codex output"
    return text[:limit]


def write_env(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={shlex.quote(value)}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_failure_message(target_date: str, reason: str) -> str:
    return (
        f"日报 {target_date}：反方 agent 失败（{reason[:100]}），"
        "已跳过反方 + 辨析两节，思考章节降级为纯正方叙事"
    )


def notify_failure(target_date: str, reason: str) -> None:
    notifier = os.environ.get("DR_NOTIFY_CMD") or str(PUBLISH_DIR / "send-cc-notification.sh")
    if notifier != ":" and not Path(notifier).exists():
        print(
            f"[run-opposing-codex] warning: notifier not found: {notifier}",
            file=sys.stderr,
        )
        return
    proc = subprocess.run(
        [notifier, build_failure_message(target_date, reason)],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        print(
            "[run-opposing-codex] warning: failure notification failed: "
            f"{proc.stderr.strip() or proc.stdout.strip()}",
            file=sys.stderr,
        )


def send_telegram(target_date: str, run_dir: Path, opposing_file: Path) -> None:
    sender = PUBLISH_DIR / "send-telegram-opposing.sh"
    if not sender.exists():
        print(
            f"[run-opposing-codex] warning: telegram sender not found: {sender}",
            file=sys.stderr,
        )
        return
    env = os.environ.copy()
    env["TARGET_DATE"] = target_date
    env["RUN_DIR"] = str(run_dir)
    proc = subprocess.run(
        [str(sender), str(opposing_file)],
        check=False,
        text=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        print(
            "[run-opposing-codex] warning: telegram send failed: "
            f"{proc.stderr.strip() or proc.stdout.strip()}",
            file=sys.stderr,
        )


def run_codex(
    prompt_file: Path,
    raw_file: Path,
    stderr_file: Path,
    codex_bin: str,
    timeout_sec: int,
) -> int:
    if shutil.which(codex_bin) is None and not Path(codex_bin).exists():
        raw_file.write_text(
            f"CODEX_ERROR: executable not found: {codex_bin}\n",
            encoding="utf-8",
        )
        return 127

    codex_cwd = os.environ.get("CODEX_CWD") or os.getcwd()
    cmd = [
        codex_bin,
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--cd",
        codex_cwd,
    ]
    try:
        with prompt_file.open("rb") as stdin, raw_file.open("wb") as stdout, stderr_file.open(
            "wb"
        ) as stderr:
            proc = subprocess.run(
                cmd,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                timeout=timeout_sec,
                check=False,
            )
            return proc.returncode
    except subprocess.TimeoutExpired:
        err_tail = tail_text(stderr_file, lines=10)
        raw_file.write_text(
            "CODEX_TIMEOUT: codex exec exceeded "
            f"{timeout_sec}s local timeout\n--- last stderr ---\n{err_tail}\n",
            encoding="utf-8",
        )
        return 124
    except OSError as exc:
        raw_file.write_text(
            f"CODEX_ERROR: failed to execute {codex_bin}: {exc}\n",
            encoding="utf-8",
        )
        return 126


def parse_codex(raw_file: Path, output_file: Path, ok_file: Path) -> bool:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "parse-codex-output.py"),
            "--input",
            str(raw_file),
            "--output",
            str(output_file),
            "--status-output",
            str(ok_file),
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode not in (0, 1):
        print(
            "[run-opposing-codex] warning: parse-codex-output failed: "
            f"{proc.stderr.strip() or proc.stdout.strip()}",
            file=sys.stderr,
        )
        ok_file.write_text("0\n", encoding="utf-8")
        return False
    return ok_file.read_text(encoding="utf-8").strip() == "1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", required=True)
    parser.add_argument("--window-start-iso", required=True)
    parser.add_argument("--window-end-iso", required=True)
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--codex-timeout", type=int, default=600)
    parser.add_argument("--notify-failure", action="store_true")
    parser.add_argument("--send-telegram", action="store_true")
    ns = parser.parse_args()

    run_dir = Path(ns.run_dir).expanduser().resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    work_map = Path(
        run_python(
            SCRIPT_DIR / "build-work-map.py",
            [
                "--window-start",
                ns.window_start,
                "--window-end",
                ns.window_end,
                "--target-date",
                ns.target_date,
                "--output",
                str(run_dir / "opposing-work-map.md"),
            ],
        )
    )
    prompt_file = Path(
        run_python(
            SCRIPT_DIR / "build-opposing-prompt.py",
            [
                "--window-start",
                ns.window_start,
                "--window-end",
                ns.window_end,
                "--window-start-iso",
                ns.window_start_iso,
                "--window-end-iso",
                ns.window_end_iso,
                "--target-date",
                ns.target_date,
                "--work-map-path",
                str(work_map),
                "--output",
                str(run_dir / "opposing-prompt.txt"),
            ],
        )
    )

    raw_file = run_dir / "opposing-raw.txt"
    stderr_file = run_dir / "opposing-stderr.txt"
    output_file = run_dir / "opposing.txt"
    ok_file = run_dir / "opposing.ok"
    analysis_file = run_dir / "analysis.txt"

    code = run_codex(
        prompt_file=prompt_file,
        raw_file=raw_file,
        stderr_file=stderr_file,
        codex_bin=ns.codex_bin,
        timeout_sec=ns.codex_timeout,
    )
    if code not in (0, 124, 127):
        raw_tail = tail_text(raw_file, lines=20)
        err_tail = tail_text(stderr_file, lines=20)
        raw_file.write_text(
            f"CODEX_ERROR: exit={code}\n--- stderr ---\n{err_tail}\n"
            f"--- stdout tail ---\n{raw_tail}\n",
            encoding="utf-8",
        )

    ok = parse_codex(raw_file, output_file, ok_file)
    raw_text = raw_file.read_text(encoding="utf-8", errors="replace")

    if ok:
        analysis_file.write_text("", encoding="utf-8")
        if ns.send_telegram:
            send_telegram(ns.target_date, run_dir, output_file)
    else:
        reason = first_reason(raw_text)
        output_file.write_text(
            f"**本次因 codex 失败跳过**（原因：{reason}）\n",
            encoding="utf-8",
        )
        ok_file.write_text("0\n", encoding="utf-8")
        analysis_file.write_text("**反方跳过，辨析不执行**\n", encoding="utf-8")
        if ns.notify_failure:
            notify_failure(ns.target_date, reason)

    env_file = run_dir / "opposing.env"
    write_env(
        env_file,
        {
            "WORK_MAP_FILE": str(work_map),
            "OPPOSING_PROMPT_FILE": str(prompt_file),
            "OPPOSING_RAW_FILE": str(raw_file),
            "OPPOSING_FILE": str(output_file),
            "OPPOSING_OK_FILE": str(ok_file),
            "ANALYSIS_FILE": str(analysis_file),
            "OPPOSING_OK": "1" if ok else "0",
        },
    )

    print(str(env_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
