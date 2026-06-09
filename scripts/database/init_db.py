import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

DB_PATH = Path(__file__).parent.parent.parent / "data" / "jobclaw.db"
OLD_JSON_PATH = Path(__file__).parent.parent.parent / "data" / "jobs.json"


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)

    # Enable WAL mode for high concurrency
    conn.execute("PRAGMA journal_mode=WAL;")

    cursor = conn.cursor()

    # Create the core jobs table
    # Unique constraint prevents identical job IDs from the same company spanning the DB
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

    # Create indexing for the headless discord bot to query fast
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON jobs(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_first_seen ON jobs(first_seen)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_company ON jobs(company)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_ats ON jobs(source_ats)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_is_active ON jobs(is_active)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_quality_state ON jobs(quality_state)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS job_fingerprints (
        internal_hash TEXT PRIMARY KEY,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        posted_at TEXT,
        source_ats TEXT DEFAULT ''
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_fingerprints_last_seen ON job_fingerprints(last_seen)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_fingerprints_posted_at ON job_fingerprints(posted_at)")

    # Run schema migrations for existing databases
    _migrate_schema(conn)

    # Create the canonical run history table for monitoring health
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
        source_count INTEGER DEFAULT 1,
        priority_score REAL DEFAULT 0,
        next_scrape_at TEXT,
        total_scrapes INTEGER DEFAULT 0,
        total_jobs_found INTEGER DEFAULT 0,
        total_relevant_jobs_found INTEGER DEFAULT 0,
        avg_jobs_found REAL DEFAULT 0,
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
        UNIQUE(ats_type, slug)
    )
    """)
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_ats_slug ON companies (ats_type, slug)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_next_scrape ON companies (is_dead, next_scrape_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_priority ON companies (priority_score DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_lease ON companies (lease_until)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_companies_queue ON companies (is_dead, health_state, next_due_at, scrape_score DESC)"
    )

    conn.commit()
    logging.info(f"SQLite DB initialized at {DB_PATH} with WAL mode enabled.")
    return conn


def _migrate_schema(conn):
    """Add columns that may be missing on older databases."""
    cursor = conn.cursor()
    # Get existing column names
    cursor.execute("PRAGMA table_info(jobs)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    migrations = [
        ("description", "TEXT"),
        ("salary_min", "REAL"),
        ("salary_max", "REAL"),
        ("salary_currency", "TEXT"),
        ("experience_years", "INTEGER"),
        ("remote_ok", "TEXT"),
        ("job_type", "TEXT"),
        ("seniority_level", "TEXT"),
        ("visa_sponsorship", "INTEGER"),
        ("tech_stack", "TEXT"),
        ("is_active", "INTEGER DEFAULT 1"),
        ("last_seen_at", "TEXT"),
        ("quality_score", "REAL DEFAULT 0"),
        ("quality_state", "TEXT DEFAULT 'needs_review'"),
        ("quality_reasons", "TEXT DEFAULT '[]'"),
        ("canonical_company", "TEXT DEFAULT ''"),
        ("canonical_title", "TEXT DEFAULT ''"),
        ("source_confidence", "REAL DEFAULT 0"),
    ]

    for col_name, col_type in migrations:
        if col_name not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}")
                logging.info(f"Migrated: added column '{col_name}' to jobs table.")
            except Exception as e:
                logging.warning(f"Migration skipped for '{col_name}': {e}")

    conn.commit()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS job_fingerprints (
        internal_hash TEXT PRIMARY KEY,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        posted_at TEXT,
        source_ats TEXT DEFAULT ''
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_fingerprints_last_seen ON job_fingerprints(last_seen)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_fingerprints_posted_at ON job_fingerprints(posted_at)")
    conn.commit()

    # Add failure-tracking columns to companies table if missing
    try:
        cursor.execute("PRAGMA table_info(companies)")
        company_cols = {row[1] for row in cursor.fetchall()}
        for col_name, col_type in [
            ("consecutive_failures", "INTEGER DEFAULT 0"),
            ("is_dead", "INTEGER DEFAULT 0"),
            ("validation_status", "TEXT DEFAULT 'unknown'"),
            ("validation_error", "TEXT DEFAULT ''"),
            ("validation_checked_at", "TEXT"),
            ("validation_failure_category", "TEXT DEFAULT ''"),
            ("validation_http_status", "INTEGER"),
            ("source_count", "INTEGER DEFAULT 1"),
            ("priority_score", "REAL DEFAULT 0"),
            ("next_scrape_at", "TEXT"),
            ("total_scrapes", "INTEGER DEFAULT 0"),
            ("total_jobs_found", "INTEGER DEFAULT 0"),
            ("total_relevant_jobs_found", "INTEGER DEFAULT 0"),
            ("avg_jobs_found", "REAL DEFAULT 0"),
            ("validated_metadata", "TEXT DEFAULT ''"),
            ("last_failure_category", "TEXT DEFAULT ''"),
            ("last_failure_at", "TEXT"),
            ("last_success_at", "TEXT"),
            ("next_due_at", "TEXT"),
            ("lease_until", "TEXT"),
            ("lease_owner", "TEXT DEFAULT ''"),
            ("last_attempt_at", "TEXT"),
            ("health_state", "TEXT DEFAULT 'unknown'"),
            ("scrape_score", "REAL DEFAULT 0"),
            ("avg_duration_ms", "REAL DEFAULT 0"),
            ("yield_rate", "REAL DEFAULT 0"),
            ("fresh_job_rate", "REAL DEFAULT 0"),
            ("platform_budget_key", "TEXT DEFAULT ''"),
        ]:
            if col_name not in company_cols:
                cursor.execute(f"ALTER TABLE companies ADD COLUMN {col_name} {col_type}")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_ats_slug ON companies (ats_type, slug)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_next_scrape ON companies (is_dead, next_scrape_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_priority ON companies (priority_score DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_lease ON companies (lease_until)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_companies_queue ON companies (is_dead, health_state, next_due_at, scrape_score DESC)"
        )
        conn.commit()
    except Exception:
        pass  # companies table may not exist yet (PostgreSQL path)

    try:
        cursor.execute("PRAGMA table_info(scraper_runs)")
        run_cols = {row[1] for row in cursor.fetchall()}
        for col_name, col_type in [
            ("status", "TEXT DEFAULT 'success'"),
            ("summary_json", "TEXT DEFAULT ''"),
        ]:
            if col_name not in run_cols:
                cursor.execute(f"ALTER TABLE scraper_runs ADD COLUMN {col_name} {col_type}")
        conn.commit()
    except Exception:
        pass  # scraper_runs table may not exist yet


def migrate_old_data(conn):
    if not OLD_JSON_PATH.exists():
        logging.info("No old jobs.json found to migrate.")
        return

    try:
        with open(OLD_JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)

        old_jobs = data.get("jobs", {})
        if not old_jobs:
            logging.info("jobs.json is empty. Nothing to migrate.")
            return

        cursor = conn.cursor()
        migrated_count = 0

        for _k, v in old_jobs.items():
            # Old data used a short hash as the key. Let's build the composite hash exactly like the new system will.
            # Using url or job_id + company
            company_norm = v.get("company", "Unknown").lower().strip()
            source_ats = v.get("source_ats", "unknown").lower().strip()
            job_id_norm = str(v.get("job_id", v.get("url", ""))).lower().strip()

            internal_hash = f"{source_ats}::{company_norm}::{job_id_norm}"

            keywords = json.dumps(v.get("keywords_matched", []))

            # Since these were already in jobs.json, they've been posted previously (or at least we don't want to re-spam them).
            # We'll set status to 'posted' to avoid the discord bot blasting thousands of old jobs.
            try:
                cursor.execute(
                    """
                    INSERT INTO jobs (
                        internal_hash, job_id, title, company, location, url,
                        date_posted, source_ats, first_seen, status, keywords_matched
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'posted', ?)
                """,
                    (
                        internal_hash,
                        v.get("job_id", ""),
                        v.get("title", ""),
                        v.get("company", ""),
                        v.get("location", ""),
                        v.get("url", ""),
                        v.get("date_posted", ""),
                        v.get("source_ats", ""),
                        v.get("first_seen", datetime.now(timezone.utc).isoformat()),
                        keywords,
                    ),
                )
                migrated_count += 1
            except sqlite3.IntegrityError:
                pass  # Already exists

        conn.commit()
        logging.info(f"Migrated {migrated_count} legacy jobs into SQLite as 'posted'.")

    except Exception as e:
        logging.error(f"Failed to migrate old JSON data: {e}")


if __name__ == "__main__":
    conn = init_db()
    migrate_old_data(conn)
    conn.close()
