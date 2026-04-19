#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render a Hexo Markdown daily report to standalone email HTML."""
from __future__ import annotations

import argparse
from pathlib import Path


STYLE = (
    "<style>"
    "body{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;"
    "max-width:760px;margin:24px auto;padding:0 16px;line-height:1.65;color:#222}"
    "pre{background:#f6f8fa;padding:12px;border-radius:6px;overflow-x:auto}"
    "code{background:#f6f8fa;padding:2px 4px;border-radius:3px}"
    "blockquote{border-left:4px solid #dfe2e5;padding:0 12px;color:#6a737d;margin:0}"
    "table{border-collapse:collapse}td,th{border:1px solid #dfe2e5;padding:6px 10px}"
    "h1,h2,h3{border-bottom:1px solid #eaecef;padding-bottom:4px}"
    "</style>"
)


def strip_frontmatter(md: str) -> str:
    if md.startswith("---"):
        parts = md.split("---", 2)
        if len(parts) >= 3:
            return parts[2].lstrip()
    return md


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markdown", required=True)
    parser.add_argument("--output", required=True)
    ns = parser.parse_args()

    try:
        import markdown  # type: ignore
    except ImportError as exc:
        raise SystemExit("python markdown package is required: pip3 install --user markdown") from exc

    md = strip_frontmatter(Path(ns.markdown).read_text(encoding="utf-8"))
    html = markdown.markdown(md, extensions=["fenced_code", "tables", "toc"])
    Path(ns.output).write_text(
        '<!doctype html><html><head><meta charset="utf-8">'
        + STYLE
        + "</head><body>"
        + html
        + "</body></html>",
        encoding="utf-8",
    )
    print(ns.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
