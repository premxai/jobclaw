#!/usr/bin/env python3
"""Per-platform scraper health aggregation.

Answers the operational question "is Workday (or any platform) actually
working, or silently rate-limited / erroring?" by aggregating recent ATS run
summaries (persisted in scraper_runs.summary_json by log_scraper_run) into a
per-platform success/error-rate breakdown by classify_failure category.

Pure aggregation (`aggregate_platform_health`) is DB-free and unit-tested; the
DB fetch lives in `fetch_recent_ats_run_summaries`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.database.db_utils import is_postgres

# Error categories worth calling out on a health dashboard. `bad_target` is a
# target-quality signal (dead slug) rather than an infra problem, so it is
# tracked separately from the anti-bot / throttling signals that mean "the
# platform is fighting us".
INFRA_ERROR_CATEGORIES = ("rate_limited", "anti_bot", "timeout", "connection", "parse")


def _coerce_summary(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def aggregate_platform_health(summaries: list) -> dict:
    """Fold a list of run summary dicts (or JSON strings) into per-platform health.

    Returns {platform: {attempted, succeeded, failed, jobs_fetched,
    success_rate, error_rate, infra_error_rate, categories{...}}}.
    """
    agg: dict[str, dict] = {}
    for raw in summaries:
        summary = _coerce_summary(raw)
        platforms = summary.get("platforms") or {}
        breakdown = summary.get("failure_breakdown") or {}
        for platform, metrics in platforms.items():
            slot = agg.setdefault(
                platform,
                {"attempted": 0, "succeeded": 0, "failed": 0, "jobs_fetched": 0, "categories": {}},
            )
            slot["attempted"] += int(metrics.get("attempted") or 0)
            slot["succeeded"] += int(metrics.get("succeeded") or 0)
            slot["failed"] += int(metrics.get("failed") or 0)
            slot["jobs_fetched"] += int(metrics.get("jobs_fetched") or 0)
            for category, count in (breakdown.get(platform) or {}).items():
                slot["categories"][category] = slot["categories"].get(category, 0) + int(count or 0)

    for slot in agg.values():
        attempted = slot["attempted"] or 0
        slot["success_rate"] = round(slot["succeeded"] / attempted, 4) if attempted else None
        slot["error_rate"] = round(slot["failed"] / attempted, 4) if attempted else None
        infra_errors = sum(slot["categories"].get(cat, 0) for cat in INFRA_ERROR_CATEGORIES)
        slot["infra_error_rate"] = round(infra_errors / attempted, 4) if attempted else None
    return agg


def fetch_recent_ats_run_summaries(conn, limit: int = 25) -> list:
    """Fetch summary_json from the most recent ATS scraper runs."""
    cursor = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"
    cursor.execute(
        f"""
        SELECT summary_json FROM scraper_runs
        WHERE scraper = {placeholder} AND summary_json IS NOT NULL AND summary_json <> ''
        ORDER BY run_at DESC
        LIMIT {placeholder}
        """,
        ("scrape_ats", limit),
    )
    return [row[0] if not hasattr(row, "keys") else row["summary_json"] for row in cursor.fetchall()]


def get_platform_health(conn, runs_limit: int = 25) -> dict:
    """DB-backed convenience: aggregate the last `runs_limit` ATS runs."""
    return aggregate_platform_health(fetch_recent_ats_run_summaries(conn, runs_limit))


if __name__ == "__main__":
    from scripts.database.db_utils import get_connection

    conn = get_connection()
    try:
        health = get_platform_health(conn)
    finally:
        conn.close()
    print(json.dumps(health, indent=2, sort_keys=True))
