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
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "jobclaw.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "")
HOT_COMPANIES_PATH = Path(__file__).parent.parent.parent / "config" / "hot_companies.json"

_hot_slugs_cache = None


def get_hot_slugs() -> set[str]:
    """Load and cache the list of hot company slugs."""
    global _hot_slugs_cache
    if _hot_slugs_cache is None:
        try:
            if HOT_COMPANIES_PATH.exists():
                data = json.loads(HOT_COMPANIES_PATH.read_text())
                if isinstance(data, dict) and "companies" in data:
                    _hot_slugs_cache = {c["slug"] for c in data["companies"] if "slug" in c}
                elif isinstance(data, list):
                    _hot_slugs_cache = {c["slug"] for c in data if "slug" in c}
                else:
                    _hot_slugs_cache = set()
            else:
                _hot_slugs_cache = set()
        except Exception:
            _hot_slugs_cache = set()
    return _hot_slugs_cache


def compute_quality_score(job_dict: dict) -> float:
    """Calculate a quality score (0-100) for a job listing."""
    from scripts.ingestion.role_filter import get_role_weight, matches_target_role

    score = 0.0
    hot_slugs = get_hot_slugs()

    # 1. Hot Company Bonus (+25)
    if job_dict.get("source_ats") in hot_slugs:
        score += 25

    # 2. Salary Transparency (+15)
    if job_dict.get("salary_min") and float(job_dict["salary_min"]) > 0:
        score += 15

    # 3. Freshness (bonus for being new)
    score += 10

    # 4. Description Depth (+8)
    desc = job_dict.get("description", "")
    if len(desc) > 500:
        score += 8
    elif len(desc) > 100:
        score += 4

    # 5. Semantic Weight (Phase 3)
    categories = job_dict.get("keywords_matched", [])
    if not categories:
        categories = matches_target_role(job_dict.get("title", ""))

    if categories:
        max_weight = max(get_role_weight(cat) for cat in categories)
        score += max_weight * 20  # Up to +20 for high-value roles

    # 6. Title Relevance
    title = job_dict.get("title", "")
    if len(title) > 100:
        score -= 10
    elif len(title) < 60:
        score += 5

    # 7. Seniority Filter
    title_lower = title.lower()
    if any(kw in title_lower for kw in ["director", "vp ", "vice president", "v.p.", "c-level", "chief"]):
        score -= 30

    return max(0.0, min(100.0, score))


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
    """Get a SQLite connection. Falls back to SQLite if no DATABASE_URL.

    Auto-initializes the schema (jobs + runs tables) on first access
    so GitHub Actions runners don't crash with 'no such table'.
    """
    if is_postgres():
        # For sync code that needs a connection, create a psycopg2 connection
        try:
            import psycopg2

            conn = psycopg2.connect(DATABASE_URL)
            conn.autocommit = False
            _ensure_postgres_schema(conn)
            return conn
        except ImportError as err:
            raise ImportError("psycopg2 required for PostgreSQL. Run: pip install psycopg2-binary") from err

    # Ensure the data directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")

    _ensure_sqlite_schema(conn)

    return conn


