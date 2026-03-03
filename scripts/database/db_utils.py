"""
JobClaw Database Layer — Dual Backend (SQLite + PostgreSQL).

Supports both SQLite (local dev) and PostgreSQL (production) via the
DATABASE_URL environment variable:
  - If DATABASE_URL is set → use asyncpg with connection pool
  - Otherwise → use sqlite3 (backward compatible)

Usage:
    from scripts.database.db_utils import get_connection, insert_job
    conn = get_connection()  # Works with both backends transparently

For async PostgreSQL:
    from scripts.database.db_utils import get_pg_pool
    pool = await get_pg_pool()
    async with pool.acquire() as conn:
        await conn.execute(...)
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "jobclaw.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "")


# ═══════════════════════════════════════════════════════════════════════
# BACKEND DETECTION
# ═══════════════════════════════════════════════════════════════════════

def is_postgres() -> bool:
    """Check if PostgreSQL backend is configured."""
    return DATABASE_URL.startswith("postgres")


# ═══════════════════════════════════════════════════════════════════════
# SQLITE BACKEND (default — backward compatible)
# ═══════════════════════════════════════════════════════════════════════

def get_connection():
    """Get a SQLite connection. Falls back to SQLite if no DATABASE_URL."""
    if is_postgres():
        # For sync code that needs a connection, create a psycopg2 connection
        try:
            import psycopg2
            conn = psycopg2.connect(DATABASE_URL)
            conn.autocommit = False
            return conn
        except ImportError:
            raise ImportError("psycopg2 required for PostgreSQL. Run: pip install psycopg2-binary")
    
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ═══════════════════════════════════════════════════════════════════════
# ASYNC POSTGRESQL BACKEND
# ═══════════════════════════════════════════════════════════════════════

_pg_pool = None

async def get_pg_pool():
    """Get or create an asyncpg connection pool.
    
    Pool sizes:
      - min: 5 connections (scrapers + API baseline)
      - max: 25 connections (burst capacity)
    """
    global _pg_pool
    if _pg_pool is None:
        try:
            import asyncpg
        except ImportError:
            raise ImportError("asyncpg required for PostgreSQL. Run: pip install asyncpg")
        
        _pg_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=5,
            max_size=25,
            command_timeout=30,
        )
    return _pg_pool


async def close_pg_pool():
    """Gracefully close the connection pool."""
    global _pg_pool
    if _pg_pool:
        await _pg_pool.close()
        _pg_pool = None


# ═══════════════════════════════════════════════════════════════════════
# CORE OPERATIONS — work with both backends
# ═══════════════════════════════════════════════════════════════════════

def _make_hash(job_dict: dict) -> str:
    """Create the dedup hash from job dict."""
    company_norm = job_dict.get("company", "Unknown").lower().strip()
    source_ats = job_dict.get("source_ats", "unknown").lower().strip()
    job_id_norm = str(job_dict.get("job_id", job_dict.get("url", ""))).lower().strip()
    return f"{source_ats}::{company_norm}::{job_id_norm}"


def insert_job(conn, job_dict: dict) -> bool:
    """
    Insert a job — works with both SQLite and PostgreSQL.
    Returns True if genuinely new (inserted), False if dedup hit.
    """
    internal_hash = _make_hash(job_dict)
    keywords = json.dumps(job_dict.get("keywords_matched", []))
    first_seen = datetime.now(timezone.utc).isoformat()

    if is_postgres():
        return _insert_job_pg(conn, job_dict, internal_hash, keywords, first_seen)
    else:
        return _insert_job_sqlite(conn, job_dict, internal_hash, keywords, first_seen)


def _insert_job_sqlite(conn, job_dict, internal_hash, keywords, first_seen) -> bool:
    """SQLite insert with IntegrityError-based dedup."""
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO jobs (
                internal_hash, job_id, title, company, location, url, 
                date_posted, source_ats, first_seen, status, keywords_matched,
                description, salary_min, salary_max, salary_currency,
                experience_years, is_active, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'unposted', ?, ?, ?, ?, ?, ?, 1, ?)
        """, (
            internal_hash,
            job_dict.get("job_id", ""),
            job_dict.get("title", ""),
            job_dict.get("company", ""),
            job_dict.get("location", ""),
            job_dict.get("url", ""),
            job_dict.get("date_posted", ""),
            job_dict.get("source_ats", ""),
            first_seen,
            keywords,
            job_dict.get("description"),
            job_dict.get("salary_min"),
            job_dict.get("salary_max"),
            job_dict.get("salary_currency"),
            job_dict.get("experience_years"),
            first_seen,
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        try:
            cursor.execute("""
                UPDATE jobs 
                SET last_seen_at = ?, is_active = 1 
                WHERE internal_hash = ?
            """, (first_seen, internal_hash))
            if job_dict.get("description"):
                cursor.execute("""
                    UPDATE jobs 
                    SET description = ?, salary_min = COALESCE(salary_min, ?),
                        salary_max = COALESCE(salary_max, ?),
                        salary_currency = COALESCE(salary_currency, ?),
                        experience_years = COALESCE(experience_years, ?)
                    WHERE internal_hash = ? AND (description IS NULL OR description = '')
                """, (
                    job_dict.get("description"),
                    job_dict.get("salary_min"),
                    job_dict.get("salary_max"),
                    job_dict.get("salary_currency"),
                    job_dict.get("experience_years"),
                    internal_hash,
                ))
            conn.commit()
        except Exception:
            pass
        return False


def _insert_job_pg(conn, job_dict, internal_hash, keywords, first_seen) -> bool:
    """PostgreSQL insert with ON CONFLICT upsert."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO jobs (
            internal_hash, job_id, title, company, location, url, 
            date_posted, source_ats, first_seen, status, keywords_matched,
            description, salary_min, salary_max, salary_currency,
            experience_years, is_active, last_seen_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'unposted', %s, %s, %s, %s, %s, %s, TRUE, %s)
        ON CONFLICT (internal_hash) DO UPDATE SET
            last_seen_at = EXCLUDED.last_seen_at,
            is_active = TRUE,
            description = COALESCE(NULLIF(jobs.description, ''), EXCLUDED.description),
            salary_min = COALESCE(jobs.salary_min, EXCLUDED.salary_min),
            salary_max = COALESCE(jobs.salary_max, EXCLUDED.salary_max),
            salary_currency = COALESCE(jobs.salary_currency, EXCLUDED.salary_currency),
            experience_years = COALESCE(jobs.experience_years, EXCLUDED.experience_years)
        RETURNING (xmax = 0) AS is_new
    """, (
        internal_hash,
        job_dict.get("job_id", ""),
        job_dict.get("title", ""),
        job_dict.get("company", ""),
        job_dict.get("location", ""),
        job_dict.get("url", ""),
        job_dict.get("date_posted", ""),
        job_dict.get("source_ats", ""),
        first_seen,
        keywords,
        job_dict.get("description"),
        job_dict.get("salary_min"),
        job_dict.get("salary_max"),
        job_dict.get("salary_currency"),
        job_dict.get("experience_years"),
        first_seen,
    ))
    result = cursor.fetchone()
    conn.commit()
    return result[0] if result else False


