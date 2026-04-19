#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""publish-facet.py — 将 RUN_DIR 下的 facet-*.json 发布到 blog 的 facets 归档目录。

行为（冻结文档 Schema 6）：
- glob $RUN_DIR/facet-*.json
- 按 TARGET_DATE=YYYY-MM-DD 切出 Y/M/D 三段
- 目标路径 $BLOG_FACETS_ROOT/YYYY/MM/DD/<sid>.json
- 目标存在：语义等价比较（dict ==）→ 等价 skip、不等价覆盖写
- 目标不存在：直接写
- 单文件错误不阻塞其他文件
- 目标根目录权限不足时 exit 1；TARGET_DATE 格式非法 exit 2；空 RUN_DIR exit 0

硬约束：Python 3.8+ stdlib only，UTF-8 + ensure_ascii=False, indent=2，零 LLM。
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from pathlib import Path
from typing import Tuple


DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def parse_target_date(target_date: str) -> Tuple[str, str, str]:
    """把 YYYY-MM-DD 严格切成三段。格式非法抛 ValueError。"""
    if not isinstance(target_date, str):
        raise ValueError(f"TARGET_DATE must be str, got {type(target_date).__name__}")
    m = DATE_RE.match(target_date)
    if not m:
        raise ValueError(
            f"TARGET_DATE {target_date!r} not in strict YYYY-MM-DD format"
        )
    yyyy, mm, dd = m.group(1), m.group(2), m.group(3)
    # 进一步做值合法性校验（01<=mm<=12, 01<=dd<=31），避免 2026-13-40 通过
    month = int(mm)
    day = int(dd)
    if not (1 <= month <= 12):
        raise ValueError(f"TARGET_DATE {target_date!r} has invalid month")
    if not (1 <= day <= 31):
        raise ValueError(f"TARGET_DATE {target_date!r} has invalid day")
    return yyyy, mm, dd


def extract_sid(facet_path: Path) -> str:
    """从 facet-<sid>.json 抽出 sid。"""
    name = facet_path.name
    if not name.startswith("facet-") or not name.endswith(".json"):
        raise ValueError(f"unexpected facet filename: {name}")
    return name[len("facet-"):-len(".json")]


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _canonicalize(obj):
    """v1.2：对已知语义无序的 list 字段做排序副本，仅用于比较不改磁盘内容。

    语义无序字段：
      facet.friction_types  # top-level list
      facet.anchors.files   # nested list
    其他字段（含 facet.languages 虽为 sorted list 但作为机械字段不应被 LLM 动；
    anchors 其他子键都是 scalar）按原值比较。

    理由：LLM 两次生成 friction_types / anchors.files 顺序可能不稳；若 publish
    端严格按 `==` 会把语义等价判为不等，触发反复 wrote，破坏增量缓存价值。
    """
    if not isinstance(obj, dict):
        return obj
    out = dict(obj)  # 浅拷贝，不改原对象
    ft = out.get("friction_types")
    if isinstance(ft, list):
        out["friction_types"] = sorted(ft)
    anchors = out.get("anchors")
    if isinstance(anchors, dict):
        anchors_copy = dict(anchors)
        af = anchors_copy.get("files")
        if isinstance(af, list):
            anchors_copy["files"] = sorted(af)
        out["anchors"] = anchors_copy
    return out


