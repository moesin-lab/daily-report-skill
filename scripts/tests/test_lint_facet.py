# -*- coding: utf-8 -*-
"""test_lint_facet.py — 单测 lint-facet.py。

Python 3.8+ stdlib only；不用 pytest / 不连 LLM。

跑法：
    cd ~/.claude/skills/daily-report/scripts/
    python3 -m unittest tests.test_lint_facet -v
"""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional

# 脚本名含连字符，不能直接 import；从文件路径加载模块
_THIS_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _THIS_DIR.parent
_LINT_FACET_PATH = _SCRIPTS_DIR / "session" / "lint-facet.py"

_spec = importlib.util.spec_from_file_location("lint_facet", _LINT_FACET_PATH)
assert _spec is not None and _spec.loader is not None, "failed to locate lint-facet.py"
lint_facet_mod = importlib.util.module_from_spec(_spec)
sys.modules["lint_facet"] = lint_facet_mod
_spec.loader.exec_module(lint_facet_mod)


# ------------------------- 构造器 -------------------------

def make_stub_metadata(sid: str = "abc123") -> Dict[str, Any]:
    """严格按 Schema 1 构造一份合法 metadata dict。"""
    return {
        "session_id": sid,
        "target_date": "2026-04-15",
        "window_start_iso": "2026-04-14T16:00:00Z",
        "window_end_iso": "2026-04-15T16:00:00Z",
        "start_ts": "2026-04-15T01:23:45.678Z",
        "end_ts": "2026-04-15T03:45:12.345Z",
        "duration_minutes": 141,
        "user_message_count": 15,
        "turn_count": 38,
        "tools_used": {"Read": 12, "Edit": 3, "Bash": 20},
        "languages": ["bash", "markdown", "python"],
        "raw_stats": {
            "input_tokens": 120000,
            "output_tokens": 8000,
            "cache_creation_input_tokens": 30000,
            "cache_read_input_tokens": 80000,
            "tool_errors": 2,
            "user_interruptions": 1,
            "git_commits": 3,
            "git_pushes": 1,
        },
        "schema_version": 1,
    }


def make_stub_facet(sid: str = "abc123") -> Dict[str, Any]:
    """严格按 Schema 2 构造一份合法 facet dict（机械字段与 make_stub_metadata 一致）。"""
    facet = make_stub_metadata(sid)
    facet.update({
        "goal": "修Bug",
        "goal_detail": "修复 watchdog pgrep 误杀 sshd",
        "satisfaction": "likely_satisfied",
        "friction_types": ["tool_error"],
        "anchors": {
            "repo": "cc-connect",
            "branch_or_pr": "PR #42",
            "issue_or_bug": None,
            "target_object": "watchdog pgrep",
            "files": ["src/watchdog.py"],
        },
        "first_prompt_summary": "修 watchdog 重启不掉",
        "summary": "修复 pgrep 误杀 sshd",
        "status": "已交付",
        "runtime_warning": None,
    })
    return facet


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ------------------------- 纯函数级（lint_facet）测试 -------------------------


