#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""slice-session.py — 为 LLM 子代理生成可安全 Read 的 session 窗口切片。

Claude Read 工具有文件大小 / token 上限，不能直接整读大型 jsonl。本脚本逐行扫描
raw session，只保留窗口内 user / assistant 的关键信号，并在单条消息和总输出上做硬
截断，产物供 session-reader / session-merger 读取。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

DEFAULT_MAX_BYTES = 180_000
DEFAULT_CHUNK_CHARS = 25_000
DEFAULT_MAX_FIELD_CHARS = 2_400
DEFAULT_MAX_TOOL_RESULT_CHARS = 900
DEFAULT_MAX_TOOL_INPUT_CHARS = 1_600


def _parse_iso(ts: str) -> Optional[datetime]:
    if not isinstance(ts, str) or not ts:
        return None
    s = ts[:-1] + "+00:00" if ts.endswith("Z") else ts
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _in_window(ts: str, start: datetime, end: datetime) -> bool:
    dt = _parse_iso(ts)
    return dt is not None and start <= dt < end


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    omitted = len(text) - limit
    return text[:limit].rstrip() + f"\n...[truncated {omitted} chars]", True


def _json_compact(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return repr(value)


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                print(
                    f"[slice-session] WARN {path}:{lineno} json parse failed: {e}",
                    file=sys.stderr,
                )
                continue
            if isinstance(obj, dict):
                obj["_line"] = lineno
                yield obj


def _content_items(message: Any) -> list[Any]:
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, list):
        return content
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def _render_tool_use(item: dict[str, Any], max_tool_input_chars: int) -> tuple[str, bool]:
    name = item.get("name")
    tool_id = item.get("id")
    tool_input = item.get("input")
    input_text, truncated = _truncate(_json_compact(tool_input), max_tool_input_chars)
    return (
        "\n".join(
            [
                f"- tool_use: {name or '<unknown>'}",
                f"  id: {tool_id or '<none>'}",
                f"  input: {input_text}",
            ]
        ),
        truncated,
    )


def _render_tool_result(item: dict[str, Any], max_tool_result_chars: int) -> tuple[str, bool]:
    if item.get("is_error") is not True:
        return "", False
    content = item.get("content")
    text = content if isinstance(content, str) else _json_compact(content)
    text, truncated = _truncate(text, max_tool_result_chars)
    return (
        "\n".join(
            [
                f"- tool_result_error: {item.get('tool_use_id') or '<unknown>'}",
                f"  content: {text}",
            ]
        ),
        truncated,
    )


def render_event(
    obj: dict[str, Any],
    max_field_chars: int,
    max_tool_input_chars: int,
    max_tool_result_chars: int,
) -> tuple[str, bool]:
    mtype = obj.get("type")
    ts = obj.get("timestamp") or "<no timestamp>"
    line = obj.get("_line")
    header = f"## {ts} line={line} type={mtype}"
    message = obj.get("message")
    parts = [header]
    truncated = False

    for item in _content_items(message):
        if not isinstance(item, dict):
            continue
        itype = item.get("type")
        if itype == "text":
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                text, did_truncate = _truncate(text.strip(), max_field_chars)
                truncated = truncated or did_truncate
                parts.append(text)
        elif itype == "tool_use":
            rendered, did_truncate = _render_tool_use(item, max_tool_input_chars)
            truncated = truncated or did_truncate
            parts.append(rendered)
        elif itype == "tool_result":
            rendered, did_truncate = _render_tool_result(item, max_tool_result_chars)
            truncated = truncated or did_truncate
            if rendered:
                parts.append(rendered)

    if len(parts) == 1:
        return "", False
    return "\n".join(parts).rstrip() + "\n", truncated


def build_slice(
    session_file: Path,
    window_start: str,
    window_end: str,
    max_bytes: int,
    max_field_chars: int,
    max_tool_input_chars: int,
    max_tool_result_chars: int,
) -> tuple[str, dict[str, int]]:
    start_dt = _parse_iso(window_start)
    end_dt = _parse_iso(window_end)
    if start_dt is None or end_dt is None:
        raise ValueError("invalid window iso")

    sid = session_file.stem
    chunks: list[str] = [
        f"# Session Slice: {sid}\n",
        f"- source: {session_file}\n",
        f"- window: {window_start} <= timestamp < {window_end}\n",
        "- note: raw jsonl is intentionally not reproduced; bulky fields are truncated.\n\n",
    ]
    stats = {
        "window_events": 0,
        "included_events": 0,
        "omitted_events": 0,
        "truncated_fields": 0,
    }
    used = sum(len(c.encode("utf-8")) for c in chunks)
    summary_budget = 512
    content_budget = max(max_bytes - summary_budget, used)

    for obj in _iter_jsonl(session_file):
        ts = obj.get("timestamp")
        if not isinstance(ts, str) or not _in_window(ts, start_dt, end_dt):
            continue
        if obj.get("type") not in {"user", "assistant"}:
            continue
        rendered, truncated = render_event(
            obj,
            max_field_chars=max_field_chars,
            max_tool_input_chars=max_tool_input_chars,
            max_tool_result_chars=max_tool_result_chars,
        )
        if not rendered:
            continue
        stats["window_events"] += 1
        if truncated:
            stats["truncated_fields"] += 1
        rendered_bytes = len(rendered.encode("utf-8")) + 1
        if used + rendered_bytes > content_budget:
            stats["omitted_events"] += 1
            continue
        chunks.append(rendered + "\n")
        used += rendered_bytes
        stats["included_events"] += 1

    summary = (
        "\n# Slice Stats\n"
        f"- window_events: {stats['window_events']}\n"
        f"- included_events: {stats['included_events']}\n"
        f"- omitted_events_due_to_budget: {stats['omitted_events']}\n"
        f"- truncated_fields: {stats['truncated_fields']}\n"
    )
    summary_bytes = len(summary.encode("utf-8"))
    while used + summary_bytes > max_bytes and len(chunks) > 4:
        removed = chunks.pop()
        used -= len(removed.encode("utf-8"))
        stats["included_events"] = max(0, stats["included_events"] - 1)
        stats["omitted_events"] += 1
    chunks.append(summary)
    return "".join(chunks), stats


