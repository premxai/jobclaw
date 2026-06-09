"""Decide whether the scheduled Workday long-tail sweep should run."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.database import db_utils
from scripts.database.db_utils import get_connection
from scripts.utils.logger import _log


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _first_value(row, default=0):
    if row is None:
        return default
    if isinstance(row, dict):
        return next(iter(row.values()), default)
    try:
        return row[0]
    except Exception:
        return default


def evaluate_workday_guard(metrics: dict, thresholds: dict, *, force: bool = False) -> tuple[bool, list[str]]:
    if force:
        return True, ["forced"]

    reasons = []
    if int(metrics.get("total_jobs", 0)) >= int(thresholds["max_total_jobs"]):
        reasons.append("total_jobs_at_or_above_limit")
    if int(metrics.get("accepted_unposted", 0)) >= int(thresholds["max_accepted_unposted"]):
        reasons.append("accepted_unposted_backlog_high")
    if int(metrics.get("active_workday_leases", 0)) > 0:
        reasons.append("active_workday_leases_present")

    statuses = [str(s).lower() for s in metrics.get("recent_workday_statuses", [])]
    bad_streak = 0
    for status in statuses:
        if status in {"failed", "degraded"}:
            bad_streak += 1
        else:
            break
    if bad_streak >= int(thresholds["max_recent_bad_runs"]):
        reasons.append("recent_workday_runs_bad")

    return not reasons, reasons or ["ok"]


def collect_metrics(conn) -> dict:
    cursor = conn.cursor()
    placeholder = "%s" if db_utils.is_postgres() else "?"
    now = datetime.now(timezone.utc).isoformat()

    def scalar(sql, params=()):
        cursor.execute(sql, params)
        return int(_first_value(cursor.fetchone(), 0) or 0)

    total_jobs = scalar("SELECT COUNT(*) FROM jobs")
    accepted_unposted = scalar(
        """
        SELECT COUNT(*) FROM jobs
        WHERE status = 'unposted'
          AND COALESCE(quality_state, 'needs_review') = 'accepted'
        """
    )
    active_workday_leases = scalar(
        f"""
        SELECT COUNT(*) FROM companies
        WHERE ats_type = 'workday'
          AND COALESCE(is_dead, 0) = 0
          AND lease_until IS NOT NULL
          AND lease_until > {placeholder}
        """,
        (now,),
    )
    cursor.execute(
        f"""
        SELECT COALESCE(status, 'success') AS status
        FROM scraper_runs
        WHERE scraper = 'scrape_ats'
          AND COALESCE(summary_json, '') LIKE {placeholder}
        ORDER BY run_at DESC
        LIMIT 3
        """,
        ('%"workday"%',),
    )
    recent_statuses = []
    for row in cursor.fetchall():
        if isinstance(row, dict):
            recent_statuses.append(row.get("status") or "success")
        else:
            recent_statuses.append(row[0] or "success")

    return {
        "total_jobs": total_jobs,
        "accepted_unposted": accepted_unposted,
        "active_workday_leases": active_workday_leases,
        "recent_workday_statuses": recent_statuses,
    }


def _write_github_output(name: str, value: str) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def main() -> int:
    thresholds = {
        "max_total_jobs": _env_int("JOBCLAW_WORKDAY_SWEEP_MAX_TOTAL_JOBS", 50000),
        "max_accepted_unposted": _env_int("JOBCLAW_WORKDAY_SWEEP_MAX_ACCEPTED_UNPOSTED", 1000),
        "max_recent_bad_runs": _env_int("JOBCLAW_WORKDAY_SWEEP_MAX_RECENT_BAD_RUNS", 2),
    }
    force = _env_bool("JOBCLAW_WORKDAY_SWEEP_FORCE", False)

    conn = get_connection()
    try:
        metrics = collect_metrics(conn)
    finally:
        conn.close()

    should_run, reasons = evaluate_workday_guard(metrics, thresholds, force=force)
    payload = {
        "should_run": should_run,
        "reasons": reasons,
        "metrics": metrics,
        "thresholds": thresholds,
        "force": force,
    }
    _log(f"[workday-guard] {json.dumps(payload, sort_keys=True)}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    _write_github_output("should_run", "true" if should_run else "false")
    _write_github_output("reason", ",".join(reasons))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
