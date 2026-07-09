"""
Database query layer for the JobClaw API.

Supports both SQLite (default) and PostgreSQL (via DATABASE_URL).
Provides read-only query functions for the REST API.
"""

import json
import os
import sqlite3
from collections.abc import Mapping, Sequence
from decimal import Decimal
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "jobclaw.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "")
DATABASE_URL_PLACEHOLDER_HINTS = (
    "user:password@",
    "ep-xxx.",
    "your-postgres",
    "localhost:5432/jobclaw",
)
_COLUMN_CACHE: dict[tuple[str, str], set[str]] = {}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _is_pg() -> bool:
    return DATABASE_URL.startswith("postgres")


def validate_database_url() -> None:
    """Fail fast when production is configured with an example database URL."""
    if not DATABASE_URL:
        return

    if any(hint in DATABASE_URL for hint in DATABASE_URL_PLACEHOLDER_HINTS):
        raise RuntimeError(
            "DATABASE_URL is still using a placeholder value. "
            "Set it to the real Railway Postgres or Neon connection string, "
            "for example the Railway Postgres DATABASE_URL reference."
        )


def get_db():
    """Get a database connection (SQLite or PostgreSQL)."""
    validate_database_url()

    if _is_pg():
        import psycopg2
        import psycopg2.extras

        statement_timeout_ms = max(1000, _env_int("JOBCLAW_PG_STATEMENT_TIMEOUT_MS", 15000))
        return psycopg2.connect(
            DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=max(1, _env_int("JOBCLAW_PG_CONNECT_TIMEOUT", 10)),
            options=f"-c statement_timeout={statement_timeout_ms}",
        )

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_mapping(row) -> dict:
    """Convert sqlite/psycopg rows into a plain dict."""
    if row is None:
        return {}
    return dict(row)


def _first_value(row, default=0):
    """Read the first selected value from sqlite rows or psycopg dict rows."""
    if row is None:
        return default
    if isinstance(row, Mapping):
        return next(iter(row.values()), default)
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray)):
        return row[0] if row else default
    try:
        return row[0]
    except Exception:
        return default


