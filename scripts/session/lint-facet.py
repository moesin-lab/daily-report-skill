#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lint-facet.py — 校验 $RUN_DIR/facet-*.json，追加 entry 到 lint-report.json。

严格按 Daily Report Refactor 冻结文档 v1.1 的 Schema 2 / Schema 4 执行：

- 判断字段齐全 + 类型 + taxonomy 枚举校验
- 机械字段一致性闸门：逐字段对比同目录 metadata-<sid>.json
- schema_version == 1
- runtime_warning 类型 str | null
- anchors 5 键 + files list
- 追加 entry 到 $RUN_DIR/lint-report.json（兼容 lint-phase1.py 旧 entry；旧 entry 原样保留不升级 schema）

零 LLM、stdlib only、失败不 exit（由主 skill 读 lint-report.json 决策）。

CLI:
    RUN_DIR=/tmp/dr-2026-04-15 python3 lint-facet.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
from typing import Any, Dict, List, Optional, Tuple


# ------------------------- Taxonomy（来自冻结文档） -------------------------

GOAL_VALUES = {"修Bug", "新功能", "治理", "调研", "工具", "其他"}

SATISFACTION_VALUES = {
    "frustrated",
    "dissatisfied",
    "likely_satisfied",
    "satisfied",
    "happy",
    "unsure",
}

FRICTION_VALUES = {
    "misunderstood_request",
    "wrong_approach",
    "buggy_code",
    "tool_error",
    "user_rejected_action",
    "user_interruption",
    "repeated_same_error",
    "external_dependency_blocked",
    "rate_limit",
    "context_loss",
    "destructive_action_attempted",
    "other",
}

STATUS_VALUES = {"已交付", "在分支", "调研中", "阻塞", "无需交付"}

INSIGHTS_GOAL_CATEGORY_VALUES = {
    "debug_investigate",
    "implement_feature",
    "fix_bug",
    "write_script_tool",
    "refactor_code",
    "configure_system",
    "create_pr_commit",
    "analyze_data",
    "understand_codebase",
    "write_tests",
    "write_docs",
    "deploy_infra",
    "warmup_minimal",
}

OUTCOME_VALUES = {
    "fully_achieved",
    "mostly_achieved",
    "partially_achieved",
    "not_achieved",
    "unclear_from_transcript",
}

CLAUDE_HELPFULNESS_VALUES = {
    "unhelpful",
    "slightly_helpful",
    "moderately_helpful",
    "very_helpful",
    "essential",
}

SESSION_TYPE_VALUES = {
    "single_task",
    "multi_task",
    "iterative_refinement",
    "exploration",
    "quick_question",
}

INSIGHTS_FRICTION_VALUES = {
    "misunderstood_request",
    "wrong_approach",
    "buggy_code",
    "user_rejected_action",
    "claude_got_blocked",
    "user_stopped_early",
    "wrong_file_or_location",
    "excessive_changes",
    "slow_or_verbose",
    "tool_failed",
    "user_unclear",
    "external_issue",
}

PRIMARY_SUCCESS_VALUES = {
    "none",
    "fast_accurate_search",
    "correct_code_edits",
    "good_explanations",
    "proactive_help",
    "multi_file_changes",
    "good_debugging",
}

ANCHORS_KEYS = ("repo", "branch_or_pr", "issue_or_bug", "target_object", "files")

# 机械字段：必须与 metadata-<sid>.json 一致的键集合（冻结文档 Schema 4）
MECHANICAL_KEYS = (
    "session_id",
    "target_date",
    "window_start_iso",
    "window_end_iso",
    "start_ts",
    "end_ts",
    "duration_minutes",
    "user_message_count",
    "turn_count",
    "tools_used",
    "languages",
    "raw_stats",
    "schema_version",
)

# 判断字段必填键（存在性检查；值的具体类型 / 枚举再由专门校验函数补）
VERDICT_REQUIRED_KEYS = (
    "goal",
    "goal_detail",
    "satisfaction",
    "friction_types",
    "summary",
    "first_prompt_summary",
    "status",
    "anchors",
    "runtime_warning",
)

SCHEMA_VERSION_EXPECTED = 1


# ------------------------- 校验函数（可单测 import） -------------------------

def _is_str(v: Any) -> bool:
    return isinstance(v, str)


def _check_required(facet: Dict[str, Any], errors: List[str]) -> None:
    """必填键存在性：判断字段 + 机械字段；不在则 "missing field: <k>"。"""
    for k in VERDICT_REQUIRED_KEYS:
        if k not in facet:
            errors.append(f"missing field: {k}")
    for k in MECHANICAL_KEYS:
        if k not in facet:
            errors.append(f"missing field: {k}")