def _ensure_postgres_schema(conn):
    """Create core tables on Postgres if they don't exist."""
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id SERIAL PRIMARY KEY,
        internal_hash TEXT UNIQUE NOT NULL,
        job_id TEXT,
        title TEXT NOT NULL,
        company TEXT NOT NULL,
        location TEXT,
        url TEXT NOT NULL,
        date_posted TEXT,
        source_ats TEXT NOT NULL,
        first_seen TEXT NOT NULL DEFAULT now()::text,
        status TEXT DEFAULT 'unposted',
        keywords_matched TEXT,
        description TEXT,
        salary_min REAL,
        salary_max REAL,
        salary_currency TEXT,
        experience_years TEXT,
        remote_ok TEXT,
        job_type TEXT,
        seniority_level TEXT,
        visa_sponsorship INTEGER,
        tech_stack TEXT,
        is_active INTEGER DEFAULT 1,
        last_seen_at TEXT,
        discord_posted INTEGER DEFAULT 0,
        embedding_json TEXT,
        quality_score REAL DEFAULT 0
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pg_status ON jobs(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pg_first_seen ON jobs(first_seen)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pg_company ON jobs(company)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pg_source_ats ON jobs(source_ats)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pg_is_active ON jobs(is_active)")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        id SERIAL PRIMARY KEY,
        scraper TEXT NOT NULL,
        companies INTEGER DEFAULT 0,
        new_jobs INTEGER DEFAULT 0,
        duration_secs REAL DEFAULT 0,
        errors TEXT DEFAULT '',
        run_at TEXT DEFAULT now()::text
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scraper_runs (
        id SERIAL PRIMARY KEY,
        scraper TEXT NOT NULL,
        companies_scraped INTEGER DEFAULT 0,
        new_jobs INTEGER DEFAULT 0,
        duration_seconds REAL DEFAULT 0,
        errors TEXT DEFAULT '',
        run_at TEXT DEFAULT now()::text,
        shard_index INTEGER DEFAULT 0
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        id SERIAL PRIMARY KEY,
        slug TEXT UNIQUE NOT NULL,
        name TEXT,
        ats_type TEXT,
        tier TEXT DEFAULT 'P2',
        last_scraped_at TEXT,
        last_job_found_at TEXT
    )
    """)
    conn.commit()


def _ensure_sqlite_schema(conn):
    """Create core tables if they don't exist. Lightweight — safe to call multiple times."""
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        internal_hash TEXT UNIQUE NOT NULL,
        job_id TEXT,
        title TEXT NOT NULL,
        company TEXT NOT NULL,
        location TEXT,
        url TEXT NOT NULL,
        date_posted TEXT,
        source_ats TEXT NOT NULL,
        first_seen TEXT NOT NULL,
        status TEXT DEFAULT 'unposted',
        keywords_matched TEXT,
        description TEXT,
        salary_min REAL,
        salary_max REAL,
        salary_currency TEXT,
        experience_years INTEGER,
        remote_ok TEXT,
        job_type TEXT,
        seniority_level TEXT,
        visa_sponsorship INTEGER,
        tech_stack TEXT,
        is_active INTEGER DEFAULT 1,
        last_seen_at TEXT,
        quality_score REAL DEFAULT 0
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON jobs(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_first_seen ON jobs(first_seen)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_company ON jobs(company)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_ats ON jobs(source_ats)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_is_active ON jobs(is_active)")

    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN quality_score REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_quality ON jobs(quality_score)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scraper TEXT NOT NULL,
        companies INTEGER DEFAULT 0,
        new_jobs INTEGER DEFAULT 0,
        duration_secs REAL DEFAULT 0,
        errors TEXT DEFAULT '',
        run_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scraper_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scraper TEXT NOT NULL,
        companies_scraped INTEGER DEFAULT 0,
        new_jobs INTEGER DEFAULT 0,
        duration_seconds REAL DEFAULT 0,
        errors TEXT DEFAULT '',
        run_at TEXT DEFAULT CURRENT_TIMESTAMP,
        shard_index INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE NOT NULL,
        name TEXT,
        ats_type TEXT,
        tier TEXT DEFAULT 'P2',
        last_scraped_at TEXT,
        last_job_found_at TEXT
    )
    """)
    conn.commit()


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
        except ImportError as err:
            raise ImportError("asyncpg required for PostgreSQL. Run: pip install asyncpg") from err

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
        tech_stack_json = json.dumps(job_dict["tech_stack"]) if job_dict.get("tech_stack") else None
        cursor.execute(
            """
            INSERT INTO jobs (
                internal_hash, job_id, title, company, location, url,
                date_posted, source_ats, first_seen, status, keywords_matched,
                description, salary_min, salary_max, salary_currency,
                experience_years, remote_ok, job_type, seniority_level,
                visa_sponsorship, tech_stack, is_active, last_seen_at, quality_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'unposted', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
            (
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
                job_dict.get("remote_ok"),
                job_dict.get("job_type"),
                job_dict.get("seniority_level"),
                job_dict.get("visa_sponsorship"),
                tech_stack_json,
                first_seen,
                compute_quality_score(job_dict),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        try:
            cursor.execute(
                """
                UPDATE jobs
                SET last_seen_at = ?, is_active = 1, quality_score = ?
                WHERE internal_hash = ?
            """,
                (first_seen, compute_quality_score(job_dict), internal_hash),
            )
            if job_dict.get("description"):
                tech_stack_json = json.dumps(job_dict["tech_stack"]) if job_dict.get("tech_stack") else None
                cursor.execute(
                    """
                    UPDATE jobs
                    SET description = ?, salary_min = COALESCE(salary_min, ?),
                        salary_max = COALESCE(salary_max, ?),
                        salary_currency = COALESCE(salary_currency, ?),
                        experience_years = COALESCE(experience_years, ?),
                        remote_ok = COALESCE(remote_ok, ?),
                        job_type = COALESCE(job_type, ?),
                        seniority_level = COALESCE(seniority_level, ?),
                        visa_sponsorship = COALESCE(visa_sponsorship, ?),
                        tech_stack = COALESCE(tech_stack, ?)
                    WHERE internal_hash = ? AND (description IS NULL OR description = '')
                """,
                    (
                        job_dict.get("description"),
                        job_dict.get("salary_min"),
                        job_dict.get("salary_max"),
                        job_dict.get("salary_currency"),
                        job_dict.get("experience_years"),
                        job_dict.get("remote_ok"),
                        job_dict.get("job_type"),
                        job_dict.get("seniority_level"),
                        job_dict.get("visa_sponsorship"),
                        tech_stack_json,
                        internal_hash,
                    ),
                )
            conn.commit()
        except Exception:
            pass
        return False


def _insert_job_pg(conn, job_dict, internal_hash, keywords, first_seen) -> bool:
    """PostgreSQL insert with ON CONFLICT upsert."""
    try:
        cursor = conn.cursor()
        tech_stack_json = json.dumps(job_dict["tech_stack"]) if job_dict.get("tech_stack") else None
        cursor.execute(
            """
            INSERT INTO jobs (
                internal_hash, job_id, title, company, location, url,
                date_posted, source_ats, first_seen, status, keywords_matched,
                description, salary_min, salary_max, salary_currency,
                experience_years, remote_ok, job_type, seniority_level,
                visa_sponsorship, tech_stack, is_active, last_seen_at, quality_score
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'unposted', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)
            ON CONFLICT (internal_hash) DO UPDATE SET
                last_seen_at = EXCLUDED.last_seen_at,
                is_active = 1,
                quality_score = EXCLUDED.quality_score,
                description = COALESCE(NULLIF(jobs.description, ''), EXCLUDED.description),
                salary_min = COALESCE(jobs.salary_min, EXCLUDED.salary_min),
                salary_max = COALESCE(jobs.salary_max, EXCLUDED.salary_max),
                salary_currency = COALESCE(jobs.salary_currency, EXCLUDED.salary_currency),
                experience_years = COALESCE(jobs.experience_years, EXCLUDED.experience_years),
                remote_ok = COALESCE(jobs.remote_ok, EXCLUDED.remote_ok),
                job_type = COALESCE(jobs.job_type, EXCLUDED.job_type),
                seniority_level = COALESCE(jobs.seniority_level, EXCLUDED.seniority_level),
                visa_sponsorship = COALESCE(jobs.visa_sponsorship, EXCLUDED.visa_sponsorship),
                tech_stack = COALESCE(jobs.tech_stack, EXCLUDED.tech_stack)
            RETURNING (xmax = 0) AS is_new
        """,
            (
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
                job_dict.get("remote_ok"),
                job_dict.get("job_type"),
                job_dict.get("seniority_level"),
                1 if job_dict.get("visa_sponsorship") is True else (0 if job_dict.get("visa_sponsorship") is False else job_dict.get("visa_sponsorship")),
                tech_stack_json,
                first_seen,
                compute_quality_score(job_dict),
            ),
        )
        result = cursor.fetchone()
        conn.commit()
        return result[0] if result else False
    except Exception as e:
        conn.rollback()
        from scripts.utils.logger import _log
        _log(f"PG Insert Error ({job_dict.get('company')} - {job_dict.get('title')}): {e}", "ERROR")
        return False


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
        f"SELECT internal_hash FROM jobs WHERE source_ats = {placeholder} AND LOWER(company) = {placeholder} AND is_active = 1",
        (ats_norm, company_norm),
    )
    all_hashes = {row[0] for row in cursor.fetchall()}
    stale_hashes = all_hashes - active_hashes

    if stale_hashes:
        qs = ",".join(placeholder for _ in stale_hashes)
        params = [now] + list(stale_hashes)
        cursor.execute(
            f"UPDATE jobs SET is_active = 0, last_seen_at = {placeholder} WHERE internal_hash IN ({qs})",
            params,
        )
        conn.commit()

    return len(stale_hashes)


def get_unposted_jobs(conn):
    """Fetch jobs ready to be sent to Discord (last 48 hours only)."""
    if is_postgres():
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM jobs
               WHERE status = 'unposted'
                 AND (
                   (date_posted != '' AND date_posted::timestamptz >= NOW() - INTERVAL '48 hours')
                   OR (date_posted = '' AND first_seen >= NOW() - INTERVAL '48 hours')
                 )
               ORDER BY first_seen ASC
               LIMIT 500"""
        )
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
        cursor.execute(
            """SELECT * FROM jobs
               WHERE status = 'unposted'
                 AND (
                   (date_posted != '' AND date_posted >= datetime('now', '-48 hours'))
                   OR (date_posted = '' AND first_seen >= datetime('now', '-48 hours'))
                 )
               ORDER BY first_seen ASC
               LIMIT 500"""
        )
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


def purge_stale_unposted(conn) -> int:
    """Archive jobs that are too old to post (>48 hours unposted). Returns count archived."""
    cursor = conn.cursor()
    try:
        if is_postgres():
            cursor.execute(
                """UPDATE jobs SET status = 'archived'
                   WHERE status = 'unposted'
                   AND first_seen < NOW() - INTERVAL '48 hours'"""
            )
        else:
            cursor.execute(
                """UPDATE jobs SET status = 'archived'
                   WHERE status = 'unposted'
                   AND first_seen < datetime('now', '-48 hours')"""
            )
        count = cursor.rowcount
        conn.commit()
        return count
    except Exception as e:
        from scripts.utils.logger import _log

        _log(f"purge_stale_unposted failed: {e}", "WARNING")
        conn.rollback()
        return 0


def prune_scraper_runs(conn, keep_last_n: int = 500) -> int:
    """Delete old scraper_run records, keeping only the last N per scraper. Returns rows deleted."""
    cursor = conn.cursor()
    try:
        if is_postgres():
            cursor.execute(
                """DELETE FROM scraper_runs
                   WHERE id NOT IN (
                       SELECT id FROM (
                           SELECT id, ROW_NUMBER() OVER (PARTITION BY scraper ORDER BY id DESC) as rn
                           FROM scraper_runs
                       ) ranked
                       WHERE rn <= %s
                   )""",
                (keep_last_n,),
            )
        else:
            cursor.execute(
                """DELETE FROM scraper_runs
                   WHERE id NOT IN (
                       SELECT id FROM (
                           SELECT id, ROW_NUMBER() OVER (PARTITION BY scraper ORDER BY id DESC) as rn
                           FROM scraper_runs
                       ) ranked
                       WHERE rn <= ?
                   )""",
                (keep_last_n,),
            )
        count = cursor.rowcount
        conn.commit()
        return count
    except Exception as e:
        from scripts.utils.logger import _log

        _log(f"prune_scraper_runs failed: {e}", "WARNING")
        return 0


def mark_jobs_posted(conn, internal_hashes: list[str]):
    """Update status to posted."""
    if not internal_hashes:
        return
    cursor = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"
    qs = ",".join(placeholder for _ in internal_hashes)
    cursor.execute(f"UPDATE jobs SET status = 'posted' WHERE internal_hash IN ({qs})", internal_hashes)
    conn.commit()


def get_next_shard_from_db(conn, scraper_name: str, total_shards: int = 4) -> int:
    """Read shard from DB to ensure rotation persists even in ephemeral runners."""
    cursor = conn.cursor()
    try:
        placeholder = "%s" if is_postgres() else "?"
        cursor.execute(f"SELECT COUNT(*) FROM scraper_runs WHERE scraper = {placeholder}", (scraper_name,))
        row = cursor.fetchone()
        run_count = row[0] if row else 0
        return run_count % total_shards
    except Exception:
        return 0


def get_companies_by_tier(conn, tier: str, shard: int = None, total_shards: int = 4) -> list[dict]:
    """Fetch companies of a specific tier, optionally sharded for rotation.

    Includes TTL Backoff: P1/P2 companies with 0 jobs found in last 30 days are skipped
    to save request volume for more active targets.
    """
    cursor = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"

    now = datetime.now(timezone.utc)
    thirty_days_ago = (now - timedelta(days=30)).isoformat()

    # Base query
    query = f"SELECT * FROM companies WHERE tier = {placeholder}"
    params = [tier]

    # TTL Backoff for non-P0 tiers
    if tier != "P0":
        query += f" AND (last_job_found_at IS NULL OR last_job_found_at >= {placeholder})"
        params.append(thirty_days_ago)

    cursor.execute(query, params)

    if is_postgres():
        cols = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        all_companies = [dict(zip(cols, row)) for row in rows]
    else:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        all_companies = [dict(r) for r in rows]

    if shard is not None and all_companies:
        # Client-side sharding for simplicity, or we could do it in SQL
        all_companies.sort(key=lambda x: x["slug"])
        chunk_size = len(all_companies) // total_shards
        remainder = len(all_companies) % total_shards
        start_idx = shard * chunk_size + min(shard, remainder)
        end_idx = start_idx + chunk_size + (1 if shard < remainder else 0)
        return all_companies[start_idx:end_idx]

    return all_companies


def update_company_last_scraped(conn, slug: str, job_found: bool = False):
    """Update metadata for TTL backoff logic.

    Dynamic Tier Promotion: If a P2 company posts a job, promote it to P1 for
    more frequent monitoring in subsequent runs.
    """
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    placeholder = "%s" if is_postgres() else "?"

    if job_found:
        # Dynamic Promotion P2 -> P1
        cursor.execute(
            f"UPDATE companies SET last_scraped_at = {placeholder}, last_job_found_at = {placeholder}, tier = CASE WHEN tier = 'P2' THEN 'P1' ELSE tier END WHERE slug = {placeholder}",
            (now, now, slug),
        )
    else:
        cursor.execute(f"UPDATE companies SET last_scraped_at = {placeholder} WHERE slug = {placeholder}", (now, slug))
    conn.commit()


def log_scraper_run(
    conn,
    script_name: str,
    companies_scraped: int,
    new_jobs: int,
    duration: float,
    errors: str = None,
    shard_index: int = 0,
):
    """Log the performance metrics of a scraper run, including shard index."""
    cursor = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"
    cursor.execute(
        f"""
        INSERT INTO scraper_runs (scraper, companies_scraped, new_jobs, duration_seconds, errors, run_at, shard_index)
        VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
    """,
        (
            script_name,
            companies_scraped,
            new_jobs,
            duration,
            errors or "",
            datetime.now(timezone.utc).isoformat(),
            shard_index,
        ),
    )
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
        tech_stack_json = json.dumps(job_dict["tech_stack"]) if job_dict.get("tech_stack") else None
        result = await conn.fetchrow(
            """
            INSERT INTO jobs (
                internal_hash, job_id, title, company, location, url,
                date_posted, source_ats, first_seen, status, keywords_matched,
                description, salary_min, salary_max, salary_currency,
                experience_years, remote_ok, job_type, seniority_level,
                visa_sponsorship, tech_stack, is_active, last_seen_at, quality_score
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'unposted', $10,
                      $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, TRUE, $21, $22)
            ON CONFLICT (internal_hash) DO UPDATE SET
                last_seen_at = EXCLUDED.last_seen_at,
                is_active = TRUE,
                quality_score = EXCLUDED.quality_score,
                description = COALESCE(NULLIF(jobs.description, ''), EXCLUDED.description),
                salary_min = COALESCE(jobs.salary_min, EXCLUDED.salary_min),
                salary_max = COALESCE(jobs.salary_max, EXCLUDED.salary_max),
                remote_ok = COALESCE(jobs.remote_ok, EXCLUDED.remote_ok),
                job_type = COALESCE(jobs.job_type, EXCLUDED.job_type),
                seniority_level = COALESCE(jobs.seniority_level, EXCLUDED.seniority_level),
                visa_sponsorship = COALESCE(jobs.visa_sponsorship, EXCLUDED.visa_sponsorship),
                tech_stack = COALESCE(jobs.tech_stack, EXCLUDED.tech_stack)
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
            job_dict.get("remote_ok"),
            job_dict.get("job_type"),
            job_dict.get("seniority_level"),
            job_dict.get("visa_sponsorship"),
            tech_stack_json,
            first_seen,
            compute_quality_score(job_dict),
        )
        return result["is_new"] if result else False


async def async_full_text_search(pool, query: str, limit: int = 50) -> list[dict]:
    """PostgreSQL full-text search with ranking."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *,
                   ts_rank(search_vector, websearch_to_tsquery('english', $1)) AS rank
            FROM jobs
            WHERE search_vector @@ websearch_to_tsquery('english', $1)
              AND is_active = TRUE
            ORDER BY rank DESC, first_seen DESC
            LIMIT $2
        """,
            query,
            limit,
        )
        return [dict(row) for row in rows]
