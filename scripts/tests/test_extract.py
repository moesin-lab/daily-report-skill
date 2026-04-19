# -*- coding: utf-8 -*-
"""test_extract.py — 单测 extract-metadata.py。

Python 3.8+ stdlib only；不用 pytest / 不连 LLM。

跑法：
    cd ~/.claude/skills/daily-report/scripts/
    python3 -m unittest tests.test_extract -v
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# 脚本名含连字符，不能直接 import；从文件路径加载模块
_THIS_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _THIS_DIR.parent
_EXTRACT_PATH = _SCRIPTS_DIR / "session" / "extract-metadata.py"

_spec = importlib.util.spec_from_file_location("extract_metadata", _EXTRACT_PATH)
assert _spec is not None and _spec.loader is not None, "failed to locate extract-metadata.py"
extract_metadata = importlib.util.module_from_spec(_spec)
sys.modules["extract_metadata"] = extract_metadata
_spec.loader.exec_module(extract_metadata)


# ---------- 公共工具 ----------

WINDOW_START = "2026-04-14T16:00:00Z"
WINDOW_END = "2026-04-15T16:00:00Z"
TARGET_DATE = "2026-04-15"


def _write_jsonl(lines, sid="test-session-0001"):
    """把 list[dict|str] 写入一个临时 .jsonl，返回绝对路径。

    dict 元素会被 json.dumps；str 元素按原样写（用来测坏行）。
    """
    tmp_dir = tempfile.mkdtemp(prefix="dr-extract-test-")
    path = os.path.join(tmp_dir, f"{sid}.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for ln in lines:
            if isinstance(ln, str):
                f.write(ln)
            else:
                f.write(json.dumps(ln, ensure_ascii=False))
            f.write("\n")
    return path


def _user_text(ts, text):
    return {
        "type": "user",
        "timestamp": ts,
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def _user_string_content(ts, text):
    return {
        "type": "user",
        "timestamp": ts,
        "message": {"role": "user", "content": text},
    }


def _user_tool_result(ts, is_error=False, result_text="ok"):
    return {
        "type": "user",
        "timestamp": ts,
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_x",
                    "content": result_text,
                    "is_error": is_error,
                }
            ],
        },
    }


def _assistant(ts, content=None, usage=None):
    msg = {"role": "assistant", "content": content or []}
    if usage is not None:
        msg["usage"] = usage
    return {"type": "assistant", "timestamp": ts, "message": msg}


def _tool_use(name, tool_input, tool_id="toolu_1"):
    return {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}


def _compute(jsonl_path):
    return extract_metadata.compute_metadata(
        session_file=jsonl_path,
        window_start_iso=WINDOW_START,
        window_end_iso=WINDOW_END,
        target_date=TARGET_DATE,
    )


# ---------- 测试类 ----------

class HappyPathTest(unittest.TestCase):
    """覆盖点 1：happy path — 多条混合消息，所有字段计算正确。"""

    def test_all_fields(self):
        lines = [
            _user_text("2026-04-15T01:00:00.000Z", "帮我改一下 foo.py"),
            _assistant(
                "2026-04-15T01:00:05.000Z",
                content=[
                    {"type": "text", "text": "好的"},
                    _tool_use("Read", {"file_path": "/repo/foo.py"}, tool_id="t1"),
                ],
                usage={
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 10,
                    "cache_read_input_tokens": 20,
                },
            ),
            _user_tool_result("2026-04-15T01:00:06.000Z", is_error=False),
            _assistant(
                "2026-04-15T01:05:00.000Z",
                content=[
                    _tool_use("Edit", {"file_path": "/repo/foo.py"}, tool_id="t2"),
                    _tool_use(
                        "Bash",
                        {"command": "git commit -m 'fix foo'"},
                        tool_id="t3",
                    ),
                ],
                usage={
                    "input_tokens": 200,
                    "output_tokens": 30,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 500,
                },
            ),
            _user_text("2026-04-15T01:10:00.000Z", "再看看 README.md"),
            _assistant(
                "2026-04-15T01:12:00.000Z",
                content=[_tool_use("Read", {"file_path": "/repo/README.md"})],
                usage={"input_tokens": 10, "output_tokens": 5},
            ),
        ]
        path = _write_jsonl(lines)
        m = _compute(path)

        self.assertEqual(m["session_id"], "test-session-0001")
        self.assertEqual(m["target_date"], TARGET_DATE)
        self.assertEqual(m["window_start_iso"], WINDOW_START)
        self.assertEqual(m["window_end_iso"], WINDOW_END)
        self.assertEqual(m["start_ts"], "2026-04-15T01:00:00.000Z")
        self.assertEqual(m["end_ts"], "2026-04-15T01:12:00.000Z")
        # 01:00:00 -> 01:12:00 = 12 分钟
        self.assertEqual(m["duration_minutes"], 12)
        # 2 条真实 user（tool_result 那条不算）
        self.assertEqual(m["user_message_count"], 2)
        self.assertEqual(m["turn_count"], 3)
        self.assertEqual(m["tools_used"], {"Read": 2, "Edit": 1, "Bash": 1})
        self.assertEqual(m["languages"], ["markdown", "python"])
        rs = m["raw_stats"]
        self.assertEqual(rs["input_tokens"], 310)
        self.assertEqual(rs["output_tokens"], 85)
        self.assertEqual(rs["cache_creation_input_tokens"], 10)
        self.assertEqual(rs["cache_read_input_tokens"], 520)
        self.assertEqual(rs["tool_errors"], 0)
        self.assertEqual(rs["user_interruptions"], 0)
        self.assertEqual(rs["git_commits"], 1)
        self.assertEqual(rs["git_pushes"], 0)
        self.assertEqual(m["schema_version"], 1)


class WindowBoundaryTest(unittest.TestCase):
    """覆盖点 2：窗口外消息被排除；半开区间 [start, end)。

    冻结文档 v1.1：`ts >= WINDOW_START_ISO`（含左端）且 `ts < WINDOW_END_ISO`
    （不含右端）。WINDOW_START 保留，WINDOW_END 剔除；WINDOW_END 前 1ms 保留。
    """

    def test_boundary_half_open_interval(self):
        end_minus_1ms = "2026-04-15T15:59:59.999Z"  # WINDOW_END 前 1ms — 保留
        lines = [
            # 窗口前
            _user_text("2026-04-14T15:59:59.999Z", "窗口外之前"),
            _assistant("2026-04-14T15:59:59.999Z", content=[], usage={"input_tokens": 999}),
            # 窗口起点（半开区间 — 保留）
            _user_text(WINDOW_START, "窗口起点边界"),
            _assistant(WINDOW_START, content=[_tool_use("Read", {"file_path": "/a.py"})]),
            # 窗口中
            _user_text("2026-04-15T08:00:00.000Z", "中间"),
            # 窗口终点前 1ms（半开区间 — 保留，应作为 end_ts）
            _assistant(end_minus_1ms, content=[], usage={"input_tokens": 7}),
            # 窗口终点（半开区间 — 剔除）
            _assistant(WINDOW_END, content=[], usage={"input_tokens": 123}),
            # 窗口后
            _user_text("2026-04-15T16:00:00.001Z", "窗口外之后"),
        ]
        path = _write_jsonl(lines)
        m = _compute(path)

        self.assertEqual(m["start_ts"], WINDOW_START)
        # 半开：end_ts 必须是终点前 1ms，WINDOW_END 本身被剔除
        self.assertEqual(m["end_ts"], end_minus_1ms)
        self.assertEqual(m["user_message_count"], 2)  # WINDOW_START + 中间
        # turn_count：WINDOW_START assistant + end-1ms assistant = 2；WINDOW_END assistant 剔除
        self.assertEqual(m["turn_count"], 2)
        self.assertEqual(m["tools_used"], {"Read": 1})
        # 窗口外 input_tokens=999 和 终点 input_tokens=123 都不该进，只剩 7
        self.assertEqual(m["raw_stats"]["input_tokens"], 7)
        # 24 小时 - 1ms，int 截断后仍是 1439 分钟（23h59min）
        self.assertEqual(m["duration_minutes"], 24 * 60 - 1)

    def test_window_end_exact_timestamp_excluded(self):
        """正向测试：消息 timestamp 恰等于 WINDOW_END_ISO → 该消息不入 metadata。"""
        lines = [
            _user_text(WINDOW_START, "起点保留"),
            _assistant(
                WINDOW_END,
                content=[_tool_use("Read", {"file_path": "/excluded.py"})],
                usage={"input_tokens": 500, "output_tokens": 400},
            ),
            _user_text(WINDOW_END, "终点 user 也应被剔除"),
        ]
        path = _write_jsonl(lines)
        m = _compute(path)

        # WINDOW_END 上的 assistant / user 均剔除
        self.assertEqual(m["user_message_count"], 1)  # 只有 WINDOW_START 那条
        self.assertEqual(m["turn_count"], 0)          # WINDOW_END assistant 剔除
        self.assertEqual(m["tools_used"], {})         # 对应 tool_use 不计
        self.assertEqual(m["languages"], [])          # 对应 .py 不入列
        self.assertEqual(m["raw_stats"]["input_tokens"], 0)
        self.assertEqual(m["raw_stats"]["output_tokens"], 0)
        # start_ts == end_ts == WINDOW_START（窗口内只有 1 条消息）
        self.assertEqual(m["start_ts"], WINDOW_START)
        self.assertEqual(m["end_ts"], WINDOW_START)
        self.assertEqual(m["duration_minutes"], 0)


class ToolUseAccumulationTest(unittest.TestCase):
    """覆盖点 3：同名 tool 多次调用累加。"""

    def test_same_tool_multiple_calls(self):
        lines = [
            _assistant(
                "2026-04-15T01:00:00.000Z",
                content=[
                    _tool_use("Read", {"file_path": "/a.py"}, tool_id="1"),
                    _tool_use("Read", {"file_path": "/b.py"}, tool_id="2"),
                    _tool_use("Read", {"file_path": "/c.py"}, tool_id="3"),
                    _tool_use("Bash", {"command": "ls"}, tool_id="4"),
                ],
            ),
            _assistant(
                "2026-04-15T01:00:10.000Z",
                content=[
                    _tool_use("Read", {"file_path": "/d.py"}, tool_id="5"),
                    _tool_use("Bash", {"command": "pwd"}, tool_id="6"),
                ],
            ),
        ]
        path = _write_jsonl(lines)
        m = _compute(path)
        self.assertEqual(m["tools_used"], {"Read": 4, "Bash": 2})


class LanguageDerivationTest(unittest.TestCase):
    """覆盖点 4：.py → python；.tsx → typescript；.xyz 未知后缀不入列。"""

    def test_known_and_unknown_extensions(self):
        lines = [
            _assistant(
                "2026-04-15T01:00:00.000Z",
                content=[
                    _tool_use("Read", {"file_path": "/repo/a.py"}, tool_id="1"),
                    _tool_use("Read", {"file_path": "/repo/b.tsx"}, tool_id="2"),
                    _tool_use("Read", {"file_path": "/repo/c.xyz"}, tool_id="3"),
                    _tool_use("Read", {"path": "/repo/d.md"}, tool_id="4"),
                    _tool_use(
                        "Glob",
                        {"files": ["/repo/e.rs", "/repo/f.unknownext"]},
                        tool_id="5",
                    ),
                ],
            )
        ]
        path = _write_jsonl(lines)
        m = _compute(path)
        self.assertEqual(m["languages"], ["markdown", "python", "rust", "typescript"])

    def test_no_file_paths_yield_empty_languages(self):
        lines = [
            _assistant(
                "2026-04-15T01:00:00.000Z",
                content=[_tool_use("Bash", {"command": "ls"}, tool_id="1")],
            )
        ]
        path = _write_jsonl(lines)
        m = _compute(path)
        self.assertEqual(m["languages"], [])


class UserInterruptionTest(unittest.TestCase):
    """覆盖点 5：[Request interrupted by user] 子串 → user_interruptions=1。"""

    def test_interrupt_in_text_content(self):
        lines = [
            _user_text(
                "2026-04-15T01:00:00.000Z",
                "一些文本 [Request interrupted by user] 追加内容",
            )
        ]
        path = _write_jsonl(lines)
        m = _compute(path)
        self.assertEqual(m["raw_stats"]["user_interruptions"], 1)

    def test_interrupt_in_string_content(self):
        lines = [
            _user_string_content(
                "2026-04-15T01:00:00.000Z",
                "[Request interrupted by user]",
            )
        ]
        path = _write_jsonl(lines)
        m = _compute(path)
        self.assertEqual(m["raw_stats"]["user_interruptions"], 1)


class ToolErrorTest(unittest.TestCase):
    """覆盖点 6：is_error:true 的 tool_result 计入 tool_errors。"""

    def test_tool_errors_count(self):
        lines = [
            _user_tool_result("2026-04-15T01:00:00.000Z", is_error=True, result_text="boom"),
            _user_tool_result("2026-04-15T01:00:10.000Z", is_error=False),
            _user_tool_result("2026-04-15T01:00:20.000Z", is_error=True, result_text="err2"),
        ]
        path = _write_jsonl(lines)
        m = _compute(path)
        self.assertEqual(m["raw_stats"]["tool_errors"], 2)
        # tool_result 伪装的 user 不算真实 user
        self.assertEqual(m["user_message_count"], 0)


class GitRegexTest(unittest.TestCase):
    """覆盖点 7：git commit / push 正则；committed 字面不计。"""

    def test_git_commit_and_push_and_negative(self):
        lines = [
            _assistant(
                "2026-04-15T01:00:00.000Z",
                content=[
                    _tool_use("Bash", {"command": "git commit -m 'xxx'"}, tool_id="1"),
                    _tool_use("Bash", {"command": "GIT COMMIT -m foo"}, tool_id="2"),  # 大小写
                    _tool_use("Bash", {"command": "git committed"}, tool_id="3"),  # 负例
                    _tool_use("Bash", {"command": "git push origin main"}, tool_id="4"),
                    _tool_use("Bash", {"command": "echo 'git pushes nothing'"}, tool_id="5"),
                    _tool_use(
                        "Bash",
                        {"command": "git commit -m a && git push"},
                        tool_id="6",
                    ),
                ],
            )
        ]
        path = _write_jsonl(lines)
        m = _compute(path)
        # commit: #1 + #2 + #6 = 3；"committed" 不匹配 \bgit\s+commit\b（后缀 ed 属词内但 \b 在 t/e 之间不成立，见下注）
        # 实际：git\s+commit 后必须 \b，而 "committed" 末尾 t 和 e 都是词字符，所以 \bgit\s+commit\b 要求 commit 之后是非单词字符。
        # 所以 "git committed" 不匹配。
        self.assertEqual(m["raw_stats"]["git_commits"], 3)
        # push: #4 + #6 = 2；"pushes" 是 push+es 后接单词字符 → \bpush\b 不匹配
        self.assertEqual(m["raw_stats"]["git_pushes"], 2)


class EmptyWindowTest(unittest.TestCase):
    """覆盖点 8：窗口内无消息 → duration=0 / start_ts=null / end_ts=null / 零值。"""

    def test_all_outside_window(self):
        lines = [
            _user_text("2026-04-10T01:00:00.000Z", "太早"),
            _assistant("2026-04-20T01:00:00.000Z", content=[], usage={"input_tokens": 5}),
        ]
        path = _write_jsonl(lines)
        m = _compute(path)
        self.assertIsNone(m["start_ts"])
        self.assertIsNone(m["end_ts"])
        self.assertEqual(m["duration_minutes"], 0)
        self.assertEqual(m["user_message_count"], 0)
        self.assertEqual(m["turn_count"], 0)
        self.assertEqual(m["tools_used"], {})
        self.assertEqual(m["languages"], [])
        rs = m["raw_stats"]
        for k in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
            "tool_errors",
            "user_interruptions",
            "git_commits",
            "git_pushes",
        ):
            self.assertEqual(rs[k], 0, f"{k} should be 0")
        self.assertEqual(m["schema_version"], 1)


class CorruptLineTest(unittest.TestCase):
    """覆盖点 9：损坏 jsonl 行跳过，不崩溃。"""

    def test_broken_line_skipped(self):
        # 混入坏行 + 非字符串 timestamp + 空行
        lines = [
            _user_text("2026-04-15T01:00:00.000Z", "第一条"),
            "{not a valid json",  # 原样写入 → parse 失败
            "",  # 空行
            _assistant(
                "2026-04-15T01:01:00.000Z",
                content=[_tool_use("Read", {"file_path": "/x.py"}, tool_id="t1")],
                usage={"input_tokens": 1, "output_tokens": 1},
            ),
        ]
        path = _write_jsonl(lines)
        m = _compute(path)
        self.assertEqual(m["user_message_count"], 1)
        self.assertEqual(m["turn_count"], 1)
        self.assertEqual(m["tools_used"], {"Read": 1})


class UsageMissingTest(unittest.TestCase):
    """覆盖点 10：assistant 消息无 usage → token 字段 0。"""

    def test_no_usage_fields_zero(self):
        lines = [
            _assistant(
                "2026-04-15T01:00:00.000Z",
                content=[_tool_use("Read", {"file_path": "/a.py"}, tool_id="t1")],
                usage=None,
            ),
            _assistant(
                "2026-04-15T01:00:05.000Z",
                content=[],
                usage={"input_tokens": 3},  # 只给一个字段，其余应为 0
            ),
        ]
        path = _write_jsonl(lines)
        m = _compute(path)
        rs = m["raw_stats"]
        self.assertEqual(rs["input_tokens"], 3)
        self.assertEqual(rs["output_tokens"], 0)
        self.assertEqual(rs["cache_creation_input_tokens"], 0)
        self.assertEqual(rs["cache_read_input_tokens"], 0)


class WriteMetadataTest(unittest.TestCase):
    """端到端小验收：write_metadata 幂等覆盖写，落盘路径与 schema 一致。"""

    def test_write_and_overwrite(self):
        lines = [_user_text("2026-04-15T01:00:00.000Z", "hi")]
        path = _write_jsonl(lines, sid="sid-abc")
        m1 = _compute(path)

        with tempfile.TemporaryDirectory() as run_dir:
            out = extract_metadata.write_metadata(run_dir, m1)
            self.assertEqual(out, os.path.join(run_dir, "metadata-sid-abc.json"))
            with open(out, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["session_id"], "sid-abc")
            self.assertEqual(data["schema_version"], 1)

            # 再写一次必须覆盖（幂等）
            m2 = dict(m1)
            m2["user_message_count"] = 99
            extract_metadata.write_metadata(run_dir, m2)
            with open(out, "r", encoding="utf-8") as f:
                data2 = json.load(f)
            self.assertEqual(data2["user_message_count"], 99)


class UserTextDetectionTest(unittest.TestCase):
    """辅助：user 消息排除规则细节 —— 空 text / 只有 tool_result 不算。"""

    def test_empty_text_not_counted(self):
        lines = [
            {
                "type": "user",
                "timestamp": "2026-04-15T01:00:00.000Z",
                "message": {"role": "user", "content": [{"type": "text", "text": "   "}]},
            },
            {
                "type": "user",
                "timestamp": "2026-04-15T01:00:05.000Z",
                "message": {"role": "user", "content": []},
            },
        ]
        path = _write_jsonl(lines)
        m = _compute(path)
        self.assertEqual(m["user_message_count"], 0)


if __name__ == "__main__":
    unittest.main()
