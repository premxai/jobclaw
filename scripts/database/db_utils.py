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
import re
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

DB_PATH = Path(__file__).parent.parent.parent / "data" / "jobclaw.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "")
HOT_COMPANIES_PATH = Path(__file__).parent.parent.parent / "config" / "hot_companies.json"

_hot_slugs_cache = None

TIER_INTERVALS = {
    "P0": timedelta(minutes=15),
    "P1": timedelta(hours=1),
    "P2": timedelta(hours=24),
    "P3": timedelta(days=7),
}

DEFAULT_TIER = "P2"
PG_CONNECT_TIMEOUT = int(os.getenv("JOBCLAW_PG_CONNECT_TIMEOUT", "15"))
PG_CONNECT_RETRIES = int(os.getenv("JOBCLAW_PG_CONNECT_RETRIES", "3"))
DIRECT_ATS_SOURCES = {
    "greenhouse",
    "lever",
    "ashby",
    "workday",
    "workable",
    "rippling",
    "smartrecruiters",
    "bamboohr",
    "icims",
}
_BLOCKED_JOB_URL_TOKENS = (
    "/salary",
    "/salaries",
    "/jobs-in-",
    "/browse",
    "/search",
    "q=",
    "query=",
    "keyword=",
)
_GENERIC_JOB_TITLE_RE = re.compile(
    r"\b(\d[\d,]*\+?\s+.+jobs\s+hiring|salary in|jobs hiring now|job search|career salary)\b",
    re.I,
)


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
    desc = job_dict.get("description") or ""
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
    title = job_dict.get("title") or ""
    if len(title) > 100:
        score -= 10
    elif len(title) < 60:
        score += 5

    # 7. Seniority Filter
    title_lower = title.lower()
    if any(kw in title_lower for kw in ["director", "vp ", "vice president", "v.p.", "c-level", "chief"]):
        score -= 30

    return max(0.0, min(100.0, score))


def classify_job_quality(job_dict: dict) -> tuple[str, list[str], str, str, float]:
    """Classify whether a job is safe for public surfaces."""
    title = str(job_dict.get("title") or "").strip()
    company = str(job_dict.get("company") or "").strip()
    url = str(job_dict.get("url") or "").strip()
    source = str(job_dict.get("source_ats") or "").strip().lower()
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    haystack_url = f"{parsed.path}?{parsed.query}".lower()
    reasons: list[str] = []

    if source not in DIRECT_ATS_SOURCES:
        reasons.append("non_direct_source")
    if not parsed.scheme or not parsed.netloc:
        reasons.append("invalid_apply_url")
    if any(token in haystack_url for token in _BLOCKED_JOB_URL_TOKENS):
        reasons.append("non_job_url")
    if host.endswith(("indeed.com", "careerbuilder.com", "ziprecruiter.com")):
        reasons.append("aggregator_host")
    if not title or len(title) < 4 or _GENERIC_JOB_TITLE_RE.search(title):
        reasons.append("generic_title")
    if not company or company.lower() in {"unknown", "n/a", "none"}:
        reasons.append("unknown_company")
    if "@" in company and title.lower() in company.lower():
        reasons.append("malformed_company_title")

    reason_set = set(reasons)
    confidence = 1.0
    if "non_direct_source" in reason_set:
        confidence -= 0.45
    if {"invalid_apply_url", "non_job_url", "aggregator_host"} & reason_set:
        confidence -= 0.35
    if {"generic_title", "unknown_company", "malformed_company_title"} & reason_set:
        confidence -= 0.25
    confidence = max(0.0, round(confidence, 2))

    if not reasons:
        state = "accepted"
    elif {"invalid_apply_url", "non_job_url", "aggregator_host", "generic_title"} & reason_set:
        state = "rejected"
    else:
        state = "needs_review"

    return state, reasons, company, title, confidence


# ═══════════════════════════════════════════════════════════════════════
# BACKEND DETECTION
# ═══════════════════════════════════════════════════════════════════════


def is_postgres() -> bool:
    """Check if PostgreSQL backend is configured."""
    return DATABASE_URL.startswith("postgres")


# ═══════════════════════════════════════════════════════════════════════
# SQLITE BACKEND (default — backward compatible)
# ═══════════════════════════════════════════════════════════════════════


_schema_initialized = False
_POSTGRES_SCHEMA_LOCK_ID = 839201742


def get_connection():
    """Get a SQLite connection. Falls back to SQLite if no DATABASE_URL.

    Auto-initializes the schema (jobs + runs tables) on first access
    so GitHub Actions runners don't crash with 'no such table'.
    """
    global _schema_initialized
    if is_postgres():
        # For sync code that needs a connection, create a psycopg2 connection
        try:
            import psycopg2

            last_error = None
            for attempt in range(1, PG_CONNECT_RETRIES + 1):
                try:
                    conn = psycopg2.connect(DATABASE_URL, connect_timeout=PG_CONNECT_TIMEOUT)
                    break
                except psycopg2.OperationalError as err:
                    last_error = err
                    if attempt >= PG_CONNECT_RETRIES:
                        raise
                    time.sleep(min(2 * attempt, 6))
            else:
                raise last_error
            conn.autocommit = False
            if not _schema_initialized:
                try:
                    _ensure_postgres_schema(conn)
                except Exception:
                    conn.rollback()
                    conn.close()
                    raise
                _schema_initialized = True
            return conn
        except ImportError as err:
            raise ImportError("psycopg2 required for PostgreSQL. Run: pip install psycopg2-binary") from err

    # Ensure the data directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")

    if not _schema_initialized:
        _ensure_sqlite_schema(conn)
        _schema_initialized = True

    return conn