def _check_verdict_types(facet: Dict[str, Any], errors: List[str]) -> None:
    """判断字段类型校验。字段缺失由 _check_required 管，这里只看已存在的键。"""
    if "goal" in facet and not _is_str(facet["goal"]):
        errors.append(f"goal type invalid: expected str, got {type(facet['goal']).__name__}")
    if "goal_detail" in facet and not _is_str(facet["goal_detail"]):
        errors.append(
            f"goal_detail type invalid: expected str, got {type(facet['goal_detail']).__name__}"
        )
    if "satisfaction" in facet and not _is_str(facet["satisfaction"]):
        errors.append(
            f"satisfaction type invalid: expected str, got {type(facet['satisfaction']).__name__}"
        )
    if "friction_types" in facet and not isinstance(facet["friction_types"], list):
        errors.append(
            f"friction_types type invalid: expected list, got {type(facet['friction_types']).__name__}"
        )
    if "summary" in facet and not _is_str(facet["summary"]):
        errors.append(f"summary type invalid: expected str, got {type(facet['summary']).__name__}")
    if "first_prompt_summary" in facet and not _is_str(facet["first_prompt_summary"]):
        errors.append(
            f"first_prompt_summary type invalid: expected str, got "
            f"{type(facet['first_prompt_summary']).__name__}"
        )
    if "status" in facet and not _is_str(facet["status"]):
        errors.append(f"status type invalid: expected str, got {type(facet['status']).__name__}")

    # runtime_warning: str | None
    if "runtime_warning" in facet:
        rw = facet["runtime_warning"]
        if rw is not None and not _is_str(rw):
            errors.append(
                f"runtime_warning type invalid: expected str or null, got {type(rw).__name__}"
            )


def _check_anchors(facet: Dict[str, Any], errors: List[str]) -> None:
    if "anchors" not in facet:
        return
    anchors = facet["anchors"]
    if not isinstance(anchors, dict):
        errors.append(f"anchors type invalid: expected dict, got {type(anchors).__name__}")
        return
    for k in ANCHORS_KEYS:
        if k not in anchors:
            errors.append(f"anchors missing key: {k}")
    # files 必须是 list，元素为 str；允许空
    if "files" in anchors:
        files = anchors["files"]
        if not isinstance(files, list):
            errors.append(f"anchors.files type invalid: expected list, got {type(files).__name__}")
        else:
            for idx, item in enumerate(files):
                if not _is_str(item):
                    errors.append(
                        f"anchors.files[{idx}] type invalid: expected str, got "
                        f"{type(item).__name__}"
                    )


def _check_taxonomy(facet: Dict[str, Any], errors: List[str]) -> None:
    """枚举值校验。仅对字符串/列表型字段检查；类型错误已由 _check_verdict_types 报。"""
    goal = facet.get("goal")
    if _is_str(goal) and goal not in GOAL_VALUES:
        errors.append(f"goal {goal!r} not in taxonomy")

    sat = facet.get("satisfaction")
    if _is_str(sat) and sat not in SATISFACTION_VALUES:
        errors.append(f"satisfaction {sat!r} not in taxonomy")

    st = facet.get("status")
    if _is_str(st) and st not in STATUS_VALUES:
        errors.append(f"status {st!r} not in taxonomy")

    ft = facet.get("friction_types")
    if isinstance(ft, list):
        for item in ft:
            if not _is_str(item):
                errors.append(
                    f"friction_types element type invalid: expected str, got "
                    f"{type(item).__name__}"
                )
                continue
            if item not in FRICTION_VALUES:
                errors.append(f"friction_types element {item!r} not in taxonomy")

    goal_categories = facet.get("goal_categories")
    if isinstance(goal_categories, dict):
        for key, value in goal_categories.items():
            if not _is_str(key) or key not in INSIGHTS_GOAL_CATEGORY_VALUES:
                errors.append(f"goal_categories key {key!r} not in taxonomy")
            if not isinstance(value, int) or value < 0:
                errors.append(f"goal_categories[{key!r}] count invalid: {value!r}")
    elif goal_categories is not None:
        errors.append(
            f"goal_categories type invalid: expected dict, got {type(goal_categories).__name__}"
        )

    for field, values in (
        ("outcome", OUTCOME_VALUES),
        ("claude_helpfulness", CLAUDE_HELPFULNESS_VALUES),
        ("session_type", SESSION_TYPE_VALUES),
        ("primary_success", PRIMARY_SUCCESS_VALUES),
    ):
        value = facet.get(field)
        if _is_str(value) and value not in values:
            errors.append(f"{field} {value!r} not in taxonomy")
        elif value is not None and not _is_str(value):
            errors.append(f"{field} type invalid: expected str, got {type(value).__name__}")

    friction_counts = facet.get("friction_counts")
    if isinstance(friction_counts, dict):
        for key, value in friction_counts.items():
            if not _is_str(key) or key not in INSIGHTS_FRICTION_VALUES:
                errors.append(f"friction_counts key {key!r} not in taxonomy")
            if not isinstance(value, int) or value < 0:
                errors.append(f"friction_counts[{key!r}] count invalid: {value!r}")
    elif friction_counts is not None:
        errors.append(
            f"friction_counts type invalid: expected dict, got {type(friction_counts).__name__}"
        )

    for field in ("friction_detail", "brief_summary"):
        value = facet.get(field)
        if value is not None and not _is_str(value):
            errors.append(f"{field} type invalid: expected str, got {type(value).__name__}")

    user_instructions = facet.get("user_instructions")
    if isinstance(user_instructions, list):
        for idx, item in enumerate(user_instructions):
            if not _is_str(item):
                errors.append(
                    f"user_instructions[{idx}] type invalid: expected str, got "
                    f"{type(item).__name__}"
                )
    elif user_instructions is not None:
        errors.append(
            f"user_instructions type invalid: expected list, got {type(user_instructions).__name__}"
        )


