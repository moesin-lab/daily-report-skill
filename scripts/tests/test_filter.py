"""Unit tests for filter-sessions.py (Wave 1 Worker A).

通过 importlib 加载脚本模块（脚本名含连字符，不能直接 import）。
所有 fixture 用 tempfile.TemporaryDirectory 隔离。
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List


# ---------- 加载被测模块 ----------

_HERE = Path(__file__).resolve().parent
_SCRIPT_PATH = _HERE.parent / "session" / "filter-sessions.py"

_spec = importlib.util.spec_from_file_location("filter_sessions", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None, "cannot load filter-sessions.py"
filter_sessions = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(filter_sessions)  # type: ignore[attr-defined]


# ---------- helpers ----------

WINDOW_START = "2026-04-14T16:00:00Z"
WINDOW_END = "2026-04-15T16:00:00Z"


def _user_text_msg(ts: str, text: str = "hi") -> Dict[str, Any]:
    return {
        "type": "user",
        "timestamp": ts,
        "message": {"content": [{"type": "text", "text": text}]},
    }


def _assistant_msg(ts: str) -> Dict[str, Any]:
    return {
        "type": "assistant",
        "timestamp": ts,
        "message": {"content": [{"type": "text", "text": "ok"}]},
    }


def _tool_result_user_msg(ts: str) -> Dict[str, Any]:
    """工具结果伪装的 user 消息，不应计入 user_message_count。"""
    return {
        "type": "user",
        "timestamp": ts,
        "message": {
            "content": [
                {"type": "tool_result", "tool_use_id": "abc", "content": "output"},
            ],
        },
    }


def _write_jsonl(path: Path, msgs: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for m in msgs:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")


def _write_session_files(run_dir: Path, jsonl_paths: List[Path]) -> Path:
    p = run_dir / "session-files.txt"
    p.write_text("\n".join(str(x) for x in jsonl_paths) + "\n", encoding="utf-8")
    return p


def _run(input_file: Path, run_dir: Path) -> int:
    """直接调 run_filter，绕过 argparse/env。"""
    return filter_sessions.run_filter(
        input_file=str(input_file),
        window_start_iso=WINDOW_START,
        window_end_iso=WINDOW_END,
        run_dir=str(run_dir),
    )


def _read_kept(run_dir: Path) -> List[str]:
    txt = (run_dir / "kept-sessions.txt").read_text(encoding="utf-8")
    return [line for line in txt.splitlines() if line.strip()]


def _read_filtered(run_dir: Path) -> List[Dict[str, Any]]:
    return json.loads((run_dir / "filtered-sessions.json").read_text(encoding="utf-8"))


# ---------- tests ----------

class FilterSessionsHappyPathTest(unittest.TestCase):
    def test_mixed_kept_and_filtered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            run_dir = tmp_p / "run"
            run_dir.mkdir()
            sessions_dir = tmp_p / "sessions"
            sessions_dir.mkdir()

            # kept 1: 3 条 user 消息 + 跨度 > 60s
            kept1 = sessions_dir / "kept-aaa.jsonl"
            _write_jsonl(kept1, [
                _user_text_msg("2026-04-15T01:00:00Z"),
                _assistant_msg("2026-04-15T01:00:30Z"),
                _user_text_msg("2026-04-15T01:05:00Z"),
                _user_text_msg("2026-04-15T01:10:00Z"),
            ])

            # kept 2: 2 条 user 消息、跨度 120s，夹杂一条 tool_result user（不计）
            kept2 = sessions_dir / "kept-bbb.jsonl"
            _write_jsonl(kept2, [
                _user_text_msg("2026-04-15T02:00:00Z"),
                _tool_result_user_msg("2026-04-15T02:00:30Z"),
                _user_text_msg("2026-04-15T02:02:00Z"),
            ])

            # filtered: 只有 1 条 user
            filt = sessions_dir / "filt-ccc.jsonl"
            _write_jsonl(filt, [
                _user_text_msg("2026-04-15T03:00:00Z"),
                _assistant_msg("2026-04-15T03:10:00Z"),
            ])

            input_file = _write_session_files(run_dir, [kept1, kept2, filt])
            rc = _run(input_file, run_dir)
            self.assertEqual(rc, 0)

            kept = _read_kept(run_dir)
            self.assertEqual(set(kept), {str(kept1), str(kept2)})

            filtered = _read_filtered(run_dir)
            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0]["sid"], "filt-ccc")
            self.assertEqual(filtered[0]["path"], str(filt))
            self.assertEqual(filtered[0]["reason"], "too_few_user_messages")
            self.assertEqual(filtered[0]["user_message_count"], 1)


class FilterSessionsTooShortDurationTest(unittest.TestCase):
    def test_50s_duration_filtered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            run_dir = tmp_p / "run"
            run_dir.mkdir()
            sess = tmp_p / "short-sid.jsonl"
            _write_jsonl(sess, [
                _user_text_msg("2026-04-15T04:00:00Z"),
                _user_text_msg("2026-04-15T04:00:30Z"),
                _user_text_msg("2026-04-15T04:00:50Z"),  # 跨度 50s
            ])
            input_file = _write_session_files(run_dir, [sess])
            rc = _run(input_file, run_dir)
            self.assertEqual(rc, 0)

            self.assertEqual(_read_kept(run_dir), [])
            filtered = _read_filtered(run_dir)
            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0]["reason"], "too_short_duration")
            self.assertEqual(filtered[0]["duration_seconds"], 50)
            self.assertEqual(filtered[0]["user_message_count"], 3)


class FilterSessionsSingleUserMessageTest(unittest.TestCase):
    def test_single_user_message_filtered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            run_dir = tmp_p / "run"
            run_dir.mkdir()
            sess = tmp_p / "one-user.jsonl"
            _write_jsonl(sess, [
                _user_text_msg("2026-04-15T05:00:00Z"),
                _assistant_msg("2026-04-15T05:30:00Z"),  # duration 1800s
            ])
            input_file = _write_session_files(run_dir, [sess])
            rc = _run(input_file, run_dir)
            self.assertEqual(rc, 0)

            filtered = _read_filtered(run_dir)
            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0]["reason"], "too_few_user_messages")
            self.assertEqual(filtered[0]["user_message_count"], 1)


class FilterSessionsSubagentsPathTest(unittest.TestCase):
    def test_subagents_path_is_filtered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            run_dir = tmp_p / "run"
            run_dir.mkdir()
            # 构造一条路径里含 /subagents/ 的 session，内容哪怕是 happy path
            sub_dir = tmp_p / "projects" / "subagents"
            sub_dir.mkdir(parents=True)
            sess = sub_dir / "leak-sid.jsonl"
            _write_jsonl(sess, [
                _user_text_msg("2026-04-15T06:00:00Z"),
                _user_text_msg("2026-04-15T06:05:00Z"),
                _user_text_msg("2026-04-15T06:10:00Z"),
            ])
            input_file = _write_session_files(run_dir, [sess])
            rc = _run(input_file, run_dir)
            self.assertEqual(rc, 0)

            self.assertEqual(_read_kept(run_dir), [])
            filtered = _read_filtered(run_dir)
            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0]["reason"], "subagents_path_leak")


class FilterSessionsBadJsonlTest(unittest.TestCase):
    def test_corrupt_lines_do_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            run_dir = tmp_p / "run"
            run_dir.mkdir()
            sess = tmp_p / "corrupt.jsonl"
            # 全部行都不可 parse -> user_count=0, duration=0 -> too_few_user_messages
            sess.write_text(
                "\n".join([
                    "not json at all",
                    "{bad:",
                    "}}}",
                ]) + "\n",
                encoding="utf-8",
            )
            input_file = _write_session_files(run_dir, [sess])
            rc = _run(input_file, run_dir)
            self.assertEqual(rc, 0)

            filtered = _read_filtered(run_dir)
            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0]["reason"], "too_few_user_messages")
            self.assertEqual(filtered[0]["user_message_count"], 0)
            self.assertEqual(filtered[0]["duration_seconds"], 0)

    def test_partial_bad_lines_skip_only_bad(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            run_dir = tmp_p / "run"
            run_dir.mkdir()
            sess = tmp_p / "partial.jsonl"
            good = [
                _user_text_msg("2026-04-15T07:00:00Z"),
                _user_text_msg("2026-04-15T07:02:00Z"),
            ]
            lines = [json.dumps(good[0]), "GARBAGE {", json.dumps(good[1])]
            sess.write_text("\n".join(lines) + "\n", encoding="utf-8")
            input_file = _write_session_files(run_dir, [sess])
            rc = _run(input_file, run_dir)
            self.assertEqual(rc, 0)

            kept = _read_kept(run_dir)
            self.assertEqual(kept, [str(sess)])


class FilterSessionsEmptyInputTest(unittest.TestCase):
    def test_empty_session_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            run_dir = tmp_p / "run"
            run_dir.mkdir()
            input_file = run_dir / "session-files.txt"
            input_file.write_text("", encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = _run(input_file, run_dir)
            self.assertEqual(rc, 0)

            self.assertEqual(_read_kept(run_dir), [])
            self.assertEqual(_read_filtered(run_dir), [])
            out = buf.getvalue()
            self.assertIn("kept=0", out)
            self.assertIn("filtered=0", out)


class FilterSessionsMissingInputTest(unittest.TestCase):
    def test_missing_input_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            run_dir = tmp_p / "run"
            run_dir.mkdir()
            rc = _run(tmp_p / "does-not-exist.txt", run_dir)
            self.assertEqual(rc, 2)


class FilterSessionsWindowBoundaryTest(unittest.TestCase):
    def test_out_of_window_messages_ignored(self) -> None:
        """窗口外的消息不应进入 user_count / duration 计算。"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            run_dir = tmp_p / "run"
            run_dir.mkdir()
            sess = tmp_p / "win.jsonl"
            _write_jsonl(sess, [
                _user_text_msg("2026-04-14T15:59:00Z"),  # 窗外
                _user_text_msg("2026-04-15T00:00:00Z"),  # 窗内
                _user_text_msg("2026-04-15T00:02:00Z"),  # 窗内
                _user_text_msg("2026-04-15T16:00:00Z"),  # 窗外（右开）
            ])
            input_file = _write_session_files(run_dir, [sess])
            rc = _run(input_file, run_dir)
            self.assertEqual(rc, 0)

            kept = _read_kept(run_dir)
            self.assertEqual(kept, [str(sess)])


class FilterSessionsSubprocessSmokeTest(unittest.TestCase):
    """以 subprocess 调一次，确认 CLI + env RUN_DIR 形态真能跑起来。"""

    def test_cli_entrypoint(self) -> None:
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            run_dir = tmp_p / "run"
            run_dir.mkdir()
            sess = tmp_p / "cli.jsonl"
            _write_jsonl(sess, [
                _user_text_msg("2026-04-15T08:00:00Z"),
                _user_text_msg("2026-04-15T08:05:00Z"),
            ])
            input_file = _write_session_files(run_dir, [sess])

            env = os.environ.copy()
            env["RUN_DIR"] = str(run_dir)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(_SCRIPT_PATH),
                    "--input", str(input_file),
                    "--window-start", WINDOW_START,
                    "--window-end", WINDOW_END,
                ],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            self.assertIn("[filter-sessions]", proc.stdout)
            self.assertIn("kept=1", proc.stdout)


if __name__ == "__main__":
    unittest.main()
