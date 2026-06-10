#!/usr/bin/env python3
"""Decide which scheduled scraping jobs are overdue.

GitHub scheduled workflows can be delayed or skipped. This script reads the
canonical DB state and turns each controller wake-up into a catch-up pass:
run only the jobs whose last successful run/post is older than its target SLO.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.database import db_utils
from scripts.database.db_utils import get_connection
from scripts.utils.logger import _log

FAST_PLATFORMS = {"greenhouse", "lever", "ashby"}
MEDIUM_PLATFORMS = {"workday", "workable", "rippling", "smartrecruiters", "bamboohr"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _placeholder() -> str:
    return "%s" if db_utils.is_postgres() else "?"


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _row_get(row, key: str, index: int):
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def _summary_platforms(summary_json: str | None) -> set[str]:
    if not summary_json:
        return set()
    try:
        summary = json.loads(summary_json)
    except (TypeError, json.JSONDecodeError):
        return set()
    platforms = summary.get("platforms") or {}
    if isinstance(platforms, dict):
        return {str(key).lower() for key in platforms}
    return set()


def latest_run_at(conn, scraper: str, platform_any: set[str] | None = None) -> datetime | None:
    cursor = conn.cursor()
    p = _placeholder()
    cursor.execute(
        f"""
        SELECT run_at, summary_json, status
        FROM scraper_runs
        WHERE scraper = {p}
          AND COALESCE(status, 'success') IN ('success', 'degraded')
        ORDER BY run_at DESC
        LIMIT 30
        """,
        (scraper,),
    )
    for row in cursor.fetchall():
        summary_platforms = _summary_platforms(_row_get(row, "summary_json", 1))
        if platform_any and not (summary_platforms & platform_any):
            continue
        return _parse_dt(_row_get(row, "run_at", 0))
    return None


def latest_discord_post_at(conn) -> datetime | None:
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(posted_at) FROM job_fingerprints WHERE posted_at IS NOT NULL")
    row = cursor.fetchone()
    if row is None:
        return None
    value = next(iter(row.values())) if isinstance(row, dict) else row[0]
    return _parse_dt(value)


def accepted_unposted_backlog(conn, hours: int) -> int:
    cursor = conn.cursor()
    p = _placeholder()
    if db_utils.is_postgres():
        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM jobs
            WHERE status = 'unposted'
              AND is_active = TRUE
              AND COALESCE(quality_state, 'needs_review') = 'accepted'
              AND first_seen::timestamptz >= NOW() - ({p} * INTERVAL '1 hour')
            """,
            (hours,),
        )
    else:
        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM jobs
            WHERE status = 'unposted'
              AND is_active = 1
              AND COALESCE(quality_state, 'needs_review') = 'accepted'
              AND datetime(first_seen) >= datetime('now', {p})
            """,
            (f"-{hours} hours",),
        )
    row = cursor.fetchone()
    return int((next(iter(row.values())) if isinstance(row, dict) else row[0]) or 0)


def _is_due(latest: datetime | None, now: datetime, interval_minutes: int) -> bool:
    if latest is None:
        return True
    return now - latest >= timedelta(minutes=interval_minutes)


def decide(conn, now: datetime) -> dict:
    discord_window = max(1, _env_int("JOBCLAW_DISCORD_LOOKBACK_HOURS", 24))
    state = {
        "hot": latest_run_at(conn, "scrape_hot"),
        "fast": latest_run_at(conn, "scrape_ats", FAST_PLATFORMS),
        "medium": latest_run_at(conn, "scrape_ats", MEDIUM_PLATFORMS),
        "discord": latest_discord_post_at(conn),
    }
    backlog = accepted_unposted_backlog(conn, discord_window)
    intervals = {
        "hot": max(5, _env_int("JOBCLAW_CONTROLLER_HOT_INTERVAL_MINUTES", 20)),
        "fast": max(15, _env_int("JOBCLAW_CONTROLLER_FAST_INTERVAL_MINUTES", 75)),
        "medium": max(15, _env_int("JOBCLAW_CONTROLLER_MEDIUM_INTERVAL_MINUTES", 90)),
        "discord": max(5, _env_int("JOBCLAW_CONTROLLER_DISCORD_INTERVAL_MINUTES", 15)),
    }
    due = {
        "hot": _is_due(state["hot"], now, intervals["hot"]),
        "fast": _is_due(state["fast"], now, intervals["fast"]),
        "medium": _is_due(state["medium"], now, intervals["medium"]),
        "discord": backlog > 0 and _is_due(state["discord"], now, intervals["discord"]),
    }
    return {
        "now": now.isoformat(),
        "due": due,
        "latest": {key: value.isoformat() if value else None for key, value in state.items()},
        "interval_minutes": intervals,
        "accepted_unposted_backlog": backlog,
    }


def _write_output(name: str, value: str) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def main() -> int:
    conn = get_connection()
    try:
        payload = decide(conn, datetime.now(timezone.utc))
    finally:
        conn.close()

    _log(f"[schedule-decider] {json.dumps(payload, sort_keys=True)}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    for key, value in payload["due"].items():
        _write_output(f"run_{key}", "true" if value else "false")
    _write_output("accepted_unposted_backlog", str(payload["accepted_unposted_backlog"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