def mark_stale_jobs(conn, source_ats: str, company: str, active_job_ids: set[str]) -> int:
    """Mark jobs as inactive if not in the latest scrape."""
    if not active_job_ids:
        return 0
    
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.cursor()
    
    company_norm = company.lower().strip()
    ats_norm = source_ats.lower().strip()
    
    active_hashes = set()
    for jid in active_job_ids:
        jid_norm = str(jid).lower().strip()
        active_hashes.add(f"{ats_norm}::{company_norm}::{jid_norm}")
    
    placeholder = "%s" if is_postgres() else "?"
    
    cursor.execute(
        f"SELECT internal_hash FROM jobs WHERE source_ats = {placeholder} AND LOWER(company) = {placeholder} AND is_active = {'TRUE' if is_postgres() else '1'}",
        (ats_norm, company_norm)
    )
    all_hashes = {row[0] for row in cursor.fetchall()}
    stale_hashes = all_hashes - active_hashes
    
    if stale_hashes:
        qs = ",".join(placeholder for _ in stale_hashes)
        params = [now] + list(stale_hashes)
        cursor.execute(
            f"UPDATE jobs SET is_active = {'FALSE' if is_postgres() else '0'}, last_seen_at = {placeholder} WHERE internal_hash IN ({qs})",
            params
        )
        conn.commit()
    
    return len(stale_hashes)