class TestLintFacetPureFunc(unittest.TestCase):
    """直接调 lint_facet_mod.lint_facet 拿 errors；不过文件系统，便于密集覆盖。"""

    def test_happy_path_no_errors(self):
        """happy path：合法 facet + 一致 metadata → errors=[]."""
        meta = make_stub_metadata()
        facet = make_stub_facet()
        errs = lint_facet_mod.lint_facet(facet, meta, "abc123")
        self.assertEqual(errs, [], f"expected no errors, got: {errs}")

    def test_missing_goal_field(self):
        meta = make_stub_metadata()
        facet = make_stub_facet()
        del facet["goal"]
        errs = lint_facet_mod.lint_facet(facet, meta, "abc123")
        self.assertIn("missing field: goal", errs)

    def test_goal_not_in_taxonomy(self):
        meta = make_stub_metadata()
        facet = make_stub_facet()
        facet["goal"] = "bug修复"
        errs = lint_facet_mod.lint_facet(facet, meta, "abc123")
        self.assertIn("goal 'bug修复' not in taxonomy", errs)

    def test_friction_types_invalid_element(self):
        meta = make_stub_metadata()
        facet = make_stub_facet()
        facet["friction_types"] = ["not_a_friction"]
        errs = lint_facet_mod.lint_facet(facet, meta, "abc123")
        self.assertTrue(
            any("not_a_friction" in e and "not in taxonomy" in e for e in errs),
            f"expected friction_types taxonomy error, got: {errs}",
        )

    def test_schema_version_wrong(self):
        meta = make_stub_metadata()
        facet = make_stub_facet()
        facet["schema_version"] = 2
        # metadata 也改成 2，避免被机械一致性抢先报 —— 我们要确保 version 本身也报
        meta["schema_version"] = 2
        errs = lint_facet_mod.lint_facet(facet, meta, "abc123")
        self.assertTrue(
            any(e.startswith("schema_version must be 1") for e in errs),
            f"expected schema_version error, got: {errs}",
        )

    def test_mechanical_field_mutated(self):
        meta = make_stub_metadata()
        facet = make_stub_facet()
        meta["duration_minutes"] = 150
        facet["duration_minutes"] = 999
        errs = lint_facet_mod.lint_facet(facet, meta, "abc123")
        self.assertIn("sub-agent mutated mechanical field: duration_minutes", errs)

    def test_missing_metadata_file(self):
        facet = make_stub_facet()
        errs = lint_facet_mod.lint_facet(facet, None, "abc123")
        self.assertIn("missing metadata-abc123.json for consistency check", errs)

    def test_runtime_warning_null_ok(self):
        meta = make_stub_metadata()
        facet = make_stub_facet()
        facet["runtime_warning"] = None
        errs = lint_facet_mod.lint_facet(facet, meta, "abc123")
        self.assertEqual(errs, [])

    def test_runtime_warning_str_ok(self):
        meta = make_stub_metadata()
        facet = make_stub_facet()
        facet["runtime_warning"] = "metadata duration=0 但对话有 20+ 条消息，疑似解析异常"
        errs = lint_facet_mod.lint_facet(facet, meta, "abc123")
        self.assertEqual(errs, [])

    def test_runtime_warning_wrong_type(self):
        meta = make_stub_metadata()
        facet = make_stub_facet()
        facet["runtime_warning"] = 123
        errs = lint_facet_mod.lint_facet(facet, meta, "abc123")
        self.assertTrue(
            any("runtime_warning type invalid" in e for e in errs),
            f"expected runtime_warning type error, got: {errs}",
        )

    def test_anchors_files_not_list(self):
        meta = make_stub_metadata()
        facet = make_stub_facet()
        facet["anchors"]["files"] = "src/watchdog.py"  # 应为 list
        errs = lint_facet_mod.lint_facet(facet, meta, "abc123")
        self.assertTrue(
            any("anchors.files type invalid" in e for e in errs),
            f"expected anchors.files type error, got: {errs}",
        )

    def test_anchors_missing_key(self):
        meta = make_stub_metadata()
        facet = make_stub_facet()
        del facet["anchors"]["repo"]
        errs = lint_facet_mod.lint_facet(facet, meta, "abc123")
        self.assertIn("anchors missing key: repo", errs)

    def test_anchors_files_element_not_str(self):
        meta = make_stub_metadata()
        facet = make_stub_facet()
        facet["anchors"]["files"] = ["ok.py", 123, None]
        errs = lint_facet_mod.lint_facet(facet, meta, "abc123")
        self.assertTrue(
            any("anchors.files[1]" in e for e in errs),
            f"expected element-level anchors.files type error, got: {errs}",
        )

    def test_satisfaction_not_in_taxonomy(self):
        meta = make_stub_metadata()
        facet = make_stub_facet()
        facet["satisfaction"] = "meh"
        errs = lint_facet_mod.lint_facet(facet, meta, "abc123")
        self.assertIn("satisfaction 'meh' not in taxonomy", errs)

    def test_status_not_in_taxonomy(self):
        meta = make_stub_metadata()
        facet = make_stub_facet()
        facet["status"] = "搞定了"
        errs = lint_facet_mod.lint_facet(facet, meta, "abc123")
        self.assertIn("status '搞定了' not in taxonomy", errs)

    def test_friction_types_empty_ok(self):
        """冻结文档：允许空数组。"""
        meta = make_stub_metadata()
        facet = make_stub_facet()
        facet["friction_types"] = []
        errs = lint_facet_mod.lint_facet(facet, meta, "abc123")
        self.assertEqual(errs, [])

    def test_multiple_errors_all_collected(self):
        meta = make_stub_metadata()
        facet = make_stub_facet()
        facet["goal"] = "bug修复"  # taxonomy violation
        facet["schema_version"] = 99  # wrong version
        facet["duration_minutes"] = 7777  # mechanical mutation
        errs = lint_facet_mod.lint_facet(facet, meta, "abc123")
        self.assertIn("goal 'bug修复' not in taxonomy", errs)
        self.assertTrue(any(e.startswith("schema_version must be 1") for e in errs))
        self.assertIn("sub-agent mutated mechanical field: duration_minutes", errs)
        self.assertIn("sub-agent mutated mechanical field: schema_version", errs)

    def test_friction_types_not_list(self):
        meta = make_stub_metadata()
        facet = make_stub_facet()
        facet["friction_types"] = "tool_error"  # 应为 list
        errs = lint_facet_mod.lint_facet(facet, meta, "abc123")
        self.assertTrue(
            any("friction_types type invalid" in e for e in errs),
            f"expected friction_types type error, got: {errs}",
        )


