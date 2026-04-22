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
    def _run_bootstrap(
        self,
        run_dir: Path,
        state_dir: Path,
        projects: str,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        # bootstrap.py auto-loads SKILL_DIR/.env on import; the loader's
        # contract is "if key is already in os.environ, leave it alone".
        # Tests sit inside the real skill directory, so we can't pick an
        # empty .env — pre-seeding an empty string is the sanctioned way
        # to tell the loader "already set, stay out" without mutating
        # the .env file. extra_env can override with real values.
        env["BLOG_DIR"] = ""
        env["BLOG_FACETS_ROOT"] = ""
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
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
            env=env,
        )

    def test_bootstrap_writes_env_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as projects, tempfile.TemporaryDirectory() as run_tmp:
            run_dir = Path(run_tmp) / "run"
            state_dir = Path(run_tmp) / "state"
            result = self._run_bootstrap(run_dir, state_dir, projects)

            self.assertIn("export TARGET_DATE='2026-04-15'", result.stdout)
            self.assertIn("export BOOTSTRAP_ENV_FILE=", result.stdout)
            self.assertIn(
                f"export SESSION_CARDS_FILE='{run_dir / 'session-cards.md'}'",
                result.stdout,
            )
            self.assertIn(
                f"export OUTSIDE_NOTES_FILE='{run_dir / 'outside-notes.md'}'",
                result.stdout,
            )
            # BLOG_DIR / BLOG_FACETS_ROOT are always exported (possibly
            # empty) so current.env is a single uniform contract;
            # downstream fail-loud comes from `${BLOG_DIR:?}` on empty.
            self.assertIn("export BLOG_DIR=''", result.stdout)
            self.assertIn("export BLOG_FACETS_ROOT=''", result.stdout)

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
            self.assertEqual(summary["SESSION_CARDS_FILE"], str(run_dir / "session-cards.md"))
            self.assertEqual(summary["OUTSIDE_NOTES_FILE"], str(run_dir / "outside-notes.md"))
            self.assertEqual(summary["BLOG_DIR"], "")
            self.assertEqual(summary["BLOG_FACETS_ROOT"], "")

            env = os.environ.copy()
            command = (
                f". {state_dir / 'current.env'}; "
                "printf '%s\\n' \"$TARGET_DATE\" \"$SESSION_CARDS_FILE\" \"$OUTSIDE_NOTES_FILE\""
            )
            sourced = subprocess.run(
                ["bash", "-lc", command],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                sourced.stdout.strip().splitlines(),
                [
                    "2026-04-15",
                    str(run_dir / "session-cards.md"),
                    str(run_dir / "outside-notes.md"),
                ],
            )

    def test_bootstrap_passes_blog_vars_through(self) -> None:
        with tempfile.TemporaryDirectory() as projects, tempfile.TemporaryDirectory() as run_tmp:
            run_dir = Path(run_tmp) / "run"
            state_dir = Path(run_tmp) / "state"
            blog_dir = "/fake/blog"
            result = self._run_bootstrap(
                run_dir,
                state_dir,
                projects,
                extra_env={"BLOG_DIR": blog_dir},
            )

            self.assertIn(f"export BLOG_DIR='{blog_dir}'", result.stdout)
            # BLOG_FACETS_ROOT defaults to $BLOG_DIR/facets/facets when unset.
            expected_facets = f"{blog_dir}/facets/facets"
            self.assertIn(f"export BLOG_FACETS_ROOT='{expected_facets}'", result.stdout)

            summary = json.loads(
                (run_dir / "bootstrap-summary.json").read_text(encoding="utf-8"),
            )
            self.assertEqual(summary["BLOG_DIR"], blog_dir)
            self.assertEqual(summary["BLOG_FACETS_ROOT"], expected_facets)

    def test_bootstrap_honors_explicit_blog_facets_root(self) -> None:
        with tempfile.TemporaryDirectory() as projects, tempfile.TemporaryDirectory() as run_tmp:
            run_dir = Path(run_tmp) / "run"
            state_dir = Path(run_tmp) / "state"
            result = self._run_bootstrap(
                run_dir,
                state_dir,
                projects,
                extra_env={
                    "BLOG_DIR": "/fake/blog",
                    "BLOG_FACETS_ROOT": "/custom/facets/root",
                },
            )
            self.assertIn("export BLOG_FACETS_ROOT='/custom/facets/root'", result.stdout)


if __name__ == "__main__":
    unittest.main()