def get_unposted_jobs(conn):
    """Fetch jobs ready to be sent to Discord."""
    if is_postgres():
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE status = 'unposted' ORDER BY first_seen ASC LIMIT 500")
        cols = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        jobs = []
        for row in rows:
            job = dict(zip(cols, row))
            if job.get("keywords_matched"):
                try:
                    job["keywords_matched"] = json.loads(job["keywords_matched"])
                except Exception:
                    job["keywords_matched"] = []
            jobs.append(job)
        return jobs
    else:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE status = 'unposted' ORDER BY first_seen ASC LIMIT 500")
        rows = cursor.fetchall()
        jobs = []
        for r in rows:
            job = dict(r)
            if job.get("keywords_matched"):
                try:
                    job["keywords_matched"] = json.loads(job["keywords_matched"])
                except Exception:
                    job["keywords_matched"] = []
            jobs.append(job)
        return jobs


def mark_jobs_posted(conn, internal_hashes: list[str]):
    """Update status to posted."""
    if not internal_hashes:
        return
    cursor = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"
    qs = ",".join(placeholder for _ in internal_hashes)
    cursor.execute(f"UPDATE jobs SET status = 'posted' WHERE internal_hash IN ({qs})", internal_hashes)
    conn.commit()


def log_scraper_run(conn, script_name: str, companies_fetched: int, new_jobs: int, duration: float, errors: str = None):
    """Log the performance metrics of a micro-scraper."""
    cursor = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"
    cursor.execute(f"""
        INSERT INTO runs (script_name, timestamp, companies_fetched, new_jobs_found, duration_s, errors)
        VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
    """, (
        script_name,
        datetime.now(timezone.utc).isoformat(),
        companies_fetched,
        new_jobs,
        duration,
        errors
    ))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════════
# ASYNC POSTGRESQL OPERATIONS
# ═══════════════════════════════════════════════════════════════════════

async def async_insert_job(pool, job_dict: dict) -> bool:
    """Async PostgreSQL job insert with upsert."""
    internal_hash = _make_hash(job_dict)
    keywords = json.dumps(job_dict.get("keywords_matched", []))
    first_seen = datetime.now(timezone.utc).isoformat()

    async with pool.acquire() as conn:
        result = await conn.fetchrow("""
            INSERT INTO jobs (
                internal_hash, job_id, title, company, location, url, 
                date_posted, source_ats, first_seen, status, keywords_matched,
                description, salary_min, salary_max, salary_currency,
                experience_years, is_active, last_seen_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'unposted', $10, $11, $12, $13, $14, $15, TRUE, $16)
            ON CONFLICT (internal_hash) DO UPDATE SET
                last_seen_at = EXCLUDED.last_seen_at,
                is_active = TRUE,
                description = COALESCE(NULLIF(jobs.description, ''), EXCLUDED.description),
                salary_min = COALESCE(jobs.salary_min, EXCLUDED.salary_min),
                salary_max = COALESCE(jobs.salary_max, EXCLUDED.salary_max)
            RETURNING (xmax = 0) AS is_new
        """,
            internal_hash,
            job_dict.get("job_id", ""),
            job_dict.get("title", ""),
            job_dict.get("company", ""),
            job_dict.get("location", ""),
            job_dict.get("url", ""),
            job_dict.get("date_posted", ""),
            job_dict.get("source_ats", ""),
            first_seen,
            keywords,
            job_dict.get("description"),
            float(job_dict["salary_min"]) if job_dict.get("salary_min") else None,
            float(job_dict["salary_max"]) if job_dict.get("salary_max") else None,
            job_dict.get("salary_currency"),
            int(job_dict["experience_years"]) if job_dict.get("experience_years") else None,
            first_seen,
        )
        return result["is_new"] if result else False


async def async_full_text_search(pool, query: str, limit: int = 50) -> list[dict]:
    """PostgreSQL full-text search with ranking."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT *, 
                   ts_rank(search_vector, websearch_to_tsquery('english', $1)) AS rank
            FROM jobs
            WHERE search_vector @@ websearch_to_tsquery('english', $1)
              AND is_active = TRUE
            ORDER BY rank DESC, first_seen DESC
            LIMIT $2
        """, query, limit)
        return [dict(row) for row in rows]
