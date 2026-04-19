# -*- coding: utf-8 -*-
"""Tests for scripts/review/insert-tldr.py validators and insertion."""
from __future__ import annotations

import importlib.util
from pathlib import Path


SPEC_PATH = Path(__file__).resolve().parents[1] / "review" / "insert-tldr.py"
_spec = importlib.util.spec_from_file_location("insert_tldr", SPEC_PATH)
insert_tldr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(insert_tldr)


GOOD = (
    "今天主线只有一件事：把 daily-report skill 自己改顺。"
    "一是给反方 prompt 注入机械 work-map 先验，把我写了多少和我重心在哪切开；"
    "二是合掉 facet 层改造，跑通精简和 publish。两处改动共享单窗口验证，需另找日期复核。\n\n"
    "顺手清了几条基础设施债：补跑 4-16 日报，把中间产物挪进私有仓并修了跨平台兼容问题。"
    "明天的事：给每个可落盘 step 加 checkpoint，对外 artifact 按 public private ephemeral 三档打标再发布。"
)


def test_good_passes() -> None:
    errors = insert_tldr.validate(GOOD)
    assert errors == [], errors


def test_length_too_long() -> None:
    text = "今" * 401
    errors = insert_tldr.validate(text)
    assert any("length" in e for e in errors), errors


def test_length_too_short() -> None:
    text = "今天只干了一点点事。"
    errors = insert_tldr.validate(text)
    assert any("below floor" in e for e in errors), errors


def test_verbal_tic_miao() -> None:
    text = GOOD + "喵"
    errors = insert_tldr.validate(text)
    assert any("喵" in e for e in errors), errors


def test_session_id_rejected() -> None:
    text = GOOD + " 参见 #90e08029 的工作。"
    errors = insert_tldr.validate(text)
    assert any("session id" in e for e in errors), errors


def test_file_path_rejected() -> None:
    text = GOOD + " 改了 send-telegram-opposing.sh 的解析。"
    errors = insert_tldr.validate(text)
    assert any("file names" in e for e in errors), errors


def test_absolute_path_rejected() -> None:
    text = GOOD + " 产物落在 /tmp/dr-2026-04-17/output 目录。"
    errors = insert_tldr.validate(text)
    assert any("absolute paths" in e for e in errors), errors


def test_bullet_rejected() -> None:
    text = "今天做了以下事情，下面列一下主线和副线结构，覆盖当天主要工作：\n- 第一件\n- 第二件\n两件都属于基础设施债务清理，时间都花在这上面了。"
    errors = insert_tldr.validate(text)
    assert any("bullet" in e for e in errors), errors


def test_table_rejected() -> None:
    text = "今天主线只有一件事：改 skill。下面表格呈现当天各部分的工作耗时分布与具体结果，用来对照后续的优化方向。\n| A | B |\n| - | - |\n| 1 | 2 |"
    errors = insert_tldr.validate(text)
    assert any("tables" in e for e in errors), errors


def test_meta_self_reference_rejected() -> None:
    text = GOOD + " 这份 TL;DR 总结了今天的全部要点。"
    errors = insert_tldr.validate(text)
    assert any("self-referential" in e for e in errors), errors


def test_heading_rejected() -> None:
    text = "今天主线只有一件事：改 skill。下面分几个小节回顾当天的主线与副线安排，方便半年后快速复盘各模块进度情况。\n## 小节\n另一些内容写在这里。"
    errors = insert_tldr.validate(text)
    assert any("heading" in e for e in errors), errors


def test_insert_after_frontmatter() -> None:
    md = '---\ntitle: "日报"\n---\n\n## 概览\n\n正文。\n'
    out = insert_tldr.insert(md, GOOD)
    assert out.startswith('---\ntitle: "日报"\n---\n'), out[:60]
    assert "## TL;DR" in out
    assert out.index("## TL;DR") < out.index("## 概览")


def test_insert_preserves_body() -> None:
    md = '---\ntitle: "X"\n---\n\n## A\n\nbody text\n'
    out = insert_tldr.insert(md, GOOD)
    assert "body text" in out
    assert out.count("## A") == 1


def test_insert_without_frontmatter_errors() -> None:
    md = "## 概览\n\n正文。\n"
    try:
        insert_tldr.insert(md, GOOD)
    except ValueError as e:
        assert "frontmatter" in str(e)
    else:
        raise AssertionError("expected ValueError for missing frontmatter")
