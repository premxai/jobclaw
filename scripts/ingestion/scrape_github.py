import asyncio
import aiohttp
import time
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.logger import _log
from scripts.ingestion.github_parser import fetch_all_github_repos
from scripts.ingestion.role_filter import matches_target_role
from scripts.ingestion.us_filter import is_us_location
from scripts.ingestion.parallel_ingestor import is_within_window
from scripts.database.db_utils import get_connection, insert_job, log_scraper_run

async def run_github_scraper(window_hours: int = 24):
    """
    Micro-scraper exclusively for parsing Markdown tables and JSON lists in GitHub repositories.
    """
    start_time = time.time()
    _log(">>> Starting GitHub Repos Micro-Scraper")
    
    all_jobs = []
    errors = []
    
    try:
        async with aiohttp.ClientSession() as session:
            repos_jobs, scrape_errors = await fetch_all_github_repos(session)
            all_jobs.extend(repos_jobs)
            errors.extend(scrape_errors)
            _log(f"Fetched {len(repos_jobs)} total raw jobs from GitHub repos.")
    except Exception as e:
        _log(f"GitHub Scrape Error: {e}", "ERROR")
        errors.append(str(e))
    
    if not all_jobs:
        _log("No jobs found on GitHub repos.", "WARN")
        return

    # Filtering Phase
    role_filtered = [j for j in all_jobs if matches_target_role(j.title)]
    _log(f"Role filter: {len(role_filtered)}/{len(all_jobs)} matched target tech roles.")
    
    us_filtered = [j for j in role_filtered if is_us_location(j.location)]
    _log(f"US filter: {len(us_filtered)}/{len(role_filtered)} in United States.")
    
    # We use a longer window for GitHub by default since PRs get merged in batches
    # We'll stick to the requested window though to keep deduplication standard
    time_filtered = [j for j in us_filtered if is_within_window(j.date_posted, window_hours)]
    _log(f"{window_hours}hr filter: {len(time_filtered)}/{len(us_filtered)} within window.")
    
    # Database injection + Deduplication
    conn = get_connection()
    new_jobs_inserted = 0
    try:
        for job in time_filtered:
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
            if insert_job(conn, j_dict):
                new_jobs_inserted += 1
                
    except Exception as e:
        _log(f"Database insertion error: {str(e)}", "ERROR")
        errors.append(str(e))
        
    duration = round(time.time() - start_time, 2)
    err_str = "; ".join(errors) if errors else ""
    try:
        log_scraper_run(conn, "scrape_github", 6, new_jobs_inserted, duration, err_str) # 6 hardcoded repos
    finally:
        conn.close()
    
    _log(f">>> GitHub Scraper Complete. Found {new_jobs_inserted} brand new jobs out of {len(time_filtered)} candidates. (Took {duration}s)")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # We run GitHub defaults with 72hr windows locally just in case since they are slower to update
    asyncio.run(run_github_scraper(24))