def dump_json(obj, path: Path) -> None:
    """UTF-8 + ensure_ascii=False, indent=2。"""
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def publish_one(
    facet_path: Path,
    blog_root: Path,
    yyyy: str,
    mm: str,
    dd: str,
) -> str:
    """处理单个 facet 文件。返回 'wrote' / 'skipped' / 'failed'。

    失败仅影响当前文件；调用方累计。
    """
    try:
        sid = extract_sid(facet_path)
    except ValueError as e:
        print(f"[publish-facet] warning: {e}", file=sys.stderr)
        return "failed"

    # 源 JSON 解析
    try:
        src_obj = load_json(facet_path)
    except (OSError, json.JSONDecodeError) as e:
        print(
            f"[publish-facet] warning: failed to parse {facet_path}: {e}",
            file=sys.stderr,
        )
        return "failed"

    target_dir = blog_root / yyyy / mm / dd
    target_path = target_dir / f"{sid}.json"

    # mkdir -p 目标目录（权限不足等让外层捕获以决定是否整体 exit 1）
    target_dir.mkdir(parents=True, exist_ok=True)

    if target_path.exists():
        try:
            dst_obj = load_json(target_path)
        except (OSError, json.JSONDecodeError) as e:
            # 目标文件损坏：覆盖写（宁可修坏的，也别让发布流程永久卡住）
            print(
                f"[publish-facet] warning: target {target_path} unreadable, overwriting: {e}",
                file=sys.stderr,
            )
            try:
                dump_json(src_obj, target_path)
                return "wrote"
            except OSError as e2:
                print(
                    f"[publish-facet] warning: write failed {target_path}: {e2}",
                    file=sys.stderr,
                )
                return "failed"

        # 语义等价比较（dict / list / scalar 递归 ==）；
        # v1.2：friction_types / anchors.files 做 canonical 排序副本后再比，
        # 避免 LLM 两次生成顺序抖动触发无意义 wrote。
        if _canonicalize(src_obj) == _canonicalize(dst_obj):
            return "skipped"

        try:
            dump_json(src_obj, target_path)
            return "wrote"
        except OSError as e:
            print(
                f"[publish-facet] warning: write failed {target_path}: {e}",
                file=sys.stderr,
            )
            return "failed"

    # 目标不存在 → 直接写
    try:
        dump_json(src_obj, target_path)
        return "wrote"
    except OSError as e:
        print(
            f"[publish-facet] warning: write failed {target_path}: {e}",
            file=sys.stderr,
        )
        return "failed"


def run(run_dir: str, target_date: str, blog_root: str) -> int:
    """主流程。返回 exit code。"""
    # TARGET_DATE 校验：格式非法 exit 2
    try:
        yyyy, mm, dd = parse_target_date(target_date)
    except ValueError as e:
        print(f"[publish-facet] error: {e}", file=sys.stderr)
        return 2

    run_path = Path(run_dir)
    blog_path = Path(blog_root)

    # blog 根不存在时尝试创建；权限不足 → exit 1
    try:
        blog_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(
            f"[publish-facet] error: cannot create BLOG_FACETS_ROOT {blog_root}: {e}",
            file=sys.stderr,
        )
        return 1

    # 提前尝试创建日期目录；根目录权限不足在此直接暴露
    try:
        (blog_path / yyyy / mm / dd).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(
            f"[publish-facet] error: cannot create target dir under {blog_root}: {e}",
            file=sys.stderr,
        )
        return 1

    pattern = str(run_path / "facet-*.json")
    facet_files = sorted(Path(p) for p in glob.glob(pattern))

    wrote = skipped = failed = 0
    for fp in facet_files:
        result = publish_one(fp, blog_path, yyyy, mm, dd)
        if result == "wrote":
            wrote += 1
        elif result == "skipped":
            skipped += 1
        else:
            failed += 1

    print(f"[publish-facet] wrote={wrote} skipped={skipped} failed={failed}")
    return 0


def main() -> int:
    run_dir = os.environ.get("RUN_DIR")
    target_date = os.environ.get("TARGET_DATE")

    if not run_dir:
        print("[publish-facet] error: RUN_DIR env var required", file=sys.stderr)
        return 2
    if not target_date:
        print(
            "[publish-facet] error: TARGET_DATE env var required",
            file=sys.stderr,
        )
        return 2

    blog_root = os.environ.get("BLOG_FACETS_ROOT")
    if not blog_root:
        blog_dir = os.environ.get("BLOG_DIR")
        if blog_dir:
            blog_root = os.path.join(blog_dir, "facets", "facets")
        else:
            print(
                "[publish-facet] error: BLOG_FACETS_ROOT or BLOG_DIR env var required",
                file=sys.stderr,
            )
            return 2

    return run(run_dir, target_date, blog_root)


if __name__ == "__main__":
    sys.exit(main())