def write_chunked_slice(
    content: str,
    output: Path,
    chunk_dir: Path,
    chunk_chars: int,
) -> tuple[int, int]:
    """Write an index file plus bounded chunk files.

    The index is what agents Read first. They then Read each chunk one at a time and
    summarize it before producing the final card/facet, matching the /insights-style
    "long transcript -> chunks -> summaries -> facets" pattern.
    """
    chunk_dir.mkdir(parents=True, exist_ok=True)
    for old in chunk_dir.glob("chunk-*.md"):
        old.unlink()

    chunks: list[str] = []
    start = 0
    while start < len(content):
        end = min(start + chunk_chars, len(content))
        if end < len(content):
            # Prefer splitting between rendered events so a message is less likely to
            # be cut in the middle. Fall back to a hard cut if no boundary is nearby.
            boundary = content.rfind("\n## ", start + max(1, chunk_chars // 2), end)
            if boundary != -1:
                end = boundary
        chunks.append(content[start:end].strip() + "\n")
        start = end

    chunk_paths: list[Path] = []
    for idx, chunk in enumerate(chunks, start=1):
        path = chunk_dir / f"chunk-{idx:03d}.md"
        path.write_text(chunk, encoding="utf-8")
        chunk_paths.append(path)

    index_lines = [
        "# Session Slice Index",
        f"- chunks: {len(chunk_paths)}",
        f"- chunk_chars_limit: {chunk_chars}",
        "- read_order:",
    ]
    for path in chunk_paths:
        index_lines.append(f"  - {path} ({path.stat().st_size} bytes)")
    index_lines.extend(
        [
            "",
            "## Reading Contract",
            "Read chunk files one at a time. For multi-chunk sessions, summarize each chunk first, then extract the final card/facet from those summaries plus metadata.",
            "Chunk summary focus: user asked / Claude did / files or tools touched / friction / outcome.",
            "",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(index_lines), encoding="utf-8")
    return len(chunk_paths), output.stat().st_size


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create a bounded Markdown slice from a Claude Code session jsonl.")
    p.add_argument("--session-file", required=True)
    p.add_argument("--window-start", required=True)
    p.add_argument("--window-end", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--chunk-dir", help="If set, write output as a small index plus 25k-char chunks in this directory.")
    p.add_argument("--chunk-chars", type=int, default=DEFAULT_CHUNK_CHARS)
    p.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    p.add_argument("--max-field-chars", type=int, default=DEFAULT_MAX_FIELD_CHARS)
    p.add_argument("--max-tool-input-chars", type=int, default=DEFAULT_MAX_TOOL_INPUT_CHARS)
    p.add_argument("--max-tool-result-chars", type=int, default=DEFAULT_MAX_TOOL_RESULT_CHARS)
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    session_file = Path(args.session_file).expanduser()
    output = Path(args.output).expanduser()
    if not session_file.is_file():
        print(f"[slice-session] ERROR: session file not found: {session_file}", file=sys.stderr)
        return 2
    try:
        content, stats = build_slice(
            session_file=session_file,
            window_start=args.window_start,
            window_end=args.window_end,
            max_bytes=args.max_bytes,
            max_field_chars=args.max_field_chars,
            max_tool_input_chars=args.max_tool_input_chars,
            max_tool_result_chars=args.max_tool_result_chars,
        )
    except ValueError as e:
        print(f"[slice-session] ERROR: {e}", file=sys.stderr)
        return 2

    if args.chunk_dir:
        chunks, size = write_chunked_slice(
            content=content,
            output=output,
            chunk_dir=Path(args.chunk_dir).expanduser(),
            chunk_chars=args.chunk_chars,
        )
        print(
            f"[slice-session] wrote index {output} bytes={size} chunks={chunks} "
            f"included={stats['included_events']} omitted={stats['omitted_events']}"
        )
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    size = output.stat().st_size
    print(
        f"[slice-session] wrote {output} bytes={size} "
        f"included={stats['included_events']} omitted={stats['omitted_events']}"
    )
    if size > args.max_bytes:
        print(
            f"[slice-session] ERROR: output exceeds max bytes: {size} > {args.max_bytes}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
