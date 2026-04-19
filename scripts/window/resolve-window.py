#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Resolve daily-report query window from raw skill args.

Branch order is intentionally mechanical:
1. WINDOW_END=<epoch> -> epoch
2. first YYYY-MM-DD -> ymd, interpreted as Asia/Shanghai natural day
3. fallback -> most recent complete Asia/Shanghai natural day

Default output is shell exports so callers can use:
  eval "$(python3 resolve-window.py --args "$ARGS")"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


EPOCH_RE = re.compile(r"WINDOW_END=([0-9]{9,11})")
YMD_RE = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2})")
CST = ZoneInfo(os.environ.get("DAILY_REPORT_TZ", "Asia/Shanghai"))


def _iso_utc(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve(raw_args: str, now_epoch: int | None = None) -> dict[str, str | int]:
    epoch_match = EPOCH_RE.search(raw_args or "")
    if epoch_match:
        branch = "epoch"
        window_end = int(epoch_match.group(1))
        window_start = window_end - 86400
    else:
        ymd_match = YMD_RE.search(raw_args or "")
        if ymd_match:
            branch = "ymd"
            ymd = ymd_match.group(1)
            start_dt = datetime.combine(
                datetime.strptime(ymd, "%Y-%m-%d").date(), time.min, tzinfo=CST
            )
            window_start = int(start_dt.timestamp())
            window_end = window_start + 86400
        else:
            branch = "default"
            now = (
                datetime.fromtimestamp(now_epoch, timezone.utc)
                if now_epoch is not None
                else datetime.now(timezone.utc)
            )
            local_now = now.astimezone(CST)
            local_midnight = datetime.combine(local_now.date(), time.min, tzinfo=CST)
            window_end = int(local_midnight.timestamp())
            window_start = window_end - 86400

    target_date = datetime.fromtimestamp(window_end - 1, CST).strftime("%Y-%m-%d")
    return {
        "BRANCH": branch,
        "WINDOW_START": window_start,
        "WINDOW_END": window_end,
        "WINDOW_START_ISO": _iso_utc(window_start),
        "WINDOW_END_ISO": _iso_utc(window_end),
        "TARGET_DATE": target_date,
    }


def _shell_quote(value: str | int) -> str:
    s = str(value)
    return "'" + s.replace("'", "'\"'\"'") + "'"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--args", default="", help="Raw args passed to the skill")
    parser.add_argument("--args-file", help="Read raw args from file")
    parser.add_argument("--now-epoch", type=int, help="Override current time for tests")
    parser.add_argument("--format", choices=("shell", "json"), default="shell")
    ns = parser.parse_args()

    raw_args = ns.args
    if ns.args_file:
        with open(ns.args_file, "r", encoding="utf-8") as f:
            raw_args = f.read()

    data = resolve(raw_args, ns.now_epoch)
    sys.stderr.write(
        "[daily-report] window=[{}, {}) label={} branch={}\n".format(
            data["WINDOW_START_ISO"],
            data["WINDOW_END_ISO"],
            data["TARGET_DATE"],
            data["BRANCH"],
        )
    )

    if ns.format == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        for key in (
            "BRANCH",
            "WINDOW_START",
            "WINDOW_END",
            "WINDOW_START_ISO",
            "WINDOW_END_ISO",
            "TARGET_DATE",
        ):
            print(f"export {key}={_shell_quote(data[key])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