def _check_schema_version(facet: Dict[str, Any], errors: List[str]) -> None:
    if "schema_version" not in facet:
        return
    sv = facet["schema_version"]
    if sv != SCHEMA_VERSION_EXPECTED:
        errors.append(f"schema_version must be {SCHEMA_VERSION_EXPECTED}, got {sv!r}")


def _check_mechanical_consistency(
    facet: Dict[str, Any], metadata: Optional[Dict[str, Any]], errors: List[str]
) -> None:
    """机械字段逐字段 == 对比。metadata 为 None 时整体报 missing。"""
    if metadata is None:
        # 由调用方决定 missing 报错文本（含 sid），这里不重复
        return
    for k in MECHANICAL_KEYS:
        # 两边同时缺失算一致；有一边缺失而另一边存在，视作不一致
        if k in facet and k in metadata:
            if facet[k] != metadata[k]:
                errors.append(f"sub-agent mutated mechanical field: {k}")
        elif k in facet and k not in metadata:
            errors.append(f"sub-agent mutated mechanical field: {k}")
        elif k not in facet and k in metadata:
            # missing field 已由 _check_required 报，这里不重复
            pass


def lint_facet(
    facet: Dict[str, Any], metadata: Optional[Dict[str, Any]], sid: str
) -> List[str]:
    """对单个 facet dict 跑完整校验，返回 errors 列表（空即 pass）。"""
    errors: List[str] = []
    _check_required(facet, errors)
    _check_verdict_types(facet, errors)
    _check_anchors(facet, errors)
    _check_taxonomy(facet, errors)
    _check_schema_version(facet, errors)
    if metadata is None:
        errors.append(f"missing metadata-{sid}.json for consistency check")
    else:
        _check_mechanical_consistency(facet, metadata, errors)
    return errors


def _sid_from_facet_path(path: pathlib.Path) -> str:
    """facet-<sid>.json → <sid>"""
    stem = path.stem  # facet-<sid>
    prefix = "facet-"
    if stem.startswith(prefix):
        return stem[len(prefix):]
    return stem  # 理论上不会走到这里；glob 已保证 facet-* 前缀


def _load_json(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    """读 JSON 失败返回 None（由调用方报错）。"""
    try:
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _load_existing_report(path: pathlib.Path) -> List[Dict[str, Any]]:
    """读 $RUN_DIR/lint-report.json；不存在 / parse 失败 / 非数组 → []。

    冻结文档约定：单独跑时文件不存在初始化为 []；与 lint-phase1.py 追加共存。
    """
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, json.JSONDecodeError):
        # 损坏也视为空（保守，避免把异常外抛阻塞发布管线）
        return []
    if not isinstance(obj, list):
        return []
    return obj


def run(run_dir: pathlib.Path) -> Tuple[int, int]:
    """主流程：扫 facet-*.json → 校验 → 追加 lint-report.json。

    返回 (facet 总数, 失败数)。
    """
    facets = sorted(run_dir.glob("facet-*.json"))
    existing = _load_existing_report(run_dir / "lint-report.json")

    new_entries: List[Dict[str, Any]] = []
    failed = 0
    for fp in facets:
        sid = _sid_from_facet_path(fp)
        facet = _load_json(fp)
        if facet is None:
            # facet 本身不可解析：视作一条 error，入 report
            new_entries.append({
                "sid": sid,
                "target": "facet",
                "path": str(fp),
                "errors": [f"facet JSON parse failed: {fp.name}"],
            })
            failed += 1
            continue

        metadata_path = run_dir / f"metadata-{sid}.json"
        metadata = _load_json(metadata_path) if metadata_path.exists() else None

        errors = lint_facet(facet, metadata, sid)
        if errors:
            new_entries.append({
                "sid": sid,
                "target": "facet",
                "path": str(fp),
                "errors": errors,
            })
            failed += 1

    # 合并写回：旧 entry 原样保留（不升级 schema），新 entry 追加
    merged = list(existing) + new_entries
    out_path = run_dir / "lint-report.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
        f.write("\n")

    return len(facets), failed


def main() -> int:
    run_dir_env = os.environ.get("RUN_DIR")
    if not run_dir_env:
        sys.stderr.write("lint-facet: RUN_DIR env not set\n")
        return 2
    run_dir = pathlib.Path(run_dir_env)
    if not run_dir.is_dir():
        sys.stderr.write(f"lint-facet: RUN_DIR not a directory: {run_dir}\n")
        return 2

    total, failed = run(run_dir)
    print(f"[lint-facet] {total} facets, {failed} failed")
    # lint 失败不 exit 非 0；由主 skill 读 lint-report.json 决策是否重派
    return 0


if __name__ == "__main__":
    sys.exit(main())
