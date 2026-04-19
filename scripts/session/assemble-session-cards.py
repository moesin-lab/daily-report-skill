#!/usr/bin/env python3
"""
第 1 步 f：组装最终卡片文件。

拼接规则：
- 读 $RUN_DIR/merge-groups.json（可选）拿到合并组；每组若对应的 merged-<gid>.md 存在且非空，
  就纳入输出，并把组内 session_ids 记为"已被合并"
- 遍历 phase1-*.md，跳过已被合并的 sid 和空文件
- 保留的 phase1 卡片 + merged 卡片拼接成 session-cards.md，各块之间空一行

不做 schema 校验（那是步骤 c 的 lint 职责），只判文件存在且非空。

环境变量：
  RUN_DIR（必填）

输出 $RUN_DIR/session-cards.md，stdout 打印卡片数汇总。
"""
import json
import os
import pathlib
import sys


def main() -> int:
    run_dir_env = os.environ.get("RUN_DIR")
    if not run_dir_env:
        sys.stderr.write("assemble: RUN_DIR env not set\n")
        return 2
    run_dir = pathlib.Path(run_dir_env)
    if not run_dir.is_dir():
        sys.stderr.write(f"assemble: RUN_DIR not a directory: {run_dir}\n")
        return 2

    merged_session_ids: set[str] = set()
    merged_blocks: list[str] = []

    groups_file = run_dir / "merge-groups.json"
    if groups_file.exists():
        groups = json.loads(groups_file.read_text())
        for g in groups:
            gid = g["group_id"]
            mp = run_dir / f"merged-{gid}.md"
            if not mp.exists() or mp.stat().st_size == 0:
                sys.stderr.write(
                    f"[step 1.5] merge missing/empty for {gid}, fallback to phase1\n"
                )
                continue
            merged_blocks.append(mp.read_text().rstrip() + "\n")
            merged_session_ids.update(g["session_ids"])

    kept: list[str] = []
    for p in sorted(run_dir.glob("phase1-*.md")):
        sid = p.stem[len("phase1-"):]
        if sid in merged_session_ids:
            continue
        if p.stat().st_size == 0:
            sys.stderr.write(f"[step 1.5] phase1 empty: {p.name}\n")
            continue
        kept.append(p.read_text().rstrip() + "\n")

    out = "\n\n".join(kept + merged_blocks)
    (run_dir / "session-cards.md").write_text(out)
    print(
        f"[step 1.5] final cards: {len(kept) + len(merged_blocks)} "
        f"(merged groups: {len(merged_blocks)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
