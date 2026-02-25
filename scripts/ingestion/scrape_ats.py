import asyncio
import aiohttp
import time
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.logger import _log
from scripts.ingestion.ats_adapters import fetch_company_jobs
from scripts.ingestion.role_filter import matches_target_role
from scripts.ingestion.us_filter import is_us_location
from scripts.ingestion.parallel_ingestor import load_registry, is_within_window
from scripts.database.db_utils import get_connection, insert_job, log_scraper_run

MAX_CONCURRENT = 50
MAX_RETRIES = 2
RETRY_DELAY = 1.0

async def _fetch_with_retry(session: aiohttp.ClientSession, semaphore: asyncio.Semaphore, company: dict) -> tuple:
    name = company["company"]
    ats = company["ats"]
    slug = company["slug"]

    async with semaphore:
        for attempt in range(MAX_RETRIES + 1):
            try:
                jobs = await fetch_company_jobs(session, name, ats, slug)
                return (name, jobs, None)
            except Exception as e:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    return (name, [], str(e))
    return (name, [], "Max retries exceeded")

async def run_ats_scraper(window_hours: int = 24):
    """
    Micro-scraper exclusively for Direct ATS APIs (Greenhouse, Lever, etc.)
    Designed to run fast and concurrently.
    """
    start_time = time.time()
    _log(">>> Starting ATS Micro-Scraper")
    
    registry = load_registry()
    if not registry:
        _log("Empty registry — nothing to ingest.", "WARN")
        return

    _log(f"Loaded {len(registry)} companies for ATS ingestion.")
    
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, limit_per_host=5)
    
    all_jobs = []
    errors = []
    
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [_fetch_with_retry(session, semaphore, c) for c in registry]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for res in results:
            if isinstance(res, Exception):
                errors.append(str(res))
                continue
            name, jobs, err = res
            if err:
                errors.append(f"{name}: {err}")
            all_jobs.extend(jobs)
            
    _log(f"Fetched {len(all_jobs)} total raw jobs from ATS APIs.")
    
    # Filtering Phase
    role_filtered = [j for j in all_jobs if matches_target_role(j.title)]
    _log(f"Role filter: {len(role_filtered)}/{len(all_jobs)} matched target tech roles.")
    
    us_filtered = [j for j in role_filtered if is_us_location(j.location)]
    _log(f"US filter: {len(us_filtered)}/{len(role_filtered)} in United States.")
    
    time_filtered = [j for j in us_filtered if is_within_window(j.date_posted, window_hours)]
    _log(f"{window_hours}hr filter: {len(time_filtered)}/{len(us_filtered)} within window.")
    
    # Native SQLite Database Injection + WAL Deduplication
    conn = get_connection()
    new_jobs_inserted = 0
    try:
        for job in time_filtered:
            # Converting to dictionary for insertion
            j_dict = {
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "url": job.url,
                "date_posted": job.date_posted,
                "source_ats": job.source_ats,
                "job_id": job.job_id,
                "keywords_matched": job.keywords_matched,
            }
            is_new = insert_job(conn, j_dict)
            if is_new:
                new_jobs_inserted += 1
                
    except Exception as e:
        _log(f"Database insertion error: {str(e)}", "ERROR")
        errors.append(str(e))
        
    duration = round(time.time() - start_time, 2)
    
    # Log the system health metrics to SQL
    err_str = "; ".join(errors) if errors else ""
    try:
        log_scraper_run(conn, "scrape_ats", len(registry), new_jobs_inserted, duration, err_str)
    finally:
        conn.close()
    
    _log(f">>> ATS Scraper Complete. Found {new_jobs_inserted} brand new jobs out of {len(time_filtered)} candidates. (Took {duration}s)")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_ats_scraper(24))
