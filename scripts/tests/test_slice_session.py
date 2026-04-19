#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


_HERE = Path(__file__).resolve().parent
_SCRIPT_PATH = _HERE.parent / "session" / "slice-session.py"
_spec = importlib.util.spec_from_file_location("slice_session", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
slice_session = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(slice_session)  # type: ignore[attr-defined]


WINDOW_START = "2026-04-16T16:00:00Z"
WINDOW_END = "2026-04-17T16:00:00Z"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _user(ts: str, text: str) -> dict:
    return {
        "type": "user",
        "timestamp": ts,
        "message": {"content": [{"type": "text", "text": text}]},
    }


def _assistant(ts: str, content: list[dict]) -> dict:
    return {"type": "assistant", "timestamp": ts, "message": {"content": content}}


class SliceSessionTests(unittest.TestCase):
    def test_build_slice_filters_window_and_keeps_key_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "abc.jsonl"
            _write_jsonl(
                session,
                [
                    _user("2026-04-16T15:59:59Z", "outside"),
                    _user("2026-04-16T16:00:00Z", "please fix auth bug"),
                    _assistant(
                        "2026-04-16T16:01:00Z",
                        [
                            {
                                "type": "tool_use",
                                "name": "Read",
                                "id": "t1",
                                "input": {"file_path": "src/auth.ts"},
                            },
                            {"type": "text", "text": "I found a failing guard."},
                        ],
                    ),
                    {
                        "type": "user",
                        "timestamp": "2026-04-16T16:02:00Z",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "t1",
                                    "is_error": True,
                                    "content": "Error: denied",
                                }
                            ]
                        },
                    },
                    _user("2026-04-17T16:00:00Z", "outside end"),
                ],
            )

            content, stats = slice_session.build_slice(
                session_file=session,
                window_start=WINDOW_START,
                window_end=WINDOW_END,
                max_bytes=50_000,
                max_field_chars=200,
                max_tool_input_chars=200,
                max_tool_result_chars=200,
            )

            self.assertIn("please fix auth bug", content)
            self.assertIn("tool_use: Read", content)
            self.assertIn("src/auth.ts", content)
            self.assertIn("tool_result_error: t1", content)
            self.assertIn("Error: denied", content)
            self.assertNotIn("outside end", content)
            self.assertEqual(stats["included_events"], 3)

    def test_build_slice_enforces_total_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "big.jsonl"
            rows = [_user("2026-04-16T16:00:00Z", f"msg {i} " + ("x" * 200)) for i in range(20)]
            _write_jsonl(session, rows)

            content, stats = slice_session.build_slice(
                session_file=session,
                window_start=WINDOW_START,
                window_end=WINDOW_END,
                max_bytes=2_000,
                max_field_chars=500,
                max_tool_input_chars=200,
                max_tool_result_chars=200,
            )

            self.assertLessEqual(len(content.encode("utf-8")), 2_000)
            self.assertGreater(stats["omitted_events"], 0)
            self.assertIn("omitted_events_due_to_budget", content)

    def test_write_chunked_slice_creates_small_index_and_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "slice.index.md"
            chunk_dir = root / "chunks"
            chunks, index_size = slice_session.write_chunked_slice(
                content="## a\n" + ("x" * 40) + "\n## b\n" + ("y" * 40),
                output=output,
                chunk_dir=chunk_dir,
                chunk_chars=50,
            )

            self.assertGreaterEqual(chunks, 2)
            self.assertGreater(index_size, 0)
            index = output.read_text(encoding="utf-8")
            self.assertIn("read_order", index)
            self.assertIn("chunk-001.md", index)
            self.assertTrue((chunk_dir / "chunk-001.md").exists())


if __name__ == "__main__":
    unittest.main()
