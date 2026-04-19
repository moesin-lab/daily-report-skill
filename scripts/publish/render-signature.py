#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render reference/templates/signature.md, replacing {{AUTHOR_*}} placeholders.

Reads env: AUTHOR_NAME, AUTHOR_URL, AUTHOR_AGENT_NAME.
Unset / empty vars fall back to neutral wording so the signature stays publishable.
Writes the rendered signature to stdout; strips the HTML comment block that
only documents placeholder substitution rules.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[2]
TEMPLATE = SKILL_DIR / "reference" / "templates" / "signature.md"


def main() -> int:
    text = TEMPLATE.read_text(encoding="utf-8")
    # Drop the internal HTML comment (starts with <!-- and ends with -->)
    text = re.sub(r"<!--.*?-->\n?", "", text, flags=re.DOTALL)

    name = os.environ.get("AUTHOR_NAME", "").strip() or "作者"
    url = os.environ.get("AUTHOR_URL", "").strip()
    agent = os.environ.get("AUTHOR_AGENT_NAME", "").strip() or "Claude Agent"

    if url:
        author_link = f"[{name}]({url})"
    else:
        author_link = name

    text = text.replace("[{{AUTHOR_NAME}}]({{AUTHOR_URL}})", author_link)
    text = text.replace("{{AUTHOR_NAME}}", name)
    text = text.replace("{{AUTHOR_URL}}", url)
    text = text.replace("{{AUTHOR_AGENT_NAME}}", agent)

    sys.stdout.write(text.rstrip() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