def _ensure_postgres_schema(conn):
    """Create core tables on Postgres if they don't exist."""
    cursor = conn.cursor()
    cursor.execute("SELECT pg_advisory_xact_lock(%s)", (_POSTGRES_SCHEMA_LOCK_ID,))
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
        is_active BOOLEAN DEFAULT TRUE,
        last_seen_at TEXT,
        discord_posted BOOLEAN DEFAULT FALSE,
        embedding_json TEXT,
        quality_score REAL DEFAULT 0,
        quality_state TEXT DEFAULT 'needs_review',
        quality_reasons TEXT DEFAULT '[]',
        canonical_company TEXT DEFAULT '',
        canonical_title TEXT DEFAULT '',
        source_confidence REAL DEFAULT 0
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pg_status ON jobs(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pg_first_seen ON jobs(first_seen)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pg_company ON jobs(company)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pg_source_ats ON jobs(source_ats)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pg_is_active ON jobs(is_active)")
    for col_def in [
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS quality_state TEXT DEFAULT 'needs_review'",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS quality_reasons TEXT DEFAULT '[]'",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS canonical_company TEXT DEFAULT ''",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS canonical_title TEXT DEFAULT ''",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS source_confidence REAL DEFAULT 0",
    ]:
        cursor.execute(col_def)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_quality_state ON jobs(quality_state)")
    cursor.execute("""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'jobs'
              AND column_name = 'is_active'
              AND data_type <> 'boolean'
        ) THEN
            ALTER TABLE jobs ALTER COLUMN is_active DROP DEFAULT;
            ALTER TABLE jobs
            ALTER COLUMN is_active TYPE BOOLEAN
            USING CASE
                WHEN is_active::text IN ('1', 'true', 't', 'yes') THEN TRUE
                ELSE FALSE
            END;
            ALTER TABLE jobs ALTER COLUMN is_active SET DEFAULT TRUE;
        END IF;
    END $$;
    """)
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
        shard_index INTEGER DEFAULT 0,
        status TEXT DEFAULT 'success',
        summary_json TEXT DEFAULT ''
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        id SERIAL PRIMARY KEY,
        slug TEXT NOT NULL,
        name TEXT,
        ats_type TEXT,
        tier TEXT DEFAULT 'P2',
        last_scraped_at TEXT,
        last_job_found_at TEXT,
        consecutive_failures INTEGER DEFAULT 0,
        is_dead INTEGER DEFAULT 0,
        validation_status TEXT DEFAULT 'unknown',
        validation_error TEXT DEFAULT '',
        validation_checked_at TEXT,
        validation_failure_category TEXT DEFAULT '',
        validation_http_status INTEGER,
        validated_metadata TEXT DEFAULT '',
        last_failure_category TEXT DEFAULT '',
        last_failure_at TEXT,
        last_success_at TEXT,
        next_due_at TEXT,
        lease_until TEXT,
        lease_owner TEXT DEFAULT '',
        last_attempt_at TEXT,
        health_state TEXT DEFAULT 'unknown',
        scrape_score REAL DEFAULT 0,
        avg_duration_ms REAL DEFAULT 0,
        yield_rate REAL DEFAULT 0,
        fresh_job_rate REAL DEFAULT 0,
        platform_budget_key TEXT DEFAULT '',
        source_count INTEGER DEFAULT 1,
        priority_score REAL DEFAULT 0,
        next_scrape_at TEXT,
        total_scrapes INTEGER DEFAULT 0,
        total_jobs_found INTEGER DEFAULT 0,
        total_relevant_jobs_found INTEGER DEFAULT 0,
        avg_jobs_found REAL DEFAULT 0
    )
    """)
    cursor.execute("ALTER TABLE companies DROP CONSTRAINT IF EXISTS companies_slug_key")
    cursor.execute("""
    DELETE FROM companies a
    USING companies b
    WHERE a.id > b.id
      AND a.ats_type = b.ats_type
      AND a.slug = b.slug
    """)
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_ats_slug ON companies (ats_type, slug)")
    # Migrate existing tables — ADD COLUMN IF NOT EXISTS is safe to run repeatedly
    for col_def in [
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS is_dead INTEGER DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS validation_status TEXT DEFAULT 'unknown'",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS validation_error TEXT DEFAULT ''",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS validation_checked_at TEXT",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS validation_failure_category TEXT DEFAULT ''",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS validation_http_status INTEGER",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS validated_metadata TEXT DEFAULT ''",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS last_failure_category TEXT DEFAULT ''",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS last_failure_at TEXT",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS last_success_at TEXT",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS next_due_at TEXT",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS lease_until TEXT",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS lease_owner TEXT DEFAULT ''",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS last_attempt_at TEXT",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS health_state TEXT DEFAULT 'unknown'",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS scrape_score REAL DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS avg_duration_ms REAL DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS yield_rate REAL DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS fresh_job_rate REAL DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS platform_budget_key TEXT DEFAULT ''",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS source_count INTEGER DEFAULT 1",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS priority_score REAL DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS next_scrape_at TEXT",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS total_scrapes INTEGER DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS total_jobs_found INTEGER DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS total_relevant_jobs_found INTEGER DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS avg_jobs_found REAL DEFAULT 0",
    ]:
        cursor.execute(col_def)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_next_scrape ON companies (is_dead, next_scrape_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_priority ON companies (priority_score DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_lease ON companies (lease_until)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_companies_queue ON companies (is_dead, health_state, next_due_at, scrape_score DESC)"
    )
    for col_def in [
        "ALTER TABLE scraper_runs ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'success'",
        "ALTER TABLE scraper_runs ADD COLUMN IF NOT EXISTS summary_json TEXT DEFAULT ''",
    ]:
        cursor.execute(col_def)
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
        quality_score REAL DEFAULT 0,
        quality_state TEXT DEFAULT 'needs_review',
        quality_reasons TEXT DEFAULT '[]',
        canonical_company TEXT DEFAULT '',
        canonical_title TEXT DEFAULT '',
        source_confidence REAL DEFAULT 0
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
    for col_def in [
        "ALTER TABLE jobs ADD COLUMN quality_state TEXT DEFAULT 'needs_review'",
        "ALTER TABLE jobs ADD COLUMN quality_reasons TEXT DEFAULT '[]'",
        "ALTER TABLE jobs ADD COLUMN canonical_company TEXT DEFAULT ''",
        "ALTER TABLE jobs ADD COLUMN canonical_title TEXT DEFAULT ''",
        "ALTER TABLE jobs ADD COLUMN source_confidence REAL DEFAULT 0",
    ]:
        try:
            cursor.execute(col_def)
        except sqlite3.OperationalError:
            pass

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_quality ON jobs(quality_score)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_quality_state ON jobs(quality_state)")

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
        shard_index INTEGER DEFAULT 0,
        status TEXT DEFAULT 'success',
        summary_json TEXT DEFAULT ''
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT NOT NULL,
        name TEXT,
        ats_type TEXT,
        tier TEXT DEFAULT 'P2',
        last_scraped_at TEXT,
        last_job_found_at TEXT,
        consecutive_failures INTEGER DEFAULT 0,
        is_dead INTEGER DEFAULT 0,
        validation_status TEXT DEFAULT 'unknown',
        validation_error TEXT DEFAULT '',
        validation_checked_at TEXT,
        validation_failure_category TEXT DEFAULT '',
        validation_http_status INTEGER,
        validated_metadata TEXT DEFAULT '',
        last_failure_category TEXT DEFAULT '',
        last_failure_at TEXT,
        last_success_at TEXT,
        next_due_at TEXT,
        lease_until TEXT,
        lease_owner TEXT DEFAULT '',
        last_attempt_at TEXT,
        health_state TEXT DEFAULT 'unknown',
        scrape_score REAL DEFAULT 0,
        avg_duration_ms REAL DEFAULT 0,
        yield_rate REAL DEFAULT 0,
        fresh_job_rate REAL DEFAULT 0,
        platform_budget_key TEXT DEFAULT '',
        source_count INTEGER DEFAULT 1,
        priority_score REAL DEFAULT 0,
        next_scrape_at TEXT,
        total_scrapes INTEGER DEFAULT 0,
        total_jobs_found INTEGER DEFAULT 0,
        total_relevant_jobs_found INTEGER DEFAULT 0,
        avg_jobs_found REAL DEFAULT 0,
        UNIQUE(ats_type, slug)
    )
    """)
    _migrate_sqlite_companies_schema(conn)
    for col_def in [
        "ALTER TABLE companies ADD COLUMN consecutive_failures INTEGER DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN is_dead INTEGER DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN validation_status TEXT DEFAULT 'unknown'",
        "ALTER TABLE companies ADD COLUMN validation_error TEXT DEFAULT ''",
        "ALTER TABLE companies ADD COLUMN validation_checked_at TEXT",
        "ALTER TABLE companies ADD COLUMN validation_failure_category TEXT DEFAULT ''",
        "ALTER TABLE companies ADD COLUMN validation_http_status INTEGER",
        "ALTER TABLE companies ADD COLUMN validated_metadata TEXT DEFAULT ''",
        "ALTER TABLE companies ADD COLUMN last_failure_category TEXT DEFAULT ''",
        "ALTER TABLE companies ADD COLUMN last_failure_at TEXT",
        "ALTER TABLE companies ADD COLUMN last_success_at TEXT",
        "ALTER TABLE companies ADD COLUMN next_due_at TEXT",
        "ALTER TABLE companies ADD COLUMN lease_until TEXT",
        "ALTER TABLE companies ADD COLUMN lease_owner TEXT DEFAULT ''",
        "ALTER TABLE companies ADD COLUMN last_attempt_at TEXT",
        "ALTER TABLE companies ADD COLUMN health_state TEXT DEFAULT 'unknown'",
        "ALTER TABLE companies ADD COLUMN scrape_score REAL DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN avg_duration_ms REAL DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN yield_rate REAL DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN fresh_job_rate REAL DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN platform_budget_key TEXT DEFAULT ''",
        "ALTER TABLE companies ADD COLUMN source_count INTEGER DEFAULT 1",
        "ALTER TABLE companies ADD COLUMN priority_score REAL DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN next_scrape_at TEXT",
        "ALTER TABLE companies ADD COLUMN total_scrapes INTEGER DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN total_jobs_found INTEGER DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN total_relevant_jobs_found INTEGER DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN avg_jobs_found REAL DEFAULT 0",
    ]:
        try:
            cursor.execute(col_def)
        except Exception:
            pass  # Column already exists
    cursor.execute("""
        DELETE FROM companies
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM companies
            WHERE ats_type IS NOT NULL AND slug IS NOT NULL
            GROUP BY ats_type, slug
        )
    """)
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_ats_slug ON companies (ats_type, slug)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_next_scrape ON companies (is_dead, next_scrape_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_priority ON companies (priority_score DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_lease ON companies (lease_until)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_companies_queue ON companies (is_dead, health_state, next_due_at, scrape_score DESC)"
    )
    for col_def in [
        "ALTER TABLE scraper_runs ADD COLUMN status TEXT DEFAULT 'success'",
        "ALTER TABLE scraper_runs ADD COLUMN summary_json TEXT DEFAULT ''",
    ]:
        try:
            cursor.execute(col_def)
        except Exception:
            pass
    conn.commit()


def _migrate_sqlite_companies_schema(conn):
    """Remove the old global slug UNIQUE constraint from SQLite companies tables."""
    cursor = conn.cursor()
    try:
        row = cursor.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'companies'").fetchone()
        table_sql = row[0] if row else ""
        if "slug TEXT UNIQUE NOT NULL" not in table_sql:
            return

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS companies_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL,
            name TEXT,
            ats_type TEXT,
            tier TEXT DEFAULT 'P2',
            last_scraped_at TEXT,
            last_job_found_at TEXT,
            consecutive_failures INTEGER DEFAULT 0,
            is_dead INTEGER DEFAULT 0,
            validation_status TEXT DEFAULT 'unknown',
            validation_error TEXT DEFAULT '',
            validation_checked_at TEXT,
            validation_failure_category TEXT DEFAULT '',
            validation_http_status INTEGER,
            source_count INTEGER DEFAULT 1,
            priority_score REAL DEFAULT 0,
            next_scrape_at TEXT,
            total_scrapes INTEGER DEFAULT 0,
            total_jobs_found INTEGER DEFAULT 0,
            total_relevant_jobs_found INTEGER DEFAULT 0,
            avg_jobs_found REAL DEFAULT 0,
            UNIQUE(ats_type, slug)
        )
        """)

        existing_cols = {r[1] for r in cursor.execute("PRAGMA table_info(companies)").fetchall()}
        select_cols = [
            "slug",
            "name",
            "ats_type",
            "COALESCE(tier, 'P2') AS tier",
            "last_scraped_at" if "last_scraped_at" in existing_cols else "NULL AS last_scraped_at",
            "last_job_found_at" if "last_job_found_at" in existing_cols else "NULL AS last_job_found_at",
            "COALESCE(consecutive_failures, 0) AS consecutive_failures"
            if "consecutive_failures" in existing_cols
            else "0 AS consecutive_failures",
            "COALESCE(is_dead, 0) AS is_dead" if "is_dead" in existing_cols else "0 AS is_dead",
            "COALESCE(validation_status, 'unknown') AS validation_status"
            if "validation_status" in existing_cols
            else "'unknown' AS validation_status",
            "COALESCE(validation_error, '') AS validation_error"
            if "validation_error" in existing_cols
            else "'' AS validation_error",
            "validation_checked_at" if "validation_checked_at" in existing_cols else "NULL AS validation_checked_at",
            "COALESCE(validation_failure_category, '') AS validation_failure_category"
            if "validation_failure_category" in existing_cols
            else "'' AS validation_failure_category",
            "validation_http_status" if "validation_http_status" in existing_cols else "NULL AS validation_http_status",
            "COALESCE(source_count, 1) AS source_count" if "source_count" in existing_cols else "1 AS source_count",
            "COALESCE(priority_score, 0) AS priority_score"
            if "priority_score" in existing_cols
            else "0 AS priority_score",
            "next_scrape_at" if "next_scrape_at" in existing_cols else "NULL AS next_scrape_at",
            "COALESCE(total_scrapes, 0) AS total_scrapes" if "total_scrapes" in existing_cols else "0 AS total_scrapes",
            "COALESCE(total_jobs_found, 0) AS total_jobs_found"
            if "total_jobs_found" in existing_cols
            else "0 AS total_jobs_found",
            "COALESCE(total_relevant_jobs_found, 0) AS total_relevant_jobs_found"
            if "total_relevant_jobs_found" in existing_cols
            else "0 AS total_relevant_jobs_found",
            "COALESCE(avg_jobs_found, 0) AS avg_jobs_found"
            if "avg_jobs_found" in existing_cols
            else "0 AS avg_jobs_found",
        ]
        cursor.execute(f"""
            INSERT OR IGNORE INTO companies_new (
                slug, name, ats_type, tier, last_scraped_at, last_job_found_at,
                consecutive_failures, is_dead, validation_status, validation_error,
                validation_checked_at, validation_failure_category, validation_http_status, source_count,
                priority_score, next_scrape_at, total_scrapes, total_jobs_found,
                total_relevant_jobs_found, avg_jobs_found
            )
            SELECT {", ".join(select_cols)}
            FROM companies
            WHERE slug IS NOT NULL AND ats_type IS NOT NULL
        """)
        cursor.execute("DROP TABLE companies")
        cursor.execute("ALTER TABLE companies_new RENAME TO companies")
        conn.commit()
    except Exception:
        conn.rollback()


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

    # Auto-populate keywords_matched if empty or missing
    keywords_list = job_dict.get("keywords_matched")
    if not keywords_list:
        from scripts.ingestion.role_filter import matches_target_role

        keywords_list = matches_target_role(job_dict.get("title", ""))
        job_dict["keywords_matched"] = keywords_list

    keywords = json.dumps(keywords_list)
    first_seen = datetime.now(timezone.utc).isoformat()
    quality_state, quality_reasons, canonical_company, canonical_title, source_confidence = classify_job_quality(
        job_dict
    )
    job_dict["quality_state"] = quality_state
    job_dict["quality_reasons"] = quality_reasons
    job_dict["canonical_company"] = canonical_company
    job_dict["canonical_title"] = canonical_title
    job_dict["source_confidence"] = source_confidence

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
                visa_sponsorship, tech_stack, is_active, last_seen_at, quality_score,
                quality_state, quality_reasons, canonical_company, canonical_title, source_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'unposted', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
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
                job_dict["quality_state"],
                json.dumps(job_dict["quality_reasons"]),
                job_dict["canonical_company"],
                job_dict["canonical_title"],
                job_dict["source_confidence"],
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        try:
            cursor.execute(
                """
                UPDATE jobs
                SET last_seen_at = ?, is_active = 1, quality_score = ?,
                    quality_state = ?, quality_reasons = ?,
                    canonical_company = ?, canonical_title = ?, source_confidence = ?
                WHERE internal_hash = ?
            """,
                (
                    first_seen,
                    compute_quality_score(job_dict),
                    job_dict["quality_state"],
                    json.dumps(job_dict["quality_reasons"]),
                    job_dict["canonical_company"],
                    job_dict["canonical_title"],
                    job_dict["source_confidence"],
                    internal_hash,
                ),
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
                visa_sponsorship, tech_stack, is_active, last_seen_at, quality_score,
                quality_state, quality_reasons, canonical_company, canonical_title, source_confidence
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'unposted', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (internal_hash) DO UPDATE SET
                last_seen_at = EXCLUDED.last_seen_at,
                is_active = TRUE,
                quality_score = EXCLUDED.quality_score,
                quality_state = EXCLUDED.quality_state,
                quality_reasons = EXCLUDED.quality_reasons,
                canonical_company = EXCLUDED.canonical_company,
                canonical_title = EXCLUDED.canonical_title,
                source_confidence = EXCLUDED.source_confidence,
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
                1
                if job_dict.get("visa_sponsorship") is True
                else (0 if job_dict.get("visa_sponsorship") is False else job_dict.get("visa_sponsorship")),
                tech_stack_json,
                first_seen,
                compute_quality_score(job_dict),
                job_dict["quality_state"],
                json.dumps(job_dict["quality_reasons"]),
                job_dict["canonical_company"],
                job_dict["canonical_title"],
                job_dict["source_confidence"],
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

    active_expr = "TRUE" if is_postgres() else "1"
    cursor.execute(
        f"SELECT internal_hash FROM jobs WHERE source_ats = {placeholder} AND LOWER(company) = {placeholder} AND is_active = {active_expr}",
        (ats_norm, company_norm),
    )
    all_hashes = {row[0] for row in cursor.fetchall()}
    stale_hashes = all_hashes - active_hashes

    if stale_hashes:
        qs = ",".join(placeholder for _ in stale_hashes)
        params = [now] + list(stale_hashes)
        inactive_expr = "FALSE" if is_postgres() else "0"
        cursor.execute(
            f"UPDATE jobs SET is_active = {inactive_expr}, last_seen_at = {placeholder} WHERE internal_hash IN ({qs})",
            params,
        )
        conn.commit()

    return len(stale_hashes)


def get_unposted_jobs(conn):
    """Fetch jobs ready to be sent to Discord (last 72 hours)."""
    direct_only = os.getenv("JOBCLAW_DIRECT_SOURCE_ONLY", "1").strip().lower() in {"1", "true", "yes", "on"}
    quality_clause_pg = "AND COALESCE(quality_state, 'needs_review') = 'accepted'" if direct_only else ""
    quality_clause_sqlite = "AND COALESCE(quality_state, 'needs_review') = 'accepted'" if direct_only else ""
    if is_postgres():
        cursor = conn.cursor()
        cursor.execute(
            f"""SELECT * FROM jobs
               WHERE status = 'unposted'
                 AND is_active = TRUE
                 AND first_seen::timestamptz >= NOW() - INTERVAL '72 hours'
                 {quality_clause_pg}
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
            f"""SELECT * FROM jobs
               WHERE status = 'unposted'
                   AND is_active = 1
                 AND (
                   (date_posted != '' AND date_posted >= datetime('now', '-72 hours'))
                   OR (date_posted = '' AND first_seen >= datetime('now', '-72 hours'))
                 )
                 {quality_clause_sqlite}
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
    """Archive jobs that are too old to post (>72 hours unposted). Returns count archived."""
    cursor = conn.cursor()
    try:
        if is_postgres():
            cursor.execute(
                """UPDATE jobs SET status = 'archived'
                   WHERE status = 'unposted'
                   AND first_seen::timestamptz < NOW() - INTERVAL '72 hours'"""
            )
        else:
            cursor.execute(
                """UPDATE jobs SET status = 'archived'
                   WHERE status = 'unposted'
                   AND first_seen < datetime('now', '-72 hours')"""
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

    # Base query. Runtime scrapers read from the canonical companies table
    # and skip quarantined/dead targets.
    query = f"SELECT * FROM companies WHERE tier = {placeholder} AND COALESCE(is_dead, 0) = 0"
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

    # Normalize DB column names to match the scraper's expected dict keys
    for c in all_companies:
        if "ats_type" in c and "ats" not in c:
            c["ats"] = c["ats_type"]
        if "name" in c and "company" not in c:
            c["company"] = c["name"]

    if shard is not None and all_companies:
        # Client-side sharding for simplicity, or we could do it in SQL
        all_companies.sort(key=lambda x: x["slug"])
        chunk_size = len(all_companies) // total_shards
        remainder = len(all_companies) % total_shards
        start_idx = shard * chunk_size + min(shard, remainder)
        end_idx = start_idx + chunk_size + (1 if shard < remainder else 0)
        return all_companies[start_idx:end_idx]

    return all_companies


def get_companies_for_scrape(
    conn,
    shard: int = None,
    total_shards: int = 4,
    platforms: set[str] | None = None,
) -> list[dict]:
    """Fetch all non-quarantined companies for runtime scraping."""
    cursor = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"

    query = "SELECT * FROM companies WHERE COALESCE(is_dead, 0) = 0"
    params = []
    if platforms:
        qs = ",".join(placeholder for _ in platforms)
        query += f" AND LOWER(ats_type) IN ({qs})"
        params.extend(sorted(p.lower() for p in platforms))

    cursor.execute(query, params)
    if is_postgres():
        cols = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        all_companies = [dict(zip(cols, row)) for row in rows]
    else:
        rows = cursor.fetchall()
        all_companies = [
            dict(r) if hasattr(r, "keys") else dict(zip([d[0] for d in cursor.description], r)) for r in rows
        ]

    for c in all_companies:
        if "ats_type" in c and "ats" not in c:
            c["ats"] = c["ats_type"]
        if "name" in c and "company" not in c:
            c["company"] = c["name"]

    if shard is not None and all_companies:
        if shard == -1:
            shard = get_next_shard_from_db(conn, "ats_auto", total_shards)
        all_companies.sort(key=lambda x: f"{x.get('ats', '')}:{x.get('slug', '')}")
        chunk_size = len(all_companies) // total_shards
        remainder = len(all_companies) % total_shards
        start_idx = shard * chunk_size + min(shard, remainder)
        end_idx = start_idx + chunk_size + (1 if shard < remainder else 0)
        return all_companies[start_idx:end_idx]

    return all_companies


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def compute_company_priority(company: dict) -> float:
    """Score runtime targets for due-target scheduling."""
    tier = company.get("tier") or DEFAULT_TIER
    score = {"P0": 100.0, "P1": 60.0, "P2": 20.0, "P3": 5.0}.get(tier, 20.0)

    source_count = int(company.get("source_count") or 1)
    total_jobs = int(company.get("total_jobs_found") or 0)
    total_relevant = int(company.get("total_relevant_jobs_found") or 0)
    failures = int(company.get("consecutive_failures") or 0)

    score += min(source_count, 10) * 0.5
    score += min(total_jobs, 100) * 0.2
    score += min(total_relevant, 50) * 1.5
    score -= failures * 8

    last_job = _parse_dt(company.get("last_job_found_at"))
    if last_job:
        age_hours = max(0.0, (datetime.now(timezone.utc) - last_job).total_seconds() / 3600)
        if age_hours < 24:
            score += 25
        elif age_hours < 168:
            score += 10

    return max(0.0, round(score, 2))


def compute_next_scrape_at(company: dict, job_count: int = 0, relevant_count: int = 0, failed: bool = False) -> str:
    """Calculate the next due time for a target."""
    now = datetime.now(timezone.utc)
    tier = company.get("tier") or DEFAULT_TIER
    interval = TIER_INTERVALS.get(tier, TIER_INTERVALS[DEFAULT_TIER])

    failures = int(company.get("consecutive_failures") or 0)
    if failed:
        interval = min(timedelta(days=7), interval * max(2, min(8, failures + 1)))
    elif relevant_count > 0:
        interval = min(interval, timedelta(hours=1))
    elif job_count > 0:
        interval = min(interval, timedelta(hours=4))
    elif failures >= 5:
        interval = min(timedelta(days=7), interval * 3)

    return (now + interval).isoformat()


def get_due_companies_for_scrape(
    conn,
    limit: int = 1000,
    platforms: set[str] | None = None,
    include_not_due: bool = False,
) -> list[dict]:
    """Fetch highest-priority canonical targets due for scraping."""
    cursor = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"
    now = datetime.now(timezone.utc).isoformat()

    query = "SELECT * FROM companies WHERE COALESCE(is_dead, 0) = 0"
    params = []
    if platforms:
        qs = ",".join(placeholder for _ in platforms)
        query += f" AND LOWER(ats_type) IN ({qs})"
        params.extend(sorted(p.lower() for p in platforms))
    if not include_not_due:
        query += f" AND (next_scrape_at IS NULL OR next_scrape_at <= {placeholder})"
        params.append(now)

    query += f" ORDER BY priority_score DESC, COALESCE(next_scrape_at, '') ASC, tier ASC, slug ASC LIMIT {placeholder}"
    params.append(limit)
    cursor.execute(query, params)

    if is_postgres():
        cols = [desc[0] for desc in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    else:
        rows = [
            dict(r) if hasattr(r, "keys") else dict(zip([d[0] for d in cursor.description], r))
            for r in cursor.fetchall()
        ]

    for c in rows:
        if "ats_type" in c and "ats" not in c:
            c["ats"] = c["ats_type"]
        if "name" in c and "company" not in c:
            c["company"] = c["name"]
    return rows


def _normalize_company_rows(rows: list[dict]) -> list[dict]:
    """Normalize DB company rows into scraper target shape."""
    for c in rows:
        if "ats_type" in c and "ats" not in c:
            c["ats"] = c["ats_type"]
        if "name" in c and "company" not in c:
            c["company"] = c["name"]
    return rows


def claim_adaptive_companies_for_scrape(
    conn,
    limit: int = 250,
    platforms: set[str] | None = None,
    lease_owner: str = "",
    lease_seconds: int = 300,
    include_not_due: bool = False,
) -> list[dict]:
    """Claim queue targets with a short DB lease so workers do not duplicate work."""
    cursor = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"
    now = datetime.now(timezone.utc).isoformat()
    lease_until = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).isoformat()
    owner = lease_owner or f"jobclaw:{os.getpid()}"

    platform_sql = ""
    params: list = []
    if platforms:
        qs = ",".join(placeholder for _ in platforms)
        platform_sql = f" AND LOWER(ats_type) IN ({qs})"
        params.extend(sorted(p.lower() for p in platforms))

    due_sql = ""
    if not include_not_due:
        due_sql = (
            f" AND (COALESCE(next_due_at, next_scrape_at) IS NULL "
            f"OR COALESCE(next_due_at, next_scrape_at) <= {placeholder})"
        )
        params.append(now)

    if is_postgres():
        cursor.execute(
            f"""
            WITH picked AS (
                SELECT id
                FROM companies
                WHERE COALESCE(is_dead, 0) = 0
                  AND (lease_until IS NULL OR lease_until <= {placeholder} OR lease_owner = {placeholder})
                  {platform_sql}
                  {due_sql}
                ORDER BY
                  CASE COALESCE(tier, 'P2') WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
                  COALESCE(scrape_score, 0) DESC,
                  COALESCE(priority_score, 0) DESC,
                  COALESCE(fresh_job_rate, 0) DESC,
                  COALESCE(next_due_at, next_scrape_at, '') ASC,
                  slug ASC
                LIMIT {placeholder}
                FOR UPDATE SKIP LOCKED
            )
            UPDATE companies c
            SET lease_until = {placeholder},
                lease_owner = {placeholder},
                last_attempt_at = {placeholder}
            FROM picked
            WHERE c.id = picked.id
            RETURNING c.*
            """,
            (now, owner, *params, limit, lease_until, owner, now),
        )
        cols = [desc[0] for desc in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    else:
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            f"""
            SELECT *
            FROM companies
            WHERE COALESCE(is_dead, 0) = 0
              AND (lease_until IS NULL OR lease_until <= {placeholder} OR lease_owner = {placeholder})
              {platform_sql}
              {due_sql}
            ORDER BY
              CASE COALESCE(tier, 'P2') WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
              COALESCE(scrape_score, 0) DESC,
              COALESCE(priority_score, 0) DESC,
              COALESCE(fresh_job_rate, 0) DESC,
              COALESCE(next_due_at, next_scrape_at, '') ASC,
              slug ASC
            LIMIT {placeholder}
            """,
            (now, owner, *params, limit),
        )
        rows = [
            dict(r) if hasattr(r, "keys") else dict(zip([d[0] for d in cursor.description], r))
            for r in cursor.fetchall()
        ]
        ids = [r["id"] for r in rows]
        if ids:
            qs = ",".join("?" for _ in ids)
            cursor.execute(
                f"""
                UPDATE companies
                SET lease_until = ?,
                    lease_owner = ?,
                    last_attempt_at = ?
                WHERE id IN ({qs})
                """,
                (lease_until, owner, now, *ids),
            )
    conn.commit()
    return _normalize_company_rows(rows)


def release_company_leases(conn, targets: list[dict], lease_owner: str = "") -> int:
    """Release active leases for skipped targets."""
    if not targets:
        return 0
    cursor = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"
    released = 0
    for target in targets:
        params = [target.get("ats") or target.get("ats_type"), target.get("slug")]
        owner_clause = ""
        if lease_owner:
            owner_clause = f" AND lease_owner = {placeholder}"
            params.append(lease_owner)
        cursor.execute(
            f"""
            UPDATE companies
            SET lease_until = NULL,
                lease_owner = ''
            WHERE ats_type = {placeholder}
              AND slug = {placeholder}
              {owner_clause}
            """,
            tuple(params),
        )
        released += cursor.rowcount
    conn.commit()
    return released


def get_scraper_control_snapshot(conn) -> dict:
    """Return queue/control-plane metrics for API health and operator reports."""
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    placeholder = "%s" if is_postgres() else "?"

    def scalar(sql: str, params: tuple = ()) -> int:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    active_expr = "COALESCE(is_dead, 0) = 0"
    backlog = scalar(
        f"""
        SELECT COUNT(*) FROM companies
        WHERE {active_expr}
          AND (COALESCE(next_due_at, next_scrape_at) IS NULL
               OR COALESCE(next_due_at, next_scrape_at) <= {placeholder})
        """,
        (now,),
    )
    leased = scalar(
        f"SELECT COUNT(*) FROM companies WHERE {active_expr} AND lease_until IS NOT NULL AND lease_until > {placeholder}",
        (now,),
    )
    dead = scalar("SELECT COUNT(*) FROM companies WHERE COALESCE(is_dead, 0) = 1")
    stale_hot = scalar(
        f"""
        SELECT COUNT(*) FROM companies
        WHERE tier IN ('P0', 'P1')
          AND {active_expr}
          AND (last_success_at IS NULL OR last_success_at < {placeholder})
        """,
        ((datetime.now(timezone.utc) - timedelta(hours=6)).isoformat(),),
    )

    cursor.execute(
        f"""
        SELECT COALESCE(ats_type, 'unknown') AS platform,
               COUNT(*) AS targets,
               SUM(CASE WHEN COALESCE(is_dead, 0) = 1 THEN 1 ELSE 0 END) AS dead,
               SUM(CASE WHEN lease_until IS NOT NULL AND lease_until > {placeholder} THEN 1 ELSE 0 END) AS leased,
               AVG(COALESCE(scrape_score, priority_score, 0)) AS avg_score
        FROM companies
        GROUP BY COALESCE(ats_type, 'unknown')
        ORDER BY targets DESC
        """,
        (now,),
    )
    platforms = []
    for row in cursor.fetchall():
        d = dict(row) if hasattr(row, "keys") else dict(zip([desc[0] for desc in cursor.description], row))
        platforms.append(d)

    cursor.execute(
        """
        SELECT COALESCE(ats_type, 'unknown') AS ats_type, slug, COALESCE(name, '') AS name,
               COALESCE(last_failure_category, validation_failure_category, '') AS failure_category,
               COALESCE(consecutive_failures, 0) AS consecutive_failures
        FROM companies
        WHERE COALESCE(consecutive_failures, 0) > 0
        ORDER BY consecutive_failures DESC, last_failure_at DESC
        LIMIT 10
        """
    )
    failing_targets = [
        dict(row) if hasattr(row, "keys") else dict(zip([desc[0] for desc in cursor.description], row))
        for row in cursor.fetchall()
    ]

    return {
        "mode": os.getenv("JOBCLAW_QUEUE_MODE", "active"),
        "backlog_due": backlog,
        "leased": leased,
        "dead_targets": dead,
        "stale_hot_targets": stale_hot,
        "platforms": platforms,
        "top_failing_targets": failing_targets,
    }


def update_company_last_scraped(
    conn,
    slug: str,
    job_found: bool = False,
    ats: str | None = None,
    job_count: int = 0,
    relevant_count: int = 0,
    failed: bool = False,
    failure_category: str | None = None,
):
    """Update metadata for TTL backoff logic.

    Dynamic Tier Promotion: If a P2 company posts a job, promote it to P1 for
    more frequent monitoring in subsequent runs.
    """
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    placeholder = "%s" if is_postgres() else "?"
    target_clause = f"slug = {placeholder}"
    target_params = [slug]
    if ats:
        target_clause += f" AND ats_type = {placeholder}"
        target_params.append(ats)

    cursor.execute(f"SELECT * FROM companies WHERE {target_clause} LIMIT 1", tuple(target_params))
    row = cursor.fetchone()
    if row is None:
        return
    if is_postgres():
        cols = [desc[0] for desc in cursor.description]
        company = dict(zip(cols, row))
    else:
        company = dict(row) if hasattr(row, "keys") else dict(zip([d[0] for d in cursor.description], row))

    job_found = job_found or job_count > 0
    previous_scrapes = int(company.get("total_scrapes") or 0)
    previous_jobs = int(company.get("total_jobs_found") or 0)
    total_scrapes = previous_scrapes + 1
    total_jobs = previous_jobs + max(0, job_count)
    total_relevant = int(company.get("total_relevant_jobs_found") or 0) + max(0, relevant_count)
    avg_jobs = round(total_jobs / total_scrapes, 2) if total_scrapes else 0
    yield_rate = round(total_jobs / total_scrapes, 4) if total_scrapes else 0
    fresh_job_rate = round(total_relevant / total_scrapes, 4) if total_scrapes else 0

    tier = company.get("tier") or DEFAULT_TIER
    if relevant_count > 0 and tier in {"P2", "P3"}:
        tier = "P1"
    elif job_count == 0 and previous_scrapes >= 10 and tier == "P2":
        tier = "P3"

    company.update(
        {
            "tier": tier,
            "consecutive_failures": int(company.get("consecutive_failures") or 0) + (1 if failed else 0),
            "total_scrapes": total_scrapes,
            "total_jobs_found": total_jobs,
            "total_relevant_jobs_found": total_relevant,
            "avg_jobs_found": avg_jobs,
        }
    )
    priority_score = compute_company_priority(company)
    next_scrape_at = compute_next_scrape_at(company, job_count=job_count, relevant_count=relevant_count, failed=failed)

    last_job_found_at = now if job_found else company.get("last_job_found_at")
    failure_expr = "consecutive_failures + 1" if failed else "0"
    failure_threshold = 2 if failure_category == "bad_target" else 10
    dead_expr = f"CASE WHEN consecutive_failures + 1 >= {failure_threshold} THEN 1 ELSE is_dead END" if failed else "0"
    new_failures = int(company.get("consecutive_failures") or 0) + (1 if failed else 0)
    will_be_dead = failed and new_failures >= failure_threshold
    health_state = "quarantined" if will_be_dead else ("degraded" if failed else "healthy")
    scrape_score = round(priority_score + min(fresh_job_rate * 25, 25) + min(yield_rate * 5, 25) - new_failures * 5, 2)

    cursor.execute(
        f"""
        UPDATE companies
        SET last_scraped_at = {placeholder},
            last_job_found_at = {placeholder},
            tier = {placeholder},
            consecutive_failures = {failure_expr},
            is_dead = {dead_expr},
            validation_status = {placeholder},
            validation_failure_category = {placeholder},
            last_failure_category = {placeholder},
            last_failure_at = {placeholder},
            last_success_at = {placeholder},
            total_scrapes = {placeholder},
            total_jobs_found = {placeholder},
            total_relevant_jobs_found = {placeholder},
            avg_jobs_found = {placeholder},
            priority_score = {placeholder},
            next_scrape_at = {placeholder},
            next_due_at = {placeholder},
            lease_until = NULL,
            lease_owner = '',
            health_state = {placeholder},
            scrape_score = {placeholder},
            yield_rate = {placeholder},
            fresh_job_rate = {placeholder},
            platform_budget_key = {placeholder}
        WHERE {target_clause}
        """,
        (
            now,
            last_job_found_at,
            tier,
            "failed" if failed else "ok",
            failure_category or "",
            failure_category or "",
            now if failed else company.get("last_failure_at"),
            company.get("last_success_at") if failed else now,
            total_scrapes,
            total_jobs,
            total_relevant,
            avg_jobs,
            priority_score,
            next_scrape_at,
            next_scrape_at,
            health_state,
            scrape_score,
            yield_rate,
            fresh_job_rate,
            ats or company.get("ats_type") or "",
            *target_params,
        ),
    )
    conn.commit()


def update_company_validated_metadata(conn, ats: str, slug: str, metadata: dict):
    """Merge platform-specific validated metadata for a canonical company target."""
    if not metadata:
        return
    cursor = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"
    cursor.execute(
        f"SELECT validated_metadata FROM companies WHERE ats_type = {placeholder} AND slug = {placeholder} LIMIT 1",
        (ats, slug),
    )
    row = cursor.fetchone()
    if not row:
        return
    existing = {}
    raw = row[0] if row else ""
    if raw:
        try:
            existing = json.loads(raw)
        except Exception:
            existing = {}
    existing.update(metadata)
    cursor.execute(
        f"""
        UPDATE companies
        SET validated_metadata = {placeholder},
            validation_status = 'ok',
            validation_error = '',
            validation_checked_at = {placeholder}
        WHERE ats_type = {placeholder} AND slug = {placeholder}
        """,
        (json.dumps(existing, sort_keys=True), datetime.now(timezone.utc).isoformat(), ats, slug),
    )
    conn.commit()


def clear_company_validated_metadata_key(conn, ats: str, slug: str, key: str):
    """Remove one platform metadata key without changing validation status."""
    cursor = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"
    cursor.execute(
        f"SELECT validated_metadata FROM companies WHERE ats_type = {placeholder} AND slug = {placeholder} LIMIT 1",
        (ats, slug),
    )
    row = cursor.fetchone()
    if not row:
        return
    existing = {}
    raw = row[0] if row else ""
    if raw:
        try:
            existing = json.loads(raw)
        except Exception:
            existing = {}
    if key not in existing:
        return
    existing.pop(key, None)
    cursor.execute(
        f"""
        UPDATE companies
        SET validated_metadata = {placeholder},
            validation_checked_at = {placeholder}
        WHERE ats_type = {placeholder} AND slug = {placeholder}
        """,
        (json.dumps(existing, sort_keys=True), datetime.now(timezone.utc).isoformat(), ats, slug),
    )
    conn.commit()


def mark_company_failure(conn, slug: str, permanent: bool = False):
    """
    Record a scrape failure for a company slug.
    permanent=True (HTTP 404) -> marks is_dead=1 after 2 failures.
    permanent=False (timeout) -> marks is_dead=1 after 10 failures.
    Resets automatically on next successful scrape via update_company_last_scraped().
    """
    try:
        placeholder = "%s" if is_postgres() else "?"
        cursor = conn.cursor()
        failure_status = "bad_target" if permanent else "failed"
        cursor.execute(f"SELECT * FROM companies WHERE slug = {placeholder} LIMIT 1", (slug,))
        row = cursor.fetchone()
        if row:
            if is_postgres():
                cols = [desc[0] for desc in cursor.description]
                company = dict(zip(cols, row))
            else:
                company = dict(row) if hasattr(row, "keys") else dict(zip([d[0] for d in cursor.description], row))
        else:
            company = {"tier": DEFAULT_TIER, "consecutive_failures": 0}
        company["consecutive_failures"] = int(company.get("consecutive_failures") or 0) + 1
        priority_score = compute_company_priority(company)
        next_scrape_at = compute_next_scrape_at(company, failed=True)
        cursor.execute(
            f"""
            UPDATE companies
            SET consecutive_failures = consecutive_failures + 1,
                validation_status = {placeholder},
                validation_failure_category = {placeholder},
                last_failure_category = {placeholder},
                last_failure_at = {placeholder},
                health_state = {placeholder},
                priority_score = {placeholder},
                next_scrape_at = {placeholder},
                next_due_at = {placeholder}
            WHERE slug = {placeholder}
            """,
            (
                failure_status,
                failure_status,
                failure_status,
                datetime.now(timezone.utc).isoformat(),
                "degraded",
                priority_score,
                next_scrape_at,
                next_scrape_at,
                slug,
            ),
        )
        threshold = 2 if permanent else 10
        cursor.execute(
            f"""
            UPDATE companies
            SET is_dead = 1,
                health_state = 'quarantined'
            WHERE slug = {placeholder}
              AND consecutive_failures >= {placeholder}
            """,
            (slug, threshold),
        )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


def record_company_validation(conn, ats: str, slug: str, result: dict):
    """Persist live target validation status and quarantine repeated bad targets."""
    cursor = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"
    now = datetime.now(timezone.utc).isoformat()

    status = str(result.get("status") or "unknown")
    category = str(result.get("category") or "")
    error = str(result.get("error") or "")
    http_status = result.get("status_code")
    is_good = status == "ok"
    is_bad_target = category == "bad_target" or status == "bad_target"
    cursor.execute(
        f"SELECT * FROM companies WHERE ats_type = {placeholder} AND slug = {placeholder} LIMIT 1",
        (ats, slug),
    )
    row = cursor.fetchone()
    if row:
        if is_postgres():
            cols = [desc[0] for desc in cursor.description]
            company = dict(zip(cols, row))
        else:
            company = dict(row) if hasattr(row, "keys") else dict(zip([d[0] for d in cursor.description], row))
    else:
        company = {"tier": DEFAULT_TIER, "consecutive_failures": 0}

    if is_good:
        company["consecutive_failures"] = 0
        company["is_dead"] = 0
        priority_score = compute_company_priority(company)
        cursor.execute(
            f"""
            UPDATE companies
            SET validation_status = {placeholder},
                validation_error = '',
                validation_checked_at = {placeholder},
                validation_failure_category = '',
                validation_http_status = {placeholder},
                consecutive_failures = 0,
                is_dead = 0,
                health_state = 'healthy',
                last_success_at = {placeholder},
                priority_score = {placeholder},
                next_scrape_at = CASE
                    WHEN next_scrape_at IS NULL OR next_scrape_at > {placeholder} THEN {placeholder}
                    ELSE next_scrape_at
                END,
                next_due_at = CASE
                    WHEN next_due_at IS NULL OR next_due_at > {placeholder} THEN {placeholder}
                    ELSE next_due_at
                END
            WHERE ats_type = {placeholder} AND slug = {placeholder}
            """,
            (status, now, http_status, now, priority_score, now, now, now, now, ats, slug),
        )
    else:
        company["consecutive_failures"] = int(company.get("consecutive_failures") or 0) + 1
        priority_score = compute_company_priority(company)
        next_scrape_at = compute_next_scrape_at(company, failed=True)
        cursor.execute(
            f"""
            UPDATE companies
            SET validation_status = {placeholder},
                validation_error = {placeholder},
                validation_checked_at = {placeholder},
                validation_failure_category = {placeholder},
                validation_http_status = {placeholder},
                consecutive_failures = consecutive_failures + 1,
                last_failure_category = {placeholder},
                last_failure_at = {placeholder},
                health_state = {placeholder},
                priority_score = {placeholder},
                next_scrape_at = {placeholder},
                next_due_at = {placeholder}
            WHERE ats_type = {placeholder} AND slug = {placeholder}
            """,
            (
                status,
                error[:1000],
                now,
                category,
                http_status,
                category,
                now,
                "degraded",
                priority_score,
                next_scrape_at,
                next_scrape_at,
                ats,
                slug,
            ),
        )
        threshold = 3 if is_bad_target else 10
        cursor.execute(
            f"""
            UPDATE companies
            SET is_dead = 1,
                health_state = 'quarantined'
            WHERE ats_type = {placeholder}
              AND slug = {placeholder}
              AND consecutive_failures >= {placeholder}
            """,
            (ats, slug, threshold),
        )
    conn.commit()


def log_scraper_run(
    conn,
    script_name: str,
    companies_scraped: int,
    new_jobs: int,
    duration: float,
    errors: str = None,
    shard_index: int = 0,
    status: str = "success",
    summary_json: str | dict | None = None,
):
    """Log the performance metrics of a scraper run, including shard index."""
    cursor = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"
    if isinstance(summary_json, dict):
        summary_json = json.dumps(summary_json, sort_keys=True)
    cursor.execute(
        f"""
        INSERT INTO scraper_runs (
            scraper, companies_scraped, new_jobs, duration_seconds, errors,
            run_at, shard_index, status, summary_json
        )
        VALUES (
            {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
            {placeholder}, {placeholder}, {placeholder}, {placeholder}
        )
    """,
        (
            script_name,
            companies_scraped,
            new_jobs,
            duration,
            errors or "",
            datetime.now(timezone.utc).isoformat(),
            shard_index,
            status,
            summary_json or "",
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
