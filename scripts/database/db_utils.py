import sqlite3
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "jobclaw.db"

def get_connection():
    # Because we are using WAL mode, we don't have to worry about intense locking.
    # We still use a 10s timeout just in case it takes a moment.
    return sqlite3.connect(DB_PATH, timeout=10)

def insert_job(conn, job_dict: dict) -> bool:
    """
    Inserts a job into the SQLite DB.
    Returns True if it was a genuinely NEW job (inserted).
    Returns False if it was completely ignored due to our deduplication hash constraint.
    
    If the job already exists (dedup hit), updates last_seen_at and re-activates
    it — this powers the job lifecycle tracker.
    """
    company_norm = job_dict.get("company", "Unknown").lower().strip()
    source_ats = job_dict.get("source_ats", "unknown").lower().strip()
    job_id_norm = str(job_dict.get("job_id", job_dict.get("url", ""))).lower().strip()
    
    internal_hash = f"{source_ats}::{company_norm}::{job_id_norm}"
    
    keywords = json.dumps(job_dict.get("keywords_matched", []))
    first_seen = datetime.now(timezone.utc).isoformat()
    
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
        # Job already exists — update last_seen_at and re-activate
        try:
            cursor.execute("""
                UPDATE jobs 
                SET last_seen_at = ?, is_active = 1 
                WHERE internal_hash = ?
            """, (first_seen, internal_hash))
            
            # Backfill description/salary if we have them now but didn't before
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


def mark_stale_jobs(conn, source_ats: str, company: str, active_job_ids: set[str]) -> int:
    """
    Mark jobs as inactive if they were NOT seen in the latest scrape for this 
    company+ATS combo. This detects deactivated/filled positions.
    
    Returns count of jobs marked inactive.
    """
    if not active_job_ids:
        return 0
    
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.cursor()
    
    company_norm = company.lower().strip()
    ats_norm = source_ats.lower().strip()
    
    # Build the set of hashes that ARE still active
    active_hashes = set()
    for jid in active_job_ids:
        jid_norm = str(jid).lower().strip()
        active_hashes.add(f"{ats_norm}::{company_norm}::{jid_norm}")
    
    # Find all jobs for this company+ats that are currently active
    cursor.execute("""
        SELECT internal_hash FROM jobs 
        WHERE source_ats = ? AND LOWER(company) = ? AND is_active = 1
    """, (ats_norm, company_norm))
    
    all_hashes = {row[0] for row in cursor.fetchall()}
    stale_hashes = all_hashes - active_hashes
    
    if stale_hashes:
        qs = ",".join("?" for _ in stale_hashes)
        cursor.execute(
            f"UPDATE jobs SET is_active = 0, last_seen_at = ? WHERE internal_hash IN ({qs})",
            [now] + list(stale_hashes)
        )
        conn.commit()
    
    return len(stale_hashes)

def get_unposted_jobs(conn):
    """Fetch jobs ready to be sent to Discord."""
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE status = 'unposted' ORDER BY first_seen ASC LIMIT 500")
    
    rows = cursor.fetchall()
    jobs = []
    for r in rows:
        job = dict(r)
        # Parse keywords back into a list
        if job["keywords_matched"]:
            try:
                job["keywords_matched"] = json.loads(job["keywords_matched"])
            except:
                job["keywords_matched"] = []
        jobs.append(job)
    return jobs

def mark_jobs_posted(conn, internal_hashes: list[str]):
    """Update status to posted."""
    if not internal_hashes:
        return
    cursor = conn.cursor()
    # Chunking query
    qs = ",".join("?" for _ in internal_hashes)
    cursor.execute(f"UPDATE jobs SET status = 'posted' WHERE internal_hash IN ({qs})", internal_hashes)
    conn.commit()

def log_scraper_run(conn, script_name: str, companies_fetched: int, new_jobs: int, duration: float, errors: str = None):
    """Log the performance metrics of a micro-scraper."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO runs (script_name, timestamp, companies_fetched, new_jobs_found, duration_s, errors)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        script_name,
        datetime.now(timezone.utc).isoformat(),
        companies_fetched,
        new_jobs,
        duration,
        errors
    ))
    conn.commit()
