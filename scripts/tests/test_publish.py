# -*- coding: utf-8 -*-
"""test_publish.py — publish-facet.py 的 stdlib unittest。

import 策略：脚本名含短横线，用 importlib.util 从源文件动态加载为模块 publish_facet。
不连 LLM，不依赖 ~/.claude/ 下真实文件；全部用 tempfile.TemporaryDirectory 构造。
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path


# ---------- 动态加载 publish-facet.py ----------
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_PUBLISH_PATH = _SCRIPTS_DIR / "session" / "publish-facet.py"

_spec = importlib.util.spec_from_file_location("publish_facet", _PUBLISH_PATH)
publish_facet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(publish_facet)  # type: ignore[union-attr]


def _write_facet(run_dir: Path, sid: str, payload: dict) -> Path:
    """在 run_dir 下落一个 facet-<sid>.json。"""
    path = run_dir / f"facet-{sid}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def _sample_facet(sid: str, goal: str = "修Bug") -> dict:
    """构造一个最小合法 facet dict（不涉及 lint，仅用于搬运测试）。"""
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
        "goal": goal,
        "goal_detail": "修 watchdog pgrep",
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
        "summary": "修复 pgrep 误杀 sshd 导致 watchdog 无法重启 cc-connect",
        "status": "已交付",
        "schema_version": 1,
    }


class TestParseTargetDate(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(
            publish_facet.parse_target_date("2026-04-15"),
            ("2026", "04", "15"),
        )

    def test_loose_format_rejected(self):
        # 文档要求严格 YYYY-MM-DD；2026-4-15 非法
        with self.assertRaises(ValueError):
            publish_facet.parse_target_date("2026-4-15")

    def test_garbage(self):
        for bad in ["", "2026/04/15", "abcd-ef-gh", "2026-04-15T00:00:00Z", "20260415"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                publish_facet.parse_target_date(bad)

    def test_month_day_range(self):
        with self.assertRaises(ValueError):
            publish_facet.parse_target_date("2026-13-01")
        with self.assertRaises(ValueError):
            publish_facet.parse_target_date("2026-01-32")


class TestExtractSid(unittest.TestCase):
    def test_simple(self):
        p = Path("/tmp/dr/facet-abc123.json")
        self.assertEqual(publish_facet.extract_sid(p), "abc123")

    def test_uuid_like(self):
        p = Path("/tmp/dr/facet-c71de8e0-abc1-def2-1234-567890abcdef.json")
        self.assertEqual(
            publish_facet.extract_sid(p),
            "c71de8e0-abc1-def2-1234-567890abcdef",
        )

    def test_bad_name(self):
        with self.assertRaises(ValueError):
            publish_facet.extract_sid(Path("/tmp/dr/metadata-abc.json"))


class TestRunHappyPath(unittest.TestCase):
    def test_two_facets_published(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            blog_root = Path(td) / "blog"
            run_dir.mkdir()

            facet_a = _sample_facet("abc123")
            facet_b = _sample_facet("xyz789", goal="新功能")
            _write_facet(run_dir, "abc123", facet_a)
            _write_facet(run_dir, "xyz789", facet_b)

            buf_out = io.StringIO()
            with redirect_stdout(buf_out):
                rc = publish_facet.run(str(run_dir), "2026-04-15", str(blog_root))

            self.assertEqual(rc, 0)
            self.assertIn("wrote=2 skipped=0 failed=0", buf_out.getvalue())

            out_dir = blog_root / "2026" / "04" / "15"
            self.assertTrue((out_dir / "abc123.json").is_file())
            self.assertTrue((out_dir / "xyz789.json").is_file())

            # 内容一致
            with (out_dir / "abc123.json").open("r", encoding="utf-8") as f:
                self.assertEqual(json.load(f), facet_a)
            with (out_dir / "xyz789.json").open("r", encoding="utf-8") as f:
                self.assertEqual(json.load(f), facet_b)


class TestIdempotent(unittest.TestCase):
    def test_second_run_all_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            blog_root = Path(td) / "blog"
            run_dir.mkdir()

            _write_facet(run_dir, "abc123", _sample_facet("abc123"))
            _write_facet(run_dir, "xyz789", _sample_facet("xyz789"))

            buf1 = io.StringIO()
            with redirect_stdout(buf1):
                rc1 = publish_facet.run(str(run_dir), "2026-04-15", str(blog_root))
            self.assertEqual(rc1, 0)
            self.assertIn("wrote=2 skipped=0 failed=0", buf1.getvalue())

            # 第二次：源无任何变化 → 全 skipped
            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                rc2 = publish_facet.run(str(run_dir), "2026-04-15", str(blog_root))
            self.assertEqual(rc2, 0)
            self.assertIn("wrote=0 skipped=2 failed=0", buf2.getvalue())

    def test_source_changed_writes(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            blog_root = Path(td) / "blog"
            run_dir.mkdir()

            _write_facet(run_dir, "abc123", _sample_facet("abc123"))
            _write_facet(run_dir, "xyz789", _sample_facet("xyz789"))

            buf1 = io.StringIO()
            with redirect_stdout(buf1):
                publish_facet.run(str(run_dir), "2026-04-15", str(blog_root))

            # 改掉 abc123 的 summary，xyz789 不动
            changed = _sample_facet("abc123")
            changed["summary"] = "新版结论"
            _write_facet(run_dir, "abc123", changed)

            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                rc2 = publish_facet.run(str(run_dir), "2026-04-15", str(blog_root))
            self.assertEqual(rc2, 0)
            self.assertIn("wrote=1 skipped=1 failed=0", buf2.getvalue())

            # 确认目标内容已更新
            out = blog_root / "2026" / "04" / "15" / "abc123.json"
            with out.open("r", encoding="utf-8") as f:
                self.assertEqual(json.load(f)["summary"], "新版结论")


class TestSemanticEquivalence(unittest.TestCase):
    def test_key_order_difference_is_skipped(self):
        """dict 的 key 顺序不同、值相同 → 语义等价 → skipped，不是 wrote。"""
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            blog_root = Path(td) / "blog"
            run_dir.mkdir()
            out_dir = blog_root / "2026" / "04" / "15"
            out_dir.mkdir(parents=True)

            # 源文件：标准顺序
            src_obj = _sample_facet("abc123")
            _write_facet(run_dir, "abc123", src_obj)

            # 目标文件：同样内容但手动写成 key 顺序不同的字节流
            # 用 sort_keys=True 制造不同字节表示但等价语义
            tgt_path = out_dir / "abc123.json"
            with tgt_path.open("w", encoding="utf-8") as f:
                json.dump(src_obj, f, ensure_ascii=False, indent=2, sort_keys=True)

            # 先确认字节确实不同（否则测试无意义）
            with (run_dir / "facet-abc123.json").open("rb") as f:
                src_bytes = f.read()
            with tgt_path.open("rb") as f:
                tgt_bytes = f.read()
            # 如果字节恰好相同（极少见），也不影响结论（仍应 skipped）
            # 但我们希望此测试验证"字节 != 语义"；若相同则加一个无序 key 的 nested dict
            if src_bytes == tgt_bytes:
                # 强制注入顺序差异：重写源，使 tools_used 键顺序与目标不同
                reordered = dict(src_obj)
                reordered["tools_used"] = {
                    k: src_obj["tools_used"][k]
                    for k in reversed(list(src_obj["tools_used"].keys()))
                }
                with (run_dir / "facet-abc123.json").open(
                    "w", encoding="utf-8"
                ) as f:
                    json.dump(reordered, f, ensure_ascii=False, indent=2)

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = publish_facet.run(
                    str(run_dir), "2026-04-15", str(blog_root)
                )
            self.assertEqual(rc, 0)
            self.assertIn("wrote=0 skipped=1 failed=0", buf.getvalue())


class TestCanonicalEquivalence(unittest.TestCase):
    """v1.2：friction_types / anchors.files 顺序抖动不应触发 wrote。"""

    def test_friction_types_order_is_skipped(self):
        """friction_types 顺序不同、内容相同 → canonical 等价 → skipped。"""
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            blog_root = Path(td) / "blog"
            run_dir.mkdir()
            out_dir = blog_root / "2026" / "04" / "15"
            out_dir.mkdir(parents=True)

            # 目标已有：friction_types 顺序 A
            existing = _sample_facet("abc123")
            existing["friction_types"] = ["user_interruption", "tool_error"]
            tgt_path = out_dir / "abc123.json"
            with tgt_path.open("w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

            # 源：其他一致，friction_types 顺序 B
            src = _sample_facet("abc123")
            src["friction_types"] = ["tool_error", "user_interruption"]
            _write_facet(run_dir, "abc123", src)

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = publish_facet.run(str(run_dir), "2026-04-15", str(blog_root))
            self.assertEqual(rc, 0)
            self.assertIn("wrote=0 skipped=1 failed=0", buf.getvalue())

    def test_anchors_files_order_is_skipped(self):
        """anchors.files 顺序不同、内容相同 → canonical 等价 → skipped。"""
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            blog_root = Path(td) / "blog"
            run_dir.mkdir()
            out_dir = blog_root / "2026" / "04" / "15"
            out_dir.mkdir(parents=True)

            existing = _sample_facet("abc123")
            existing["anchors"]["files"] = ["a.py", "b.py", "c.py"]
            tgt_path = out_dir / "abc123.json"
            with tgt_path.open("w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

            src = _sample_facet("abc123")
            src["anchors"]["files"] = ["c.py", "a.py", "b.py"]
            _write_facet(run_dir, "abc123", src)

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = publish_facet.run(str(run_dir), "2026-04-15", str(blog_root))
            self.assertEqual(rc, 0)
            self.assertIn("wrote=0 skipped=1 failed=0", buf.getvalue())

    def test_friction_types_real_diff_still_writes(self):
        """friction_types 内容真的不同（非顺序） → 仍应 wrote。"""
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            blog_root = Path(td) / "blog"
            run_dir.mkdir()
            out_dir = blog_root / "2026" / "04" / "15"
            out_dir.mkdir(parents=True)

            existing = _sample_facet("abc123")
            existing["friction_types"] = ["user_interruption"]
            tgt_path = out_dir / "abc123.json"
            with tgt_path.open("w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

            src = _sample_facet("abc123")
            src["friction_types"] = ["tool_error"]
            _write_facet(run_dir, "abc123", src)

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = publish_facet.run(str(run_dir), "2026-04-15", str(blog_root))
            self.assertEqual(rc, 0)
            self.assertIn("wrote=1 skipped=0 failed=0", buf.getvalue())

            # 确认目标已被覆写为源内容
            with tgt_path.open("r", encoding="utf-8") as f:
                self.assertEqual(json.load(f)["friction_types"], ["tool_error"])

    def test_disk_content_not_sorted_on_write(self):
        """canonical 只用于比较，不改磁盘：首次 wrote 时目标应保留源原顺序，
        而非 sorted 版本。"""
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            blog_root = Path(td) / "blog"
            run_dir.mkdir()

            # 源 friction_types 和 anchors.files 都是非 sorted 原顺序
            src = _sample_facet("abc123")
            src["friction_types"] = ["tool_error", "context_loss"]  # 非字典序
            src["anchors"]["files"] = ["b.py", "a.py"]  # 非字典序
            _write_facet(run_dir, "abc123", src)

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = publish_facet.run(str(run_dir), "2026-04-15", str(blog_root))
            self.assertEqual(rc, 0)
            self.assertIn("wrote=1 skipped=0 failed=0", buf.getvalue())

            # 目标磁盘内容应与源原顺序一致，不应被 canonicalize 改写
            tgt_path = blog_root / "2026" / "04" / "15" / "abc123.json"
            with tgt_path.open("r", encoding="utf-8") as f:
                written = json.load(f)
            self.assertEqual(
                written["friction_types"], ["tool_error", "context_loss"]
            )
            self.assertEqual(written["anchors"]["files"], ["b.py", "a.py"])


class TestMkdirP(unittest.TestCase):
    def test_nested_date_dir_created(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            blog_root = Path(td) / "blog"  # 整个 blog 根都不预先建
            run_dir.mkdir()
            _write_facet(run_dir, "abc123", _sample_facet("abc123"))

            self.assertFalse(blog_root.exists())
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = publish_facet.run(
                    str(run_dir), "2026-04-15", str(blog_root)
                )
            self.assertEqual(rc, 0)
            self.assertTrue((blog_root / "2026" / "04" / "15").is_dir())
            self.assertTrue(
                (blog_root / "2026" / "04" / "15" / "abc123.json").is_file()
            )


class TestTargetDateInvalid(unittest.TestCase):
    def test_loose_format_exit_2(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            blog_root = Path(td) / "blog"
            run_dir.mkdir()
            _write_facet(run_dir, "abc123", _sample_facet("abc123"))

            buf_err = io.StringIO()
            with redirect_stderr(buf_err):
                rc = publish_facet.run(str(run_dir), "2026-4-15", str(blog_root))
            self.assertEqual(rc, 2)
            self.assertIn("TARGET_DATE", buf_err.getvalue())
            # 未进入搬运流程，blog 根不应被建出日期目录
            self.assertFalse((blog_root / "2026").exists())


class TestEmptyRunDir(unittest.TestCase):
    def test_empty_exit_0_all_zero(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            blog_root = Path(td) / "blog"
            run_dir.mkdir()

            buf_out = io.StringIO()
            with redirect_stdout(buf_out):
                rc = publish_facet.run(
                    str(run_dir), "2026-04-15", str(blog_root)
                )
            self.assertEqual(rc, 0)
            self.assertIn("wrote=0 skipped=0 failed=0", buf_out.getvalue())


class TestBadJsonIsolated(unittest.TestCase):
    def test_broken_facet_failed_but_others_still_move(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            blog_root = Path(td) / "blog"
            run_dir.mkdir()

            # 一好一坏
            _write_facet(run_dir, "good", _sample_facet("good"))
            bad_path = run_dir / "facet-broken.json"
            with bad_path.open("w", encoding="utf-8") as f:
                f.write("{not: valid json,,,")

            buf_out = io.StringIO()
            buf_err = io.StringIO()
            with redirect_stdout(buf_out), redirect_stderr(buf_err):
                rc = publish_facet.run(
                    str(run_dir), "2026-04-15", str(blog_root)
                )
            self.assertEqual(rc, 0)
            self.assertIn("wrote=1 skipped=0 failed=1", buf_out.getvalue())
            self.assertIn("broken", buf_err.getvalue())

            # 好的文件确实搬过去
            out = blog_root / "2026" / "04" / "15" / "good.json"
            self.assertTrue(out.is_file())
            # 坏的文件不应在目标出现
            self.assertFalse(
                (blog_root / "2026" / "04" / "15" / "broken.json").is_file()
            )


class TestMainEntryEnvVars(unittest.TestCase):
    """测 main()：env 缺失 → exit 2。"""

    def test_missing_run_dir(self):
        old_env = dict(os.environ)
        try:
            os.environ.pop("RUN_DIR", None)
            os.environ["TARGET_DATE"] = "2026-04-15"
            buf_err = io.StringIO()
            with redirect_stderr(buf_err):
                rc = publish_facet.main()
            self.assertEqual(rc, 2)
            self.assertIn("RUN_DIR", buf_err.getvalue())
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def test_missing_target_date(self):
        old_env = dict(os.environ)
        try:
            os.environ["RUN_DIR"] = "/tmp/nowhere"
            os.environ.pop("TARGET_DATE", None)
            buf_err = io.StringIO()
            with redirect_stderr(buf_err):
                rc = publish_facet.main()
            self.assertEqual(rc, 2)
            self.assertIn("TARGET_DATE", buf_err.getvalue())
        finally:
            os.environ.clear()
            os.environ.update(old_env)


class TestPermissionDenied(unittest.TestCase):
    """目标根目录权限不足 → exit 1。"""

    def test_readonly_blog_root_parent(self):
        if os.geteuid() == 0:
            self.skipTest("root bypass permission checks")
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            _write_facet(run_dir, "abc123", _sample_facet("abc123"))

            # 建一个只读父目录，blog_root 指向其下不存在的子路径
            ro_parent = Path(td) / "ro"
            ro_parent.mkdir()
            blog_root = ro_parent / "blog"
            # 去掉写权限
            os.chmod(ro_parent, stat.S_IRUSR | stat.S_IXUSR)
            try:
                buf_err = io.StringIO()
                buf_out = io.StringIO()
                with redirect_stdout(buf_out), redirect_stderr(buf_err):
                    rc = publish_facet.run(
                        str(run_dir), "2026-04-15", str(blog_root)
                    )
                self.assertEqual(rc, 1)
                self.assertIn("BLOG_FACETS_ROOT", buf_err.getvalue())
            finally:
                # 还原权限，让 TemporaryDirectory cleanup 能删
                os.chmod(
                    ro_parent,
                    stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR,
                )


if __name__ == "__main__":
    unittest.main()
