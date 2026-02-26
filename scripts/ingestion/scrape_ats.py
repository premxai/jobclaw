"""
ATS Micro-Scraper — v3 with bounded worker pool, caching, rate limiting & lifecycle tracking.

Scrapes all companies in config/company_registry.json via their ATS board APIs
(Greenhouse, Lever, Ashby, Workday, Workable, Rippling, SmartRecruiters, BambooHR).

v3 improvements over v2:
  - Bounded worker pool: processes companies in batches instead of launching 11,800
    coroutines at once. Uses asyncio.Queue with a fixed number of workers per platform.
  - Response caching: skips companies whose cache is still fresh (saves 60-80% of requests)
  - Per-host rate limiting: respects each ATS platform's rate limits
  - UA rotation: randomizes User-Agent per request
  - Job lifecycle tracking: marks vanished jobs as inactive via mark_stale_jobs()
  - Description + salary extraction: stores full job descriptions, extracts salary ranges
  - Per-platform batching: groups companies by ATS for smarter concurrency control
  - Proxy support: reads PROXY_URL from env for rotating proxy pools
"""

import asyncio
import aiohttp
import os
import time
import sys
from collections import defaultdict
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.logger import _log
from scripts.utils.http_client import RateLimiter, create_session
from scripts.utils.response_cache import ResponseCache
from scripts.ingestion.ats_adapters import fetch_company_jobs, NormalizedJob
from scripts.ingestion.role_filter import matches_target_role
from scripts.ingestion.us_filter import is_us_location
from scripts.ingestion.parallel_ingestor import load_registry, is_within_window
from scripts.database.db_utils import get_connection, insert_job, log_scraper_run, mark_stale_jobs

# ── Platforms to skip by default ───────────────────────────────────────
# Workable: 3,547 companies, 429 rate-limits on EVERY request (unusable without proxy)
# Workday: 1,404 companies, most slugs return 422 (wrong format in registry)
DEFAULT_SKIP_PLATFORMS = {"workable", "workday"}

# ── Concurrency ───────────────────────────────────────────────────────
# Workers per platform — NOT coroutines-per-platform. Each worker pulls
# from a queue, so memory stays bounded regardless of registry size.
PLATFORM_WORKERS = {
    "greenhouse": 20,       # Public API, very tolerant
    "lever": 15,             # Public API, tolerant
    "ashby": 15,             # Public API, tolerant
    "smartrecruiters": 10,
    "workday": 5,            # Aggressive WAF — don't push past 5
    "workable": 10,
    "rippling": 10,
    "bamboohr": 8,
}
DEFAULT_WORKERS = 8


async def _worker(
    name: str,
    queue: asyncio.Queue,
    session: aiohttp.ClientSession,
    rate_limiter: RateLimiter,
    cache: ResponseCache,
    results: list,
    errors: list,
):
    """
    Worker coroutine: pulls companies from a queue until empty.
    Only N workers run per platform, bounding memory + concurrency.
    """
    while True:
        try:
            company = queue.get_nowait()
        except asyncio.QueueEmpty:
            break

        cname = company["company"]
        ats = company["ats"]
        slug = company["slug"]

        # Check cache first
        cached_data = cache.get(ats, slug)
        if cached_data is not None:
            try:
                jobs = [NormalizedJob(**j) for j in cached_data]
                results.append((cname, ats, slug, jobs, None))
                queue.task_done()
                continue
            except Exception:
                pass  # Cache corrupt — fall through

        try:
            jobs = await asyncio.wait_for(
                fetch_company_jobs(session, cname, ats, slug, rate_limiter=rate_limiter),
                timeout=60,  # 60s max per company — prevents infinite hangs
            )
            if jobs:
                cache.put(ats, slug, [j.to_dict() for j in jobs])
            results.append((cname, ats, slug, jobs, None))
        except asyncio.TimeoutError:
            _log(f"[{ats}/{slug}] Hard timeout after 60s", "WARN")
            results.append((cname, ats, slug, [], "timeout"))
        except Exception as e:
            _log(f"[{ats}/{slug}] Fetch failed: {e}", "ERROR")
            results.append((cname, ats, slug, [], str(e)))

        queue.task_done()


