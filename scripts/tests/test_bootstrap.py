# -*- coding: utf-8 -*-
"""Tests for daily-report bootstrap entry."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent.parent


class BootstrapTest(unittest.TestCase):
    def test_bootstrap_writes_env_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as projects, tempfile.TemporaryDirectory() as run_tmp:
            run_dir = Path(run_tmp) / "run"
            state_dir = Path(run_tmp) / "state"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "bootstrap.py"),
                    "--args",
                    "2026-04-15",
                    "--projects-root",
                    projects,
                    "--run-dir",
                    str(run_dir),
                    "--state-dir",
                    str(state_dir),
                    "--skip-github",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertIn("export TARGET_DATE='2026-04-15'", result.stdout)
            self.assertIn("export BOOTSTRAP_ENV_FILE=", result.stdout)

            env_file = run_dir / "bootstrap.env"
            summary_file = run_dir / "bootstrap-summary.json"
            self.assertTrue(env_file.is_file())
            self.assertTrue(summary_file.is_file())
            self.assertTrue((run_dir / "session-files.txt").is_file())
            self.assertTrue((run_dir / "token-stats.json").is_file())
            self.assertTrue((run_dir / "github-events.jsonl").is_file())
            self.assertTrue((state_dir / "current.env").is_file())
            self.assertTrue((state_dir / "current-summary.json").is_file())

            summary = json.loads(summary_file.read_text(encoding="utf-8"))
            self.assertEqual(summary["TARGET_DATE"], "2026-04-15")
            self.assertEqual(summary["session_count"], 0)
            self.assertEqual(summary["github_event_count"], 0)
            self.assertEqual(summary["BOOTSTRAP_ENV_FILE"], str(env_file))
            self.assertEqual(summary["CURRENT_BOOTSTRAP_ENV_FILE"], str(state_dir / "current.env"))

            env = os.environ.copy()
            command = f". {state_dir / 'current.env'}; printf '%s\\n' \"$TARGET_DATE\""
            sourced = subprocess.run(
                ["bash", "-lc", command],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(sourced.stdout.strip(), "2026-04-15")


if __name__ == "__main__":
    unittest.main()