def _json_safe(value):
    """Normalize DB-native values before Pydantic/JSON serialization."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _row_to_dict(row) -> dict:
    """Convert a row to a dict with parsed keywords and JSON-safe values."""
    d = {key: _json_safe(value) for key, value in _row_to_mapping(row).items()}
    if d.get("keywords_matched"):
        if isinstance(d["keywords_matched"], str):
            try:
                d["keywords_matched"] = json.loads(d["keywords_matched"])
            except (json.JSONDecodeError, TypeError):
                d["keywords_matched"] = []
        elif not isinstance(d["keywords_matched"], list):
            d["keywords_matched"] = []
    else:
        d["keywords_matched"] = []
    d["is_active"] = bool(d.get("is_active", True))
    return d


def _ph() -> str:
    """Placeholder character for the current backend."""
    return "%s" if _is_pg() else "?"


def _table_columns(conn, table: str) -> set[str]:
    """Return known columns for a table, cached per backend.

    Production databases can lag behind the latest application schema. Public
    read endpoints should degrade with defaults for optional columns instead of
    failing the whole jobs board with a 500.
    """
    backend = "pg" if _is_pg() else "sqlite"
    cache_key = (backend, table)
    if cache_key in _COLUMN_CACHE:
        return _COLUMN_CACHE[cache_key]

    cursor = conn.cursor()
    if _is_pg():
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table,),
        )
        columns = {str(_row_to_mapping(row).get("column_name")) for row in cursor.fetchall()}
    else:
        cursor.execute(f"PRAGMA table_info({table})")
        columns = {str(_row_to_mapping(row).get("name")) for row in cursor.fetchall()}

    _COLUMN_CACHE[cache_key] = columns
    return columns


def _select_or_default(columns: set[str], column: str, default_sql: str) -> str:
    return column if column in columns else f"{default_sql} AS {column}"


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
    include_description: bool = False,
) -> tuple[list[dict], int]:
    """Query jobs with pagination and filters."""
    conn = get_db()
    p = _ph()
    try:
        columns = _table_columns(conn, "jobs")
        conditions = []
        params = []

        if active_only and "is_active" in columns:
            conditions.append("is_active = TRUE" if _is_pg() else "is_active = 1")
        if company and "company" in columns:
            conditions.append(f"LOWER(company) = LOWER({p})")
            params.append(company)
        if ats and "source_ats" in columns:
            conditions.append(f"LOWER(source_ats) = LOWER({p})")
            params.append(ats)
        if keyword and "keywords_matched" in columns:
            conditions.append(f"keywords_matched LIKE {p}")
            params.append(f"%{keyword}%")
        if search:
            if _is_pg() and "search_vector" in columns:
                conditions.append(f"search_vector @@ websearch_to_tsquery('english', {p})")
                params.append(search)
            else:
                searchable = [column for column in ("title", "company", "description") if column in columns]
                if searchable:
                    operator = "ILIKE" if _is_pg() else "LIKE"
                    conditions.append("(" + " OR ".join(f"{column} {operator} {p}" for column in searchable) + ")")
                    params.extend([f"%{search}%"] * len(searchable))
        if recent_hours and ("first_seen" in columns or "date_posted" in columns):
            date_column = "first_seen" if "first_seen" in columns else "date_posted"
            if _is_pg():
                cutoff = datetime.now(timezone.utc) - timedelta(hours=recent_hours)
                conditions.append(f"{date_column} >= {p}")
                params.append(cutoff.isoformat())
            else:
                conditions.append(f"datetime({date_column}) >= datetime('now', {p})")
                params.append(f"-{recent_hours} hours")
        if quality and "quality_state" in columns:
            conditions.append(f"COALESCE(quality_state, 'needs_review') = {p}")
            params.append(quality)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM jobs {where}", params)
        row = cursor.fetchone()
        total = _first_value(row, 0)

        offset = (page - 1) * per_page

        # Safe ORDER BY — choose between two pre-defined static strings only.
        # Never interpolate user input into ORDER BY.
        if _is_pg() and search and "search_vector" in columns:
            order_clause = "ts_rank(search_vector, websearch_to_tsquery('english', %s)) DESC, first_seen DESC"
            extra_params = [search]
        else:
            order_column = "first_seen" if "first_seen" in columns else ("date_posted" if "date_posted" in columns else "internal_hash")
            order_clause = f"{order_column} DESC"
            extra_params = []

        # Job descriptions are the heaviest column in this table. Public list
        # views do not need them, so keep /jobs lean by default and reserve full
        # descriptions for /jobs/{internal_hash} or explicit callers.
        description_column = "description" if include_description and "description" in columns else "NULL AS description"
        active_default = "TRUE" if _is_pg() else "1"
        select_columns = ", ".join(
            [
                _select_or_default(columns, "internal_hash", "''"),
                _select_or_default(columns, "job_id", "''"),
                _select_or_default(columns, "title", "'Untitled Role'"),
                _select_or_default(columns, "company", "'Unknown Company'"),
                _select_or_default(columns, "location", "''"),
                _select_or_default(columns, "url", "''"),
                _select_or_default(columns, "date_posted", "''"),
                _select_or_default(columns, "source_ats", "'direct'"),
                _select_or_default(columns, "first_seen", "NULL"),
                _select_or_default(columns, "status", "'posted'"),
                _select_or_default(columns, "keywords_matched", "'[]'"),
                description_column,
                _select_or_default(columns, "salary_min", "NULL"),
                _select_or_default(columns, "salary_max", "NULL"),
                _select_or_default(columns, "salary_currency", "NULL"),
                _select_or_default(columns, "experience_years", "NULL"),
                _select_or_default(columns, "is_active", active_default),
                _select_or_default(columns, "last_seen_at", "NULL"),
                _select_or_default(columns, "quality_state", "NULL"),
                _select_or_default(columns, "quality_reasons", "NULL"),
                _select_or_default(columns, "canonical_company", "NULL"),
                _select_or_default(columns, "canonical_title", "NULL"),
                _select_or_default(columns, "source_confidence", "NULL"),
            ]
        )

        query = f"""
            SELECT {select_columns} FROM jobs {where}
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
    try:
        columns = _table_columns(conn, "jobs")
        if not {"company", "source_ats"}.issubset(columns):
            return []
        active_where = ""
        if "is_active" in columns:
            active = "TRUE" if _is_pg() else "1"
            active_where = f" AND is_active = {active}"
        latest_expr = "MAX(first_seen)" if "first_seen" in columns else ("MAX(date_posted)" if "date_posted" in columns else "NULL")
        cursor = conn.cursor()
        if ats:
            cursor.execute(
                f"""
                SELECT company, source_ats, COUNT(*) as job_count,
                       {latest_expr} as latest_job
                FROM jobs WHERE LOWER(source_ats) = LOWER({p}){active_where}
                GROUP BY company, source_ats
                ORDER BY job_count DESC
            """,
                (ats,),
            )
        else:
            cursor.execute(f"""
                SELECT company, source_ats, COUNT(*) as job_count,
                       {latest_expr} as latest_job
                FROM jobs WHERE 1 = 1{active_where}
                GROUP BY company, source_ats
                ORDER BY job_count DESC
            """)
        return [_row_to_dict(r) for r in cursor.fetchall()]
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
            return _first_value(row, 0)

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
            quality_states = {
                str(_row_to_mapping(r).get("state") or "needs_review"): int(_row_to_mapping(r).get("cnt") or 0)
                for r in cursor.fetchall()
            }
        except Exception:
            quality_states = {}

        # Platform breakdown
        cursor.execute(f"SELECT source_ats, COUNT(*) as cnt FROM jobs WHERE is_active = {active} GROUP BY source_ats")
        rows = cursor.fetchall()
        platforms = {}
        for r in rows:
            d = _row_to_mapping(r)
            platforms[str(d.get("source_ats") or "unknown")] = int(d.get("cnt") or 0)

        # Recent counts
        if _is_pg():
            last_24h = _scalar("SELECT COUNT(*) FROM jobs WHERE first_seen::timestamptz >= NOW() - INTERVAL '1 day'")
            last_7d = _scalar("SELECT COUNT(*) FROM jobs WHERE first_seen::timestamptz >= NOW() - INTERVAL '7 days'")
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


def get_platform_health(runs_limit: int = 25) -> dict:
    """Aggregate recent ATS run summaries into per-platform success/error rates.

    Powers the /stats/health endpoint and the public status page — the
    'is Workday actually working, or silently rate-limited?' readout.
    """
    from scripts.ops.platform_health import aggregate_platform_health

    conn = get_db()
    p = _ph()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT COALESCE(summary_json, '') AS summary_json
            FROM scraper_runs
            WHERE scraper = {p} AND summary_json IS NOT NULL AND summary_json <> ''
            ORDER BY run_at DESC
            LIMIT {p}
            """,
            ("scrape_ats", runs_limit),
        )
        summaries = [_row_to_mapping(r).get("summary_json") for r in cursor.fetchall()]
    finally:
        conn.close()
    return aggregate_platform_health(summaries)


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
        return [_row_to_dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()