async def run_ats_scraper(window_hours: int = 24, skip_platforms: set = None):
    """
    Micro-scraper exclusively for Direct ATS APIs (Greenhouse, Lever, etc.)
    
    Pipeline:
      1. Load registry (~11,800 companies)
      2. Filter out broken/rate-limited platforms (Workable, Workday)
      3. Group by ATS platform → build per-platform queues
      4. Launch N workers per platform (bounded, NOT 11,800 coroutines)
      5. Fetch with caching + rate limiting + UA rotation
      6. Filter: target role → US location → time window
      7. Insert into SQLite with description + salary enrichment
      8. Mark vanished jobs as inactive (lifecycle tracking)
    """
    start_time = time.time()
    _log(">>> Starting ATS Micro-Scraper v3")

    if skip_platforms is None:
        skip_platforms = DEFAULT_SKIP_PLATFORMS

    registry = load_registry()
    if not registry:
        _log("Empty registry — nothing to ingest.", "WARN")
        return

    # Filter out broken/rate-limited platforms
    before_count = len(registry)
    registry = [c for c in registry if c.get("ats", "").lower() not in skip_platforms]
    skipped = before_count - len(registry)
    if skipped:
        _log(f"Skipping {skipped} companies on platforms: {', '.join(sorted(skip_platforms))}")

    _log(f"Loaded {len(registry)} companies for ATS ingestion (from {before_count} total).")

    # Initialize shared infrastructure
    rate_limiter = RateLimiter()
    cache = ResponseCache()

    # Group companies by ATS platform
    by_platform = defaultdict(list)
    for c in registry:
        by_platform[c["ats"]].append(c)

    platform_summary = ", ".join(f"{k}={len(v)}" for k, v in sorted(by_platform.items()))
    _log(f"Platform breakdown: {platform_summary}")

    all_results = []
    errors = []

    # Proxy support: set PROXY_URL in env for rotating proxies
    proxy = os.environ.get("PROXY_URL")
    if proxy:
        _log(f"Using proxy: {proxy[:30]}...")

    async with create_session(rate_limiter, proxy=proxy) as session:
        # Build per-platform queues and launch bounded workers
        worker_tasks = []
        for platform, companies in by_platform.items():
            q = asyncio.Queue()
            for c in companies:
                q.put_nowait(c)

            num_workers = PLATFORM_WORKERS.get(platform, DEFAULT_WORKERS)
            for i in range(num_workers):
                task = asyncio.create_task(
                    _worker(
                        f"{platform}-worker-{i}",
                        q, session, rate_limiter, cache,
                        all_results, errors,
                    )
                )
                worker_tasks.append(task)

        # Wait for all workers to drain their queues
        await asyncio.gather(*worker_tasks, return_exceptions=True)

    # Flatten jobs + collect lifecycle data
    all_jobs = []
    company_job_ids = defaultdict(set)  # (ats, company) → {job_id, ...}

    for name, ats, slug, jobs, err in all_results:
        if err:
            errors.append(f"{name}: {err}")
        for job in jobs:
            all_jobs.append(job)
            company_job_ids[(ats, name)].add(job.job_id)

    cache.log_stats()
    _log(f"Fetched {len(all_jobs)} total raw jobs from ATS APIs.")

    # ── Filtering Pipeline ────────────────────────────────────────────
    role_filtered = [j for j in all_jobs if matches_target_role(j.title)]
    _log(f"Role filter: {len(role_filtered)}/{len(all_jobs)} matched target tech roles.")

    us_filtered = [j for j in role_filtered if is_us_location(j.location)]
    _log(f"US filter: {len(us_filtered)}/{len(role_filtered)} in United States.")

    # On first run (empty DB), skip time filter to get ALL active jobs.
    # On subsequent runs, only take jobs within the window.
    conn_check = get_connection()
    existing_count = conn_check.cursor().execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    conn_check.close()

    if existing_count == 0:
        _log(f"First run detected (empty DB) — skipping time window filter, taking all {len(us_filtered)} US tech jobs.")
        time_filtered = us_filtered
    else:
        time_filtered = [j for j in us_filtered if is_within_window(j.date_posted, window_hours)]
        _log(f"{window_hours}hr filter: {len(time_filtered)}/{len(us_filtered)} within window.")

    # ── Database Insertion ────────────────────────────────────────────
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
                "description": job.description,
                "salary_min": job.salary_min,
                "salary_max": job.salary_max,
                "salary_currency": job.salary_currency,
                "experience_years": job.experience_years,
            }
            is_new = insert_job(conn, j_dict)
            if is_new:
                new_jobs_inserted += 1

        # ── Job Lifecycle Tracking ────────────────────────────────────
        # For companies we successfully fetched, mark any jobs that
        # disappeared from the API as inactive (filled/removed).
        stale_total = 0
        for (ats, company_name), job_ids in company_job_ids.items():
            stale_count = mark_stale_jobs(conn, ats, company_name, job_ids)
            stale_total += stale_count

        if stale_total > 0:
            _log(f"Lifecycle: marked {stale_total} jobs as inactive (no longer on ATS).")

    except Exception as e:
        _log(f"Database insertion error: {str(e)}", "ERROR")
        errors.append(str(e))

    duration = round(time.time() - start_time, 2)

    # Log system health metrics
    err_str = "; ".join(errors[:20]) if errors else ""  # Cap error string length
    try:
        log_scraper_run(conn, "scrape_ats", len(registry), new_jobs_inserted, duration, err_str)
    finally:
        conn.close()

    _log(
        f">>> ATS Scraper Complete. "
        f"New={new_jobs_inserted}, Candidates={len(time_filtered)}, "
        f"Errors={len(errors)}, Duration={duration}s"
    )


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_ats_scraper(24))
