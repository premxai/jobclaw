import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

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
        is_active INTEGER DEFAULT 1,
        last_seen_at TEXT
    )
    """)
    
    # Create indexing for the headless discord bot to query fast
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON jobs(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_first_seen ON jobs(first_seen)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_company ON jobs(company)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_ats ON jobs(source_ats)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_is_active ON jobs(is_active)")

    # Run schema migrations for existing databases
    _migrate_schema(conn)
    
    # Create the run history table for monitoring health
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        script_name TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        companies_fetched INTEGER,
        new_jobs_found INTEGER,
        duration_s REAL,
        errors TEXT
    )
    """)
    
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
        ("is_active", "INTEGER DEFAULT 1"),
        ("last_seen_at", "TEXT"),
    ]

    for col_name, col_type in migrations:
        if col_name not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}")
                logging.info(f"Migrated: added column '{col_name}' to jobs table.")
            except Exception as e:
                logging.warning(f"Migration skipped for '{col_name}': {e}")

    conn.commit()


def migrate_old_data(conn):
    if not OLD_JSON_PATH.exists():
        logging.info("No old jobs.json found to migrate.")
        return
        
    try:
        with open(OLD_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        old_jobs = data.get("jobs", {})
        if not old_jobs:
            logging.info("jobs.json is empty. Nothing to migrate.")
            return
            
        cursor = conn.cursor()
        migrated_count = 0
        
        for k, v in old_jobs.items():
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
                cursor.execute("""
                    INSERT INTO jobs (
                        internal_hash, job_id, title, company, location, url, 
                        date_posted, source_ats, first_seen, status, keywords_matched
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'posted', ?)
                """, (
                    internal_hash,
                    v.get("job_id", ""),
                    v.get("title", ""),
                    v.get("company", ""),
                    v.get("location", ""),
                    v.get("url", ""),
                    v.get("date_posted", ""),
                    v.get("source_ats", ""),
                    v.get("first_seen", datetime.now(timezone.utc).isoformat()),
                    keywords
                ))
                migrated_count += 1
            except sqlite3.IntegrityError:
                pass # Already exists
                
        conn.commit()
        logging.info(f"Migrated {migrated_count} legacy jobs into SQLite as 'posted'.")
        
    except Exception as e:
        logging.error(f"Failed to migrate old JSON data: {e}")

if __name__ == "__main__":
    conn = init_db()
    migrate_old_data(conn)
    conn.close()
