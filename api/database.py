"""
Database query layer for the JobClaw API.

Supports both SQLite (default) and PostgreSQL (via DATABASE_URL).
Provides read-only query functions for the REST API.
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "jobclaw.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "")


def _is_pg() -> bool:
    return DATABASE_URL.startswith("postgres")


def get_db():
    """Get a database connection (SQLite or PostgreSQL)."""
    if _is_pg():
        import psycopg2
        import psycopg2.extras

        return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row) -> dict:
    """Convert a row to a dict with parsed keywords."""
    d = dict(row)
    if d.get("keywords_matched"):
        try:
            d["keywords_matched"] = json.loads(d["keywords_matched"])
        except (json.JSONDecodeError, TypeError):
            d["keywords_matched"] = []
    else:
        d["keywords_matched"] = []
    d["is_active"] = bool(d.get("is_active", True))
    return d


def _ph() -> str:
    """Placeholder character for the current backend."""
    return "%s" if _is_pg() else "?"


def get_jobs(
    page: int = 1,
    per_page: int = 50,
    company: str = None,
    ats: str = None,
    keyword: str = None,
    active_only: bool = True,
    search: str = None,
    recent_hours: int | None = None,
    quality: str | None = None,
) -> tuple[list[dict], int]:
    """Query jobs with pagination and filters."""
    conn = get_db()
    p = _ph()
    try:
        conditions = []
        params = []

        if active_only:
            conditions.append("is_active = TRUE" if _is_pg() else "is_active = 1")
        if company:
            conditions.append(f"LOWER(company) = LOWER({p})")
            params.append(company)
        if ats:
            conditions.append(f"LOWER(source_ats) = LOWER({p})")
            params.append(ats)
        if keyword:
            conditions.append(f"keywords_matched LIKE {p}")
            params.append(f"%{keyword}%")
        if search:
            if _is_pg():
                conditions.append(f"search_vector @@ websearch_to_tsquery('english', {p})")
                params.append(search)
            else:
                conditions.append(f"(title LIKE {p} OR company LIKE {p} OR description LIKE {p})")
                params.extend([f"%{search}%"] * 3)
        if recent_hours:
            if _is_pg():
                conditions.append(f"first_seen::timestamptz >= NOW() - ({p} * INTERVAL '1 hour')")
                params.append(recent_hours)
            else:
                conditions.append(f"datetime(first_seen) >= datetime('now', {p})")
                params.append(f"-{recent_hours} hours")
        if quality:
            conditions.append(f"COALESCE(quality_state, 'needs_review') = {p}")
            params.append(quality)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM jobs {where}", params)
        row = cursor.fetchone()
        total = row[0] if row else 0

        offset = (page - 1) * per_page

        # Safe ORDER BY — choose between two pre-defined static strings only.
        # Never interpolate user input into ORDER BY.
        if _is_pg() and search:
            order_clause = "ts_rank(search_vector, websearch_to_tsquery('english', %s)) DESC, first_seen DESC"
            extra_params = [search]
        else:
            order_clause = "first_seen DESC"
            extra_params = []

        query = f"""
            SELECT * FROM jobs {where}
            ORDER BY {order_clause}
            LIMIT {p} OFFSET {p}
        """
        cursor.execute(query, params + extra_params + [per_page, offset])
        rows = cursor.fetchall()
        return [_row_to_dict(r) for r in rows], total
    finally:
        conn.close()


def get_job_by_hash(internal_hash: str) -> dict | None:
    """Get a single job by its internal hash."""
    conn = get_db()
    p = _ph()
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM jobs WHERE internal_hash = {p}", (internal_hash,))
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_companies(ats: str = None) -> list[dict]:
    """Get companies with job counts."""
    conn = get_db()
    p = _ph()
    active = "TRUE" if _is_pg() else "1"
    try:
        cursor = conn.cursor()
        if ats:
            cursor.execute(
                f"""
                SELECT company, source_ats, COUNT(*) as job_count,
                       MAX(first_seen) as latest_job
                FROM jobs WHERE LOWER(source_ats) = LOWER({p}) AND is_active = {active}
                GROUP BY company, source_ats
                ORDER BY job_count DESC
            """,
                (ats,),
            )
        else:
            cursor.execute(f"""
                SELECT company, source_ats, COUNT(*) as job_count,
                       MAX(first_seen) as latest_job
                FROM jobs WHERE is_active = {active}
                GROUP BY company, source_ats
                ORDER BY job_count DESC
            """)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def get_stats() -> dict:
    """Get system-wide statistics."""
    conn = get_db()
    active = "TRUE" if _is_pg() else "1"
    try:
        cursor = conn.cursor()

        def _scalar(sql, params=()):
            cursor.execute(sql, params)
            row = cursor.fetchone()
            if isinstance(row, (list, tuple)):
                return row[0]
            if isinstance(row, dict):
                return list(row.values())[0]
            # sqlite3.Row — use index access
            return row[0]

        total = _scalar("SELECT COUNT(*) FROM jobs")
        active_count = _scalar(f"SELECT COUNT(*) FROM jobs WHERE is_active = {active}")
        inactive = total - active_count
        unposted = _scalar("SELECT COUNT(*) FROM jobs WHERE status = 'unposted'")
        posted = _scalar("SELECT COUNT(*) FROM jobs WHERE status = 'posted'")
        companies = _scalar(f"SELECT COUNT(DISTINCT company) FROM jobs WHERE is_active = {active}")

        quality_states = {}
        try:
            cursor.execute(
                "SELECT COALESCE(quality_state, 'needs_review') AS state, COUNT(*) AS cnt FROM jobs GROUP BY state"
            )
            quality_states = {dict(r).get("state", "needs_review"): dict(r).get("cnt", 0) for r in cursor.fetchall()}
        except Exception:
            quality_states = {}

        # Platform breakdown
        cursor.execute(f"SELECT source_ats, COUNT(*) as cnt FROM jobs WHERE is_active = {active} GROUP BY source_ats")
        rows = cursor.fetchall()
        platforms = {}
        for r in rows:
            d = dict(r)
            platforms[d.get("source_ats", "")] = d.get("cnt", 0)

        # Recent counts
        if _is_pg():
            last_24h = _scalar("SELECT COUNT(*) FROM jobs WHERE first_seen >= NOW() - INTERVAL '1 day'")
            last_7d = _scalar("SELECT COUNT(*) FROM jobs WHERE first_seen >= NOW() - INTERVAL '7 days'")
        else:
            last_24h = _scalar("SELECT COUNT(*) FROM jobs WHERE first_seen >= datetime('now', '-1 day')")
            last_7d = _scalar("SELECT COUNT(*) FROM jobs WHERE first_seen >= datetime('now', '-7 days')")

        queue = {}
        try:
            now = datetime.now(timezone.utc).isoformat()
            stale_hot_cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
            p = _ph()
            queue = {
                "mode": os.getenv("JOBCLAW_QUEUE_MODE", "active"),
                "backlog_due": _scalar(
                    f"""
                    SELECT COUNT(*) FROM companies
                    WHERE COALESCE(is_dead, 0) = 0
                      AND (COALESCE(next_due_at, next_scrape_at) IS NULL
                           OR COALESCE(next_due_at, next_scrape_at) <= {p})
                    """,
                    (now,),
                ),
                "leased": _scalar(
                    f"""
                    SELECT COUNT(*) FROM companies
                    WHERE COALESCE(is_dead, 0) = 0
                      AND lease_until IS NOT NULL
                      AND lease_until > {p}
                    """,
                    (now,),
                ),
                "dead_targets": _scalar("SELECT COUNT(*) FROM companies WHERE COALESCE(is_dead, 0) = 1"),
                "stale_hot_targets": _scalar(
                    f"""
                    SELECT COUNT(*) FROM companies
                    WHERE tier IN ('P0', 'P1')
                      AND COALESCE(is_dead, 0) = 0
                      AND (last_success_at IS NULL OR last_success_at < {p})
                    """,
                    (stale_hot_cutoff,),
                ),
            }
        except Exception:
            queue = {}

        return {
            "total_jobs": total,
            "active_jobs": active_count,
            "inactive_jobs": inactive,
            "unposted_jobs": unposted,
            "posted_jobs": posted,
            "companies": companies,
            "platforms": platforms,
            "quality_states": quality_states,
            "queue": queue,
            "jobs_last_24h": last_24h,
            "jobs_last_7d": last_7d,
        }
    finally:
        conn.close()


def get_scraper_runs(limit: int = 20) -> list[dict]:
    """Get recent scraper run logs from canonical scraper_runs table."""
    conn = get_db()
    p = _ph()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT
                id,
                scraper AS script_name,
                run_at AS timestamp,
                companies_scraped AS companies_fetched,
                new_jobs AS new_jobs_found,
                duration_seconds AS duration_s,
                errors,
                COALESCE(status, 'success') AS status,
                COALESCE(summary_json, '') AS summary_json
            FROM scraper_runs
            ORDER BY run_at DESC
            LIMIT {p}
            """,
            (limit,),
        )
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()
