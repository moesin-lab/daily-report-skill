#!/usr/bin/env python3
"""
Phase1 卡片格式 lint（daily-report skill 第 1 步 c/c.6 步骤）。

读 $RUN_DIR/phase1-*.md，按固定规则做机械校验：
- H2 `## session <sid>` 存在且 sid 匹配文件名
- 必填 bullet: 工作类型 / 状态 / 聚类锚点 / 关联事件
- 必填 H3: 事件摘要 / 认知增量 / 残留问题
- 聚类锚点 5 子项齐全: repo / branch_or_pr / issue_or_bug / files / target_object
- 占位符 `<...>` 残留（只抓含中文或 <SESSION_ID>/<GROUP_ID>，避免误伤真实路径）

输出 $RUN_DIR/lint-report.json，结构：
  [{"sid": "...", "path": "...", "errors": ["..."]}]

环境变量：
  RUN_DIR（必填）— run 目录绝对路径

不接受命令行参数。设计为确定性、零 LLM，只负责格式闸门；语义质量留给主 agent 步骤 1.4 察觉。
"""
import json
import os
import pathlib
import re
import sys

REQUIRED_BULLETS = ["工作类型", "状态", "聚类锚点", "关联事件"]
REQUIRED_H3 = ["事件摘要", "认知增量", "残留问题"]
REQUIRED_ANCHORS = ["repo", "branch_or_pr", "issue_or_bug", "files", "target_object"]
PLACEHOLDER_RE = re.compile(r"<[^\n>]*[\u4e00-\u9fff][^\n>]*>|<(SESSION_ID|GROUP_ID)>")


def lint(path: pathlib.Path, sid: str) -> list[str]:
    errors: list[str] = []
    text = path.read_text()

    if not re.search(rf"^## session {re.escape(sid)}\b", text, re.MULTILINE):
        errors.append(f"missing H2 `## session {sid}`")
    for b in REQUIRED_BULLETS:
        if not re.search(rf"^- \*\*{re.escape(b)}\*\*", text, re.MULTILINE):
            errors.append(f"missing bullet `**{b}**`")
    for h in REQUIRED_H3:
        if not re.search(rf"^### {re.escape(h)}\s*$", text, re.MULTILINE):
            errors.append(f"missing H3 `### {h}`")
    for a in REQUIRED_ANCHORS:
        if not re.search(rf"^  - {re.escape(a)}:", text, re.MULTILINE):
            errors.append(f"聚类锚点 missing sub-bullet `{a}`")
    for m in PLACEHOLDER_RE.finditer(text):
        errors.append(f"unresolved placeholder {m.group(0)!r}")
    return errors


def main() -> int:
    run_dir_env = os.environ.get("RUN_DIR")
    if not run_dir_env:
        sys.stderr.write("lint-phase1: RUN_DIR env not set\n")
        return 2
    run_dir = pathlib.Path(run_dir_env)
    if not run_dir.is_dir():
        sys.stderr.write(f"lint-phase1: RUN_DIR not a directory: {run_dir}\n")
        return 2

    cards = sorted(run_dir.glob("phase1-*.md"))
    report = []
    for p in cards:
        sid = p.stem[len("phase1-"):]
        errs = lint(p, sid)
        if errs:
            report.append({"sid": sid, "target": "md", "path": str(p), "errors": errs})

    (run_dir / "lint-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )
    print(f"[step 1.3 lint] {len(cards)} cards, {len(report)} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
