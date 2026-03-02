"""
Database query layer for the JobClaw API.

Thin wrapper around SQLite that returns raw dicts for the API routes.
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "jobclaw.db"


def get_db():
    """Get a SQLite connection with Row factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a dict with parsed keywords."""
    d = dict(row)
    if d.get("keywords_matched"):
        try:
            d["keywords_matched"] = json.loads(d["keywords_matched"])
        except (json.JSONDecodeError, TypeError):
            d["keywords_matched"] = []
    else:
        d["keywords_matched"] = []
    # Ensure is_active is bool
    d["is_active"] = bool(d.get("is_active", 1))
    return d


def get_jobs(
    page: int = 1,
    per_page: int = 50,
    company: str = None,
    ats: str = None,
    keyword: str = None,
    active_only: bool = True,
    search: str = None,
) -> tuple[list[dict], int]:
    """
    Query jobs with pagination and filters.
    Returns (jobs, total_count).
    """
    conn = get_db()
    try:
        conditions = []
        params = []

        if active_only:
            conditions.append("is_active = 1")
        if company:
            conditions.append("LOWER(company) = LOWER(?)")
            params.append(company)
        if ats:
            conditions.append("LOWER(source_ats) = LOWER(?)")
            params.append(ats)
        if keyword:
            conditions.append("keywords_matched LIKE ?")
            params.append(f"%{keyword}%")
        if search:
            conditions.append("(title LIKE ? OR company LIKE ? OR description LIKE ?)")
            params.extend([f"%{search}%"] * 3)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # Count
        count_sql = f"SELECT COUNT(*) FROM jobs {where}"
        total = conn.execute(count_sql, params).fetchone()[0]

        # Paginated results
        offset = (page - 1) * per_page
        query = f"""
            SELECT * FROM jobs {where}
            ORDER BY first_seen DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query, params + [per_page, offset]).fetchall()
        return [_row_to_dict(r) for r in rows], total
    finally:
        conn.close()


def get_job_by_hash(internal_hash: str) -> dict | None:
    """Get a single job by its internal hash."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM jobs WHERE internal_hash = ?", (internal_hash,)
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_companies(ats: str = None) -> list[dict]:
    """Get companies with job counts."""
    conn = get_db()
    try:
        if ats:
            rows = conn.execute("""
                SELECT company, source_ats, COUNT(*) as job_count,
                       MAX(first_seen) as latest_job
                FROM jobs WHERE LOWER(source_ats) = LOWER(?) AND is_active = 1
                GROUP BY company, source_ats
                ORDER BY job_count DESC
            """, (ats,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT company, source_ats, COUNT(*) as job_count,
                       MAX(first_seen) as latest_job
                FROM jobs WHERE is_active = 1
                GROUP BY company, source_ats
                ORDER BY job_count DESC
            """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_stats() -> dict:
    """Get system-wide statistics."""
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM jobs WHERE is_active = 1").fetchone()[0]
        inactive = total - active
        unposted = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'unposted'").fetchone()[0]
        posted = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'posted'").fetchone()[0]

        companies = conn.execute(
            "SELECT COUNT(DISTINCT company) FROM jobs WHERE is_active = 1"
        ).fetchone()[0]

        # Platform breakdown
        rows = conn.execute(
            "SELECT source_ats, COUNT(*) as cnt FROM jobs WHERE is_active = 1 GROUP BY source_ats"
        ).fetchall()
        platforms = {r["source_ats"]: r["cnt"] for r in rows}

        # Recent counts
        last_24h = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE first_seen >= datetime('now', '-1 day')"
        ).fetchone()[0]
        last_7d = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE first_seen >= datetime('now', '-7 days')"
        ).fetchone()[0]

        return {
            "total_jobs": total,
            "active_jobs": active,
            "inactive_jobs": inactive,
            "unposted_jobs": unposted,
            "posted_jobs": posted,
            "companies": companies,
            "platforms": platforms,
            "jobs_last_24h": last_24h,
            "jobs_last_7d": last_7d,
        }
    finally:
        conn.close()


def get_scraper_runs(limit: int = 20) -> list[dict]:
    """Get recent scraper run logs."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT rowid as id, * FROM runs ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