# ------------------------- 端到端（run + main）测试 -------------------------


class TestLintFacetRun(unittest.TestCase):
    """用 TemporaryDirectory 构造 RUN_DIR，跑完整 run() / main()。"""

    def test_happy_path_no_entry(self):
        """pass 的 facet 不入 entry —— 空 run_dir → lint-report.json 为 []。"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            meta = make_stub_metadata("abc123")
            facet = make_stub_facet("abc123")
            write_json(run_dir / "metadata-abc123.json", meta)
            write_json(run_dir / "facet-abc123.json", facet)

            total, failed = lint_facet_mod.run(run_dir)
            self.assertEqual(total, 1)
            self.assertEqual(failed, 0)

            with (run_dir / "lint-report.json").open("r", encoding="utf-8") as f:
                report = json.load(f)
            self.assertEqual(report, [])

    def test_failing_facet_entry_written(self):
        """失败的 facet 入 entry，target=facet 且 errors 完整。"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            meta = make_stub_metadata("abc123")
            facet = make_stub_facet("abc123")
            facet["goal"] = "bug修复"
            facet["duration_minutes"] = 999  # mutate
            write_json(run_dir / "metadata-abc123.json", meta)
            write_json(run_dir / "facet-abc123.json", facet)

            total, failed = lint_facet_mod.run(run_dir)
            self.assertEqual(total, 1)
            self.assertEqual(failed, 1)

            with (run_dir / "lint-report.json").open("r", encoding="utf-8") as f:
                report = json.load(f)
            self.assertEqual(len(report), 1)
            entry = report[0]
            self.assertEqual(entry["sid"], "abc123")
            self.assertEqual(entry["target"], "facet")
            self.assertEqual(entry["path"], str(run_dir / "facet-abc123.json"))
            self.assertIn("goal 'bug修复' not in taxonomy", entry["errors"])
            self.assertIn("sub-agent mutated mechanical field: duration_minutes", entry["errors"])

    def test_multiple_facets_mixed_pass_fail(self):
        """多 facet：pass 不入 entry，fail 入 entry。"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)

            # good facet
            write_json(run_dir / "metadata-goodone.json", make_stub_metadata("goodone"))
            write_json(run_dir / "facet-goodone.json", make_stub_facet("goodone"))

            # bad facet: taxonomy violation
            bad_meta = make_stub_metadata("badone")
            bad_facet = make_stub_facet("badone")
            bad_facet["satisfaction"] = "meh"
            write_json(run_dir / "metadata-badone.json", bad_meta)
            write_json(run_dir / "facet-badone.json", bad_facet)

            total, failed = lint_facet_mod.run(run_dir)
            self.assertEqual(total, 2)
            self.assertEqual(failed, 1)

            with (run_dir / "lint-report.json").open("r", encoding="utf-8") as f:
                report = json.load(f)
            self.assertEqual(len(report), 1)
            self.assertEqual(report[0]["sid"], "badone")
            self.assertEqual(report[0]["target"], "facet")

    def test_missing_metadata_for_facet(self):
        """metadata 缺失 → errors 含 missing metadata-<sid>.json。"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "facet-lonely.json", make_stub_facet("lonely"))

            total, failed = lint_facet_mod.run(run_dir)
            self.assertEqual(total, 1)
            self.assertEqual(failed, 1)

            with (run_dir / "lint-report.json").open("r", encoding="utf-8") as f:
                report = json.load(f)
            self.assertEqual(len(report), 1)
            self.assertIn(
                "missing metadata-lonely.json for consistency check",
                report[0]["errors"],
            )

    def test_empty_run_dir(self):
        """无 facet 文件 → 空 report，不 crash。"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            total, failed = lint_facet_mod.run(run_dir)
            self.assertEqual(total, 0)
            self.assertEqual(failed, 0)

            with (run_dir / "lint-report.json").open("r", encoding="utf-8") as f:
                report = json.load(f)
            self.assertEqual(report, [])

    def test_existing_md_entry_preserved(self):
        """现有 lint-phase1 产出的 md entry 原样保留，lint-facet 追加 facet entry。"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)

            # 模拟 lint-phase1 产出的旧 entry（可能缺 target 字段、也可能带 target=md）
            # 冻结文档要求：旧 entry 原样保留不改
            existing = [
                {
                    "sid": "oldone",
                    "path": "/tmp/dr-2026-04-15/phase1-oldone.md",
                    "errors": ["missing H3 `### 认知增量`"],
                },
                {
                    "sid": "oldtwo",
                    "target": "md",
                    "path": "/tmp/dr-2026-04-15/phase1-oldtwo.md",
                    "errors": ["unresolved placeholder '<仓库名>'"],
                },
            ]
            write_json(run_dir / "lint-report.json", existing)

            # 加一个失败的 facet
            write_json(run_dir / "metadata-newfail.json", make_stub_metadata("newfail"))
            bad = make_stub_facet("newfail")
            bad["status"] = "invalid_status"
            write_json(run_dir / "facet-newfail.json", bad)

            total, failed = lint_facet_mod.run(run_dir)
            self.assertEqual(total, 1)
            self.assertEqual(failed, 1)

            with (run_dir / "lint-report.json").open("r", encoding="utf-8") as f:
                report = json.load(f)

            # 两条旧 entry 原样保留
            self.assertEqual(len(report), 3)
            self.assertEqual(report[0], existing[0])  # 没加 target，也不要擅自升级
            self.assertEqual(report[1], existing[1])
            # 新的 facet entry
            self.assertEqual(report[2]["sid"], "newfail")
            self.assertEqual(report[2]["target"], "facet")
            self.assertTrue(
                any("status 'invalid_status' not in taxonomy" in e for e in report[2]["errors"])
            )

    def test_main_stdout_and_exit_code(self):
        """main() 输出 `[lint-facet] N facets, M failed`，exit 0。"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "metadata-one.json", make_stub_metadata("one"))
            write_json(run_dir / "facet-one.json", make_stub_facet("one"))

            bad_meta = make_stub_metadata("two")
            bad_facet = make_stub_facet("two")
            bad_facet["goal"] = "bad_goal"
            write_json(run_dir / "metadata-two.json", bad_meta)
            write_json(run_dir / "facet-two.json", bad_facet)

            prev_env = os.environ.get("RUN_DIR")
            os.environ["RUN_DIR"] = str(run_dir)
            try:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = lint_facet_mod.main()
                out = buf.getvalue()
            finally:
                if prev_env is None:
                    os.environ.pop("RUN_DIR", None)
                else:
                    os.environ["RUN_DIR"] = prev_env

            self.assertEqual(rc, 0)
            self.assertIn("[lint-facet] 2 facets, 1 failed", out)

    def test_main_missing_run_dir_env_exit_2(self):
        """RUN_DIR 未设 → exit 2。"""
        prev_env = os.environ.get("RUN_DIR")
        if prev_env is not None:
            del os.environ["RUN_DIR"]
        try:
            rc = lint_facet_mod.main()
        finally:
            if prev_env is not None:
                os.environ["RUN_DIR"] = prev_env
        self.assertEqual(rc, 2)

    def test_main_run_dir_not_a_dir_exit_2(self):
        """RUN_DIR 是文件而非目录 → exit 2。"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not a dir")
            not_dir = f.name
        try:
            prev_env = os.environ.get("RUN_DIR")
            os.environ["RUN_DIR"] = not_dir
            try:
                rc = lint_facet_mod.main()
            finally:
                if prev_env is None:
                    os.environ.pop("RUN_DIR", None)
                else:
                    os.environ["RUN_DIR"] = prev_env
            self.assertEqual(rc, 2)
        finally:
            os.unlink(not_dir)

    def test_main_lint_failure_still_exit_0(self):
        """lint 失败不 exit 非 0（冻结约定）。"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            # 故意构造一条 fail
            write_json(run_dir / "metadata-x.json", make_stub_metadata("x"))
            bad = make_stub_facet("x")
            bad["goal"] = "搞事情"
            write_json(run_dir / "facet-x.json", bad)

            prev_env = os.environ.get("RUN_DIR")
            os.environ["RUN_DIR"] = str(run_dir)
            try:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = lint_facet_mod.main()
            finally:
                if prev_env is None:
                    os.environ.pop("RUN_DIR", None)
                else:
                    os.environ["RUN_DIR"] = prev_env
            self.assertEqual(rc, 0)

    def test_optional_insights_fields_taxonomy_checked(self):
        """insights-compatible 可选字段存在时校验 taxonomy；缺失时仍兼容旧 facet。"""
        meta = make_stub_metadata("insight")
        facet = make_stub_facet("insight")
        facet.update({
            "goal_categories": {"fix_bug": 1, "bad_goal": 1},
            "outcome": "fully_achieved",
            "claude_helpfulness": "very_helpful",
            "session_type": "single_task",
            "friction_counts": {"tool_failed": 1},
            "primary_success": "wrong_success",
            "friction_detail": "tool failed once",
            "brief_summary": "用户要修 bug，最终完成",
            "user_instructions": ["以后先跑测试"],
        })

        errs = lint_facet_mod.lint_facet(facet, meta, "insight")
        self.assertTrue(any("goal_categories key 'bad_goal' not in taxonomy" in e for e in errs))
        self.assertTrue(any("primary_success 'wrong_success' not in taxonomy" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
