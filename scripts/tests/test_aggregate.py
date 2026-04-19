# -*- coding: utf-8 -*-
"""test_aggregate.py —— 覆盖 aggregate-facet.py 的主要生成规则与阈值触发。

模块名带连字符，用 importlib.util 从绝对路径加载。
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "session" / "aggregate-facet.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("aggregate_facet", str(SCRIPT_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


aggregate_facet = _load_module()


def make_facet(
    sid: str,
    goal: str = "其他",
    satisfaction: str = "unsure",
    friction_types: Optional[List[str]] = None,
    tools_used: Optional[Dict[str, int]] = None,
    languages: Optional[List[str]] = None,
    turn_count: int = 10,
    duration_minutes: int = 30,
    user_message_count: int = 5,
) -> Dict[str, Any]:
    """构造一份符合 Schema 2 的完整 facet dict（机械字段 + 判断字段全部齐全）。"""
    return {
        # ---- 机械字段（Schema 1 继承）----
        "session_id": sid,
        "target_date": "2026-04-15",
        "window_start_iso": "2026-04-14T16:00:00Z",
        "window_end_iso": "2026-04-15T16:00:00Z",
        "start_ts": "2026-04-15T01:00:00Z",
        "end_ts": "2026-04-15T02:00:00Z",
        "duration_minutes": duration_minutes,
        "user_message_count": user_message_count,
        "turn_count": turn_count,
        "tools_used": tools_used if tools_used is not None else {},
        "languages": languages if languages is not None else [],
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
        # ---- 判断字段 ----
        "goal": goal,
        "goal_detail": "stub",
        "satisfaction": satisfaction,
        "friction_types": friction_types if friction_types is not None else [],
        "anchors": {
            "repo": None,
            "branch_or_pr": None,
            "issue_or_bug": None,
            "target_object": None,
            "files": [],
        },
        "first_prompt_summary": "stub",
        "summary": "stub",
        "status": "已交付",
    }


def write_facets(run_dir: str, facets: List[Dict[str, Any]]) -> None:
    for f in facets:
        sid = f["session_id"]
        path = os.path.join(run_dir, "facet-{}.json".format(sid))
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(f, fp, ensure_ascii=False, indent=2)


class TestAggregateRender(unittest.TestCase):
    """直接测 render() 纯函数：最稳、最快。"""

    def test_happy_path_five_sessions(self):
        """5 个 facet：工作类型分布 修Bug 3 / 新功能 2；满意度 satisfied 4 / likely_satisfied 1；
        工具 Read=20 · Bash=10；语言 ['python', 'bash']。"""
        facets = [
            make_facet("s1", goal="修Bug", satisfaction="satisfied",
                       tools_used={"Read": 5, "Bash": 3}, languages=["python"],
                       turn_count=10, duration_minutes=20),
            make_facet("s2", goal="修Bug", satisfaction="satisfied",
                       tools_used={"Read": 5, "Bash": 2}, languages=["python"],
                       turn_count=15, duration_minutes=30),
            make_facet("s3", goal="修Bug", satisfaction="satisfied",
                       tools_used={"Read": 4, "Bash": 3}, languages=["bash"],
                       turn_count=8, duration_minutes=10),
            make_facet("s4", goal="新功能", satisfaction="satisfied",
                       tools_used={"Read": 3, "Bash": 1}, languages=["python"],
                       turn_count=20, duration_minutes=60),
            make_facet("s5", goal="新功能", satisfaction="likely_satisfied",
                       tools_used={"Read": 3, "Bash": 1}, languages=["bash"],
                       turn_count=12, duration_minutes=40),
        ]
        out = aggregate_facet.render(facets)
        self.assertTrue(out.startswith("## Session 指标"))
        # 工作类型：修Bug 3 · 新功能 2
        self.assertIn("| 工作类型 | 修Bug 3 · 新功能 2 |", out)
        # 满意度
        self.assertIn("| 满意度 | satisfied 4 · likely_satisfied 1 |", out)
        # 摩擦点行应当被省略（全空）
        self.assertNotIn("| 摩擦点 |", out)
        # Top 工具：Read=20, Bash=10
        self.assertIn("| Top 工具 | Read 20 · Bash 10 |", out)
        # 语言：bash · python（字母序）
        self.assertIn("| 语言 | bash · python |", out)
        # 合计：5 session / 65 轮 / avg = round((20+30+10+60+40)/5) = round(32) = 32
        self.assertIn("| 合计 | 5 session / 65 轮 / 平均 32 分钟 |", out)

    def test_friction_empty_row_omitted(self):
        facets = [
            make_facet("s1", goal="修Bug"),
            make_facet("s2", goal="修Bug"),
        ]
        out = aggregate_facet.render(facets)
        self.assertNotIn("| 摩擦点 |", out)

    def test_friction_nonempty_sorted(self):
        facets = [
            make_facet("s1", friction_types=["tool_error"]),
            make_facet("s2", friction_types=["misunderstood_request", "tool_error"]),
            make_facet("s3", friction_types=["misunderstood_request"]),
        ]
        out = aggregate_facet.render(facets)
        self.assertIn("| 摩擦点 | misunderstood_request 2 · tool_error 2 |", out)

    def test_zero_sessions_empty_output(self):
        self.assertEqual(aggregate_facet.render([]), "")

    def test_one_session_only_totals(self):
        facets = [
            make_facet("s1", goal="修Bug", satisfaction="satisfied",
                       friction_types=["tool_error"],
                       tools_used={"Read": 5}, languages=["python"],
                       turn_count=10, duration_minutes=25),
        ]
        out = aggregate_facet.render(facets)
        self.assertIn("## Session 指标", out)
        # 除合计行外，其他维度行均省略
        self.assertNotIn("| 工作类型 |", out)
        self.assertNotIn("| 满意度 |", out)
        self.assertNotIn("| 摩擦点 |", out)
        self.assertNotIn("| Top 工具 |", out)
        self.assertNotIn("| 语言 |", out)
        self.assertIn("| 合计 | 1 session / 10 轮 / 平均 25 分钟 |", out)

    def test_top_tools_cap_at_five(self):
        """6 种工具，只显示前 5。"""
        facets = [
            make_facet("s1", tools_used={
                "Read": 60, "Bash": 50, "Edit": 40, "Write": 30, "Grep": 20, "Glob": 10,
            }),
            make_facet("s2", tools_used={}),
        ]
        out = aggregate_facet.render(facets)
        self.assertIn("| Top 工具 | Read 60 · Bash 50 · Edit 40 · Write 30 · Grep 20 |", out)
        # Glob 应被截断掉
        # 断言方式：Top 工具 那一行里不含 Glob
        for line in out.splitlines():
            if line.startswith("| Top 工具 |"):
                self.assertNotIn("Glob", line)
                break
        else:
            self.fail("Top 工具 line missing")

    def test_duration_zero_excluded_from_avg(self):
        """duration_minutes=0 的 session 不计入平均；轮数与 session 数仍包含它。"""
        facets = [
            make_facet("s1", duration_minutes=30, turn_count=10),
            make_facet("s2", duration_minutes=60, turn_count=20),
            make_facet("s3", duration_minutes=0, turn_count=5),  # 被排除
        ]
        out = aggregate_facet.render(facets)
        # avg = round((30+60)/2) = 45，不是 round((30+60+0)/3)=30
        self.assertIn("| 合计 | 3 session / 35 轮 / 平均 45 分钟 |", out)

    def test_all_duration_zero_avg_is_zero(self):
        """边界：全部 session duration=0 → 平均分钟写 0，不崩。"""
        facets = [
            make_facet("s1", duration_minutes=0, turn_count=10),
            make_facet("s2", duration_minutes=0, turn_count=5),
        ]
        out = aggregate_facet.render(facets)
        self.assertIn("| 合计 | 2 session / 15 轮 / 平均 0 分钟 |", out)

    def test_goal_desc_sort_zero_omitted(self):
        """工作类型计数降序，零值档（调研）不出现在行里。"""
        facets = [
            make_facet("s1", goal="修Bug"),
            make_facet("s2", goal="修Bug"),
            make_facet("s3", goal="修Bug"),
            make_facet("s4", goal="新功能"),
            make_facet("s5", goal="新功能"),
            make_facet("s6", goal="治理"),
        ]
        out = aggregate_facet.render(facets)
        self.assertIn("| 工作类型 | 修Bug 3 · 新功能 2 · 治理 1 |", out)
        # 未出现的档位（调研 / 工具 / 其他）不入行
        for line in out.splitlines():
            if line.startswith("| 工作类型 |"):
                self.assertNotIn("调研", line)
                self.assertNotIn("工具", line)
                self.assertNotIn("其他", line)
                break
        else:
            self.fail("工作类型 line missing")

    def test_languages_dedup_sorted(self):
        """语言去重 + 字母序。输入 ['python','bash','python','markdown'] → 'bash · markdown · python'。"""
        facets = [
            make_facet("s1", languages=["python", "bash"]),
            make_facet("s2", languages=["python", "markdown"]),
        ]
        out = aggregate_facet.render(facets)
        self.assertIn("| 语言 | bash · markdown · python |", out)

    def test_optional_insights_fields_render_when_present(self):
        """insights-compatible 可选字段存在时追加聚合行；旧 facet 缺字段时不影响。"""
        f1 = make_facet("s1")
        f1.update({
            "goal_categories": {"fix_bug": 1},
            "outcome": "fully_achieved",
            "session_type": "single_task",
            "primary_success": "correct_code_edits",
            "friction_counts": {"tool_failed": 1},
        })
        f2 = make_facet("s2")
        f2.update({
            "goal_categories": {"write_tests": 1},
            "outcome": "mostly_achieved",
            "session_type": "iterative_refinement",
            "primary_success": "good_debugging",
            "friction_counts": {"buggy_code": 1},
        })
        out = aggregate_facet.render([f1, f2])
        self.assertIn("| Outcome | fully_achieved 1 · mostly_achieved 1 |", out)
        self.assertIn("| Session 类型 | iterative_refinement 1 · single_task 1 |", out)
        self.assertIn("| 主要成功 | correct_code_edits 1 · good_debugging 1 |", out)
        self.assertIn("| 细分目标 | fix_bug 1 · write_tests 1 |", out)
        self.assertIn("| 细分摩擦 | buggy_code 1 · tool_failed 1 |", out)


class TestAggregateEndToEnd(unittest.TestCase):
    """通过 RUN_DIR + subprocess 验证脚本主入口。"""

    def test_subprocess_happy_path(self):
        with tempfile.TemporaryDirectory() as run_dir:
            facets = [
                make_facet("s1", goal="修Bug", satisfaction="satisfied",
                           tools_used={"Read": 5, "Bash": 3}, languages=["python"],
                           turn_count=10, duration_minutes=20),
                make_facet("s2", goal="新功能", satisfaction="satisfied",
                           tools_used={"Read": 3, "Bash": 2}, languages=["bash"],
                           turn_count=15, duration_minutes=30),
            ]
            write_facets(run_dir, facets)
            env = os.environ.copy()
            env["RUN_DIR"] = run_dir
            r = subprocess.run(
                [sys.executable, str(SCRIPT_PATH)],
                env=env, capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, msg=r.stderr)
            self.assertTrue(r.stdout.startswith("## Session 指标"))
            self.assertIn("| 合计 | 2 session / 25 轮 / 平均 25 分钟 |", r.stdout)

    def test_subprocess_zero_sessions_empty_stdout(self):
        with tempfile.TemporaryDirectory() as run_dir:
            env = os.environ.copy()
            env["RUN_DIR"] = run_dir
            r = subprocess.run(
                [sys.executable, str(SCRIPT_PATH)],
                env=env, capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, msg=r.stderr)
            self.assertEqual(r.stdout, "")

    def test_subprocess_missing_run_dir_env(self):
        env = os.environ.copy()
        env.pop("RUN_DIR", None)
        r = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            env=env, capture_output=True, text=True,
        )
        self.assertNotEqual(r.returncode, 0)

    def test_subprocess_malformed_json_skipped(self):
        """单文件 parse 失败应 warning + 继续，不 exit 非 0。"""
        with tempfile.TemporaryDirectory() as run_dir:
            facets = [
                make_facet("s1", goal="修Bug", turn_count=10, duration_minutes=20),
                make_facet("s2", goal="修Bug", turn_count=5, duration_minutes=10),
            ]
            write_facets(run_dir, facets)
            # 再塞一个损坏的 facet-*.json
            with open(os.path.join(run_dir, "facet-broken.json"), "w", encoding="utf-8") as f:
                f.write("{ not valid json")
            env = os.environ.copy()
            env["RUN_DIR"] = run_dir
            r = subprocess.run(
                [sys.executable, str(SCRIPT_PATH)],
                env=env, capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, msg=r.stderr)
            # 损坏那个跳过，剩 2 个走正常分支
            self.assertIn("| 合计 | 2 session / 15 轮 / 平均 15 分钟 |", r.stdout)
            self.assertIn("skip", r.stderr)


if __name__ == "__main__":
    unittest.main()
