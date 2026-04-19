# -*- coding: utf-8 -*-
"""Tests for deterministic session workflow helpers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict


SCRIPTS_DIR = Path(__file__).resolve().parent.parent


def metadata(sid: str) -> Dict[str, Any]:
    return {
        "session_id": sid,
        "target_date": "2026-04-15",
        "window_start_iso": "2026-04-14T16:00:00Z",
        "window_end_iso": "2026-04-15T16:00:00Z",
        "start_ts": "2026-04-15T01:00:00Z",
        "end_ts": "2026-04-15T02:00:00Z",
        "duration_minutes": 60,
        "user_message_count": 3,
        "turn_count": 8,
        "tools_used": {"Read": 1},
        "languages": ["python"],
        "raw_stats": {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "tool_errors": 0,
            "user_interruptions": 0,
            "git_commits": 0,
            "git_pushes": 0,
        },
        "schema_version": 1,
    }


def card(sid: str, repo: str, target: str, branch: str = "null") -> str:
    return f"""## session {sid}

- **工作类型**: 修Bug
- **状态**: 已交付
- **聚类锚点**:
  - repo: `{repo}`
  - branch_or_pr: `{branch}`
  - issue_or_bug: null
  - files:
    - `src/watchdog.py`
  - target_object: `{target}`
- **关联事件**: 修 watchdog

### 事件摘要

修复 watchdog。

### 认知增量

无

### 残留问题

无
"""


class TestSessionMechanics(unittest.TestCase):
    def test_fallback_artifacts_pass_lint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            sid = "abc123"
            (run_dir / "kept-sessions.txt").write_text(f"/tmp/{sid}.jsonl\n", encoding="utf-8")
            (run_dir / f"metadata-{sid}.json").write_text(
                json.dumps(metadata(sid), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "session" / "fallback-session-artifacts.py"),
                    "--run-dir",
                    str(run_dir),
                    "--ensure-all",
                ],
                check=True,
            )

            env = os.environ.copy()
            env["RUN_DIR"] = str(run_dir)
            subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "session" / "lint-phase1.py")],
                check=True,
                env=env,
            )
            subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "session" / "lint-facet.py")],
                check=True,
                env=env,
            )
            report = json.loads((run_dir / "lint-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report, [])

    def test_lint_report_fallback_overwrites_failed_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            sid = "bad123"
            (run_dir / f"metadata-{sid}.json").write_text(
                json.dumps(metadata(sid), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (run_dir / f"phase1-{sid}.md").write_text("broken", encoding="utf-8")
            (run_dir / f"facet-{sid}.json").write_text("{}", encoding="utf-8")
            (run_dir / "lint-report.json").write_text(
                json.dumps(
                    [
                        {"sid": sid, "target": "md", "path": str(run_dir / f"phase1-{sid}.md"), "errors": ["bad"]},
                        {"sid": sid, "target": "facet", "path": str(run_dir / f"facet-{sid}.json"), "errors": ["bad"]},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "session" / "fallback-session-artifacts.py"),
                    "--run-dir",
                    str(run_dir),
                    "--from-lint-report",
                ],
                check=True,
            )

            env = os.environ.copy()
            env["RUN_DIR"] = str(run_dir)
            subprocess.run([sys.executable, str(SCRIPTS_DIR / "session" / "lint-phase1.py")], check=True, env=env)
            subprocess.run([sys.executable, str(SCRIPTS_DIR / "session" / "lint-facet.py")], check=True, env=env)
            report = json.loads((run_dir / "lint-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report, [])
            issues = (run_dir / "runtime-issues.txt").read_text(encoding="utf-8")
            self.assertIn("phase1/facet lint 二次失败: bad123", issues)

    def test_build_merge_groups_uses_structured_anchors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "phase1-a.md").write_text(card("a", "cc-connect", "watchdog"), encoding="utf-8")
            (run_dir / "phase1-b.md").write_text(card("b", "cc-connect", "watchdog"), encoding="utf-8")
            (run_dir / "phase1-c.md").write_text(card("c", "blog", "hexo"), encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "session" / "build-merge-groups.py"),
                    "--run-dir",
                    str(run_dir),
                ],
                check=True,
            )

            groups = json.loads((run_dir / "merge-groups.json").read_text(encoding="utf-8"))
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["session_ids"], ["a", "b"])
            self.assertIn("target_object=watchdog", groups[0]["merge_reason"])


if __name__ == "__main__":
    unittest.main()
