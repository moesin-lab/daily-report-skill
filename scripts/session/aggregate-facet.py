#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aggregate-facet.py —— 聚合 $RUN_DIR/facet-*.json，输出 Session 指标 Markdown 片段。

输入：环境变量 RUN_DIR（必需）
输出：stdout Markdown 片段（以 `## Session 指标` 开头），或空（facet 数 == 0）

生成规则 / 阈值触发 / 字段顺序严格遵循 dr-refactor-contracts.md Schema 5。
"""

from __future__ import annotations

import glob
import json
import os
import sys
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ---- 字段读取（容错：缺字段/类型错均按"无贡献"处理，不抛异常）----


def _load_facets(run_dir: str) -> List[Dict[str, Any]]:
    """读 $RUN_DIR/facet-*.json 全量返回 dict list。parse 失败单个跳过，stderr warning。"""
    pattern = os.path.join(run_dir, "facet-*.json")
    paths = sorted(glob.glob(pattern))
    out: List[Dict[str, Any]] = []
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            sys.stderr.write("[aggregate-facet] skip {}: {}\n".format(p, e))
            continue
        if isinstance(data, dict):
            out.append(data)
        else:
            sys.stderr.write("[aggregate-facet] skip {}: not a JSON object\n".format(p))
    return out


def _count_goals(facets: Iterable[Dict[str, Any]]) -> Counter:
    c: Counter = Counter()
    for f in facets:
        v = f.get("goal")
        if isinstance(v, str) and v:
            c[v] += 1
    return c


def _count_satisfaction(facets: Iterable[Dict[str, Any]]) -> Counter:
    c: Counter = Counter()
    for f in facets:
        v = f.get("satisfaction")
        if isinstance(v, str) and v:
            c[v] += 1
    return c


def _count_frictions(facets: Iterable[Dict[str, Any]]) -> Counter:
    c: Counter = Counter()
    for f in facets:
        v = f.get("friction_types")
        if isinstance(v, list):
            for item in v:
                if isinstance(item, str) and item:
                    c[item] += 1
    return c


def _count_dict_field(facets: Iterable[Dict[str, Any]], field: str) -> Counter:
    c: Counter = Counter()
    for f in facets:
        data = f.get(field)
        if not isinstance(data, dict):
            continue
        for key, n in data.items():
            if isinstance(key, str) and key and isinstance(n, int) and n > 0:
                c[key] += n
    return c


def _count_string_field(facets: Iterable[Dict[str, Any]], field: str) -> Counter:
    c: Counter = Counter()
    for f in facets:
        value = f.get(field)
        if isinstance(value, str) and value:
            c[value] += 1
    return c


def _count_tools(facets: Iterable[Dict[str, Any]]) -> Counter:
    c: Counter = Counter()
    for f in facets:
        tu = f.get("tools_used")
        if isinstance(tu, dict):
            for name, n in tu.items():
                if not isinstance(name, str) or not name:
                    continue
                if not isinstance(n, int):
                    continue
                c[name] += n
    return c


def _collect_languages(facets: Iterable[Dict[str, Any]]) -> List[str]:
    seen = set()
    for f in facets:
        langs = f.get("languages")
        if isinstance(langs, list):
            for lang in langs:
                if isinstance(lang, str) and lang:
                    seen.add(lang)
    return sorted(seen)


def _totals(facets: List[Dict[str, Any]]) -> Tuple[int, int, Optional[int]]:
    """返回 (session 数, 总轮数, 平均分钟 or None)。平均分钟仅算 duration_minutes > 0。"""
    session_count = len(facets)
    total_turns = 0
    durations: List[int] = []
    for f in facets:
        t = f.get("turn_count")
        if isinstance(t, int):
            total_turns += t
        d = f.get("duration_minutes")
        if isinstance(d, int) and d > 0:
            durations.append(d)
    avg_min: Optional[int] = None
    if durations:
        # round half to even 是 Python 默认，这里符合"四舍五入整数"通常预期
        avg_min = int(round(sum(durations) / len(durations)))
    return session_count, total_turns, avg_min


# ---- 渲染 ----


def _render_counter_line(c: Counter) -> Optional[str]:
    """按计数降序渲染 `key N · key N`；零值档与 0 计数在 Counter 中本就不存在；
    整行全零（空 Counter）返回 None 表示该行省略。计数相同时按 key 字典序（稳定、可测）。"""
    if not c:
        return None
    items = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
    return " · ".join("{} {}".format(k, v) for k, v in items)


def _render_tools_line(c: Counter, top_n: int = 5) -> Optional[str]:
    if not c:
        return None
    items = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]
    return " · ".join("{} {}".format(k, v) for k, v in items)


def _render_languages_line(langs: List[str]) -> Optional[str]:
    if not langs:
        return None
    return " · ".join(langs)


def _render_totals_line(session_count: int, total_turns: int, avg_min: Optional[int]) -> str:
    if avg_min is None:
        # 所有 session duration 均为 0：仍输出合计，但平均分钟写 0
        avg_str = "0"
    else:
        avg_str = str(avg_min)
    return "{} session / {} 轮 / 平均 {} 分钟".format(session_count, total_turns, avg_str)


def render(facets: List[Dict[str, Any]]) -> str:
    """按冻结文档 Schema 5 渲染完整片段；facet 数 == 0 返回空串。"""
    n = len(facets)
    if n == 0:
        return ""

    session_count, total_turns, avg_min = _totals(facets)
    totals_line = _render_totals_line(session_count, total_turns, avg_min)

    lines: List[str] = []
    lines.append("## Session 指标")
    lines.append("")
    lines.append("| 维度 | 分布 |")
    lines.append("|------|------|")

    if n < 2:
        # 样本不足：仅合计行
        lines.append("| 合计 | {} |".format(totals_line))
        return "\n".join(lines) + "\n"

    # 正常：全维度渲染，整行全零省略
    goal_line = _render_counter_line(_count_goals(facets))
    if goal_line is not None:
        lines.append("| 工作类型 | {} |".format(goal_line))

    sat_line = _render_counter_line(_count_satisfaction(facets))
    if sat_line is not None:
        lines.append("| 满意度 | {} |".format(sat_line))

    fric_line = _render_counter_line(_count_frictions(facets))
    if fric_line is not None:
        lines.append("| 摩擦点 | {} |".format(fric_line))

    outcome_line = _render_counter_line(_count_string_field(facets, "outcome"))
    if outcome_line is not None:
        lines.append("| Outcome | {} |".format(outcome_line))

    session_type_line = _render_counter_line(_count_string_field(facets, "session_type"))
    if session_type_line is not None:
        lines.append("| Session 类型 | {} |".format(session_type_line))

    success_line = _render_counter_line(_count_string_field(facets, "primary_success"))
    if success_line is not None:
        lines.append("| 主要成功 | {} |".format(success_line))

    detailed_goal_line = _render_counter_line(_count_dict_field(facets, "goal_categories"))
    if detailed_goal_line is not None:
        lines.append("| 细分目标 | {} |".format(detailed_goal_line))

    detailed_friction_line = _render_counter_line(_count_dict_field(facets, "friction_counts"))
    if detailed_friction_line is not None:
        lines.append("| 细分摩擦 | {} |".format(detailed_friction_line))

    tool_line = _render_tools_line(_count_tools(facets), top_n=5)
    if tool_line is not None:
        lines.append("| Top 工具 | {} |".format(tool_line))

    lang_line = _render_languages_line(_collect_languages(facets))
    if lang_line is not None:
        lines.append("| 语言 | {} |".format(lang_line))

    lines.append("| 合计 | {} |".format(totals_line))
    return "\n".join(lines) + "\n"


# ---- main ----


def main() -> int:
    run_dir = os.environ.get("RUN_DIR")
    if not run_dir:
        sys.stderr.write("[aggregate-facet] RUN_DIR env var required\n")
        return 2
    if not os.path.isdir(run_dir):
        sys.stderr.write("[aggregate-facet] RUN_DIR not a directory: {}\n".format(run_dir))
        return 2

    facets = _load_facets(run_dir)
    out = render(facets)
    if out:
        # 不多加换行：render 末尾已有 \n
        sys.stdout.write(out)
    # facet 数 0 → stdout 完全空（不写任何字符）
    return 0


if __name__ == "__main__":
    sys.exit(main())
