"""
ATS Micro-Scraper — v4 with curl_cffi TLS impersonation + bounded worker pool.

Scrapes all companies in config/company_registry.json via their ATS board APIs
(Greenhouse, Lever, Ashby, Workday, Workable, Rippling, SmartRecruiters, BambooHR).

v4 improvements over v3:
  - curl_cffi TLS impersonation: bypasses Cloudflare/WAF on Workday and Workable
  - All 8 ATS platforms now actively scraped (5,000 previously skipped companies unlocked)
  - Bounded worker pool: processes companies in batches via asyncio.Queue
  - Response caching: skips companies whose cache is still fresh (saves 60-80% of requests)
  - Per-host rate limiting: respects each ATS platform's rate limits
  - UA + TLS fingerprint rotation: randomizes per request
  - Job lifecycle tracking: marks vanished jobs as inactive via mark_stale_jobs()
  - Description + salary extraction: stores full job descriptions, extracts salary ranges
  - Per-platform batching: groups companies by ATS for smarter concurrency control
  - Proxy support: reads PROXY_URL from env for rotating proxy pools
"""

import asyncio
import os
import random
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
from scripts.utils.company_metadata import CompanyMetadata
from scripts.utils.retry_queue import RetryQueue
from scripts.utils.health_tracker import HealthTracker
from scripts.ingestion.ats_adapters import fetch_company_jobs, NormalizedJob
from scripts.ingestion.role_filter import matches_target_role
from scripts.ingestion.us_filter import is_us_location
from scripts.ingestion.parallel_ingestor import load_registry, is_within_window
from scripts.database.db_utils import get_connection, insert_job, log_scraper_run, mark_stale_jobs

# ── Platforms to skip by default ───────────────────────────────────────
# v4: Workday and Workable are now scrapable via curl_cffi TLS impersonation.
# Set to empty — all 8 ATS platforms are active.
DEFAULT_SKIP_PLATFORMS: set[str] = set()

# ── Concurrency ───────────────────────────────────────────────────────
# Workers per platform — NOT coroutines-per-platform. Each worker pulls
# from a queue, so memory stays bounded regardless of registry size.
# Workers per platform — lower bounds are better for 24/7 stealth scraping
PLATFORM_WORKERS = {
    "greenhouse": 5,          # Public REST API — very tolerant, increased from 3
    "lever": 5,               # Public REST API — very tolerant, increased from 3
    "ashby": 5,               # Clean API, smaller volume — increased from 3
    "smartrecruiters": 3,     # Enterprise — leave headroom, increased from 2
    "workday": 2,             # Aggressive WAF — don't push past 2-3
    "workable": 1,            # Single worker — Workable 429s hard with concurrency
    "rippling": 2,            # Large registry — careful increase from 1
    "bamboohr": 2,
    "gem": 3,                 # Mid-market ATS — clean JSON API
}
DEFAULT_WORKERS = 3

# ── Circuit Breaker ───────────────────────────────────────────────────
# Lightweight per-platform circuit breaker. No external dependencies.
# If too many consecutive failures happen on a platform, skip remaining
# companies to avoid wasting time on unresponsive hosts.

class CircuitBreaker:
    """Per-platform circuit breaker for ATS scraping.
    
    Opens (skips) after `threshold` consecutive errors on a platform.
    Tracks per-platform failure counts and provides skip decisions.
    """
    
    def __init__(self, threshold: int = 15):
        self.threshold = threshold
        self._failures: dict[str, int] = defaultdict(int)
        self._total_skipped: dict[str, int] = defaultdict(int)
    
    def record_failure(self, platform: str) -> None:
        """Record a failure for a platform."""
        self._failures[platform] += 1
    
    def record_success(self, platform: str) -> None:
        """Reset failure count on success (half-open → closed)."""
        self._failures[platform] = 0
    
    def should_skip(self, platform: str) -> bool:
        """Check if the platform circuit is open (too many failures)."""
        if self._failures[platform] >= self.threshold:
            self._total_skipped[platform] += 1
            return True
        return False
    
    def summary(self) -> str:
        """Log summary of circuit breaker state."""
        opened = {p: f for p, f in self._failures.items() if f >= self.threshold}
        skipped = {p: s for p, s in self._total_skipped.items() if s > 0}
        if opened:
            return f"Circuit breakers OPEN: {opened}, skipped: {skipped}"
        return "All circuit breakers closed (healthy)"



async def _worker(
    name: str,
    queue: asyncio.Queue,
    session,  # curl_cffi AsyncSession or aiohttp ClientSession
    rate_limiter: RateLimiter,
    cache: ResponseCache,
    results: list,
    errors: list,
    circuit_breaker: CircuitBreaker = None,
    company_metadata: CompanyMetadata = None,
    retry_queue: RetryQueue = None,
):
    """
    Worker coroutine: pulls companies from a queue until empty.
    Only N workers run per platform, bounding memory + concurrency.
    
    Uses circuit breaker to skip platforms with too many consecutive failures.
    Uses company_metadata to update scrape history after each company.
    Uses retry_queue to track failures for later retry.
    """
    while True:
        try:
            company = queue.get_nowait()
        except asyncio.QueueEmpty:
            break

        cname = company["company"]
        ats = company["ats"]
        slug = company["slug"]

        # Circuit breaker: skip if platform has too many failures
        if circuit_breaker and circuit_breaker.should_skip(ats):
            queue.task_done()
            continue

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
            # Workday is slow due to JS rendering — give it more time than others
            per_company_timeout = 90 if ats == "workday" else 60
            jobs = await asyncio.wait_for(
                fetch_company_jobs(session, cname, ats, slug, rate_limiter=rate_limiter),
                timeout=per_company_timeout,
            )
            if jobs:
                cache.put(ats, slug, [j.to_dict() for j in jobs])
            results.append((cname, ats, slug, jobs, None))
            if circuit_breaker:
                circuit_breaker.record_success(ats)
            # Update company metadata with scrape results
            if company_metadata:
                job_ids = [j.job_id for j in jobs] if jobs else []
                company_metadata.update_after_scrape(ats, slug, len(jobs), job_ids)
            # Mark success in retry queue (removes from queue if present)
            if retry_queue:
                retry_queue.mark_success(ats, slug)
        except asyncio.TimeoutError:
            _log(f"[{ats}/{slug}] Hard timeout", "WARN")
            results.append((cname, ats, slug, [], "timeout"))
            if circuit_breaker:
                circuit_breaker.record_failure(ats)
            # Add to retry queue
            if retry_queue:
                retry_queue.add_failure(cname, ats, slug, "timeout")
        except Exception as e:
            _log(f"[{ats}/{slug}] Fetch failed: {e}", "ERROR")
            results.append((cname, ats, slug, [], str(e)))
            if circuit_breaker:
                circuit_breaker.record_failure(ats)
            # Add to retry queue
            if retry_queue:
                retry_queue.add_failure(cname, ats, slug, str(e))

        queue.task_done()



async def run_ats_scraper(
    window_hours: int = 24,
    skip_platforms: set = None,
    shard: int = -1,
    total_shards: int = 4,
):
    """
    Micro-scraper exclusively for Direct ATS APIs (Greenhouse, Lever, etc.)
    
    Pipeline:
      1. Load registry (~11,800 companies)
      2. Apply shard filter (optional: split registry into N rotating chunks)
      3. Group by ATS platform → build per-platform queues
      4. Launch N workers per platform (bounded, NOT 11,800 coroutines)
      5. Fetch with caching + rate limiting + TLS fingerprint rotation
      6. Filter: target role → US location → time window
      7. Insert into SQLite with description + salary enrichment
      8. Mark vanished jobs as inactive (lifecycle tracking)

    Args:
        window_hours: Time window for filtering (default 24h)
        skip_platforms: Set of platform names to skip (default: none)
        shard: Which shard to process (0 to total_shards-1).
               -1 = auto-detect based on current 15-minute time slot.
               None = no sharding (process entire registry).
        total_shards: Number of shards to split registry into (default 4).
    """
    start_time = time.time()
    _log(">>> Starting ATS Micro-Scraper v4 (curl_cffi TLS impersonation)")

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

    # ── Registry Sharding ──────────────────────────────────────────────
    # Split 10k+ companies into N rotating shards for shorter runs.
    # Auto-shard selects based on the current 15-min time slot.
    if shard is not None:
        if shard == -1:
            # Auto-detect shard from current time
            import datetime
            now_min = datetime.datetime.now().minute
            shard = (now_min // 15) % total_shards
        
        chunk_size = len(registry) // total_shards
        remainder = len(registry) % total_shards
        start_idx = shard * chunk_size + min(shard, remainder)
        end_idx = start_idx + chunk_size + (1 if shard < remainder else 0)
        registry = registry[start_idx:end_idx]
        _log(f"Shard {shard}/{total_shards}: processing {len(registry)} companies (of {before_count - skipped} total)")

    _log(f"Loaded {len(registry)} companies for ATS ingestion (from {before_count} total).")

    # Initialize shared infrastructure
    rate_limiter = RateLimiter()
    cache = ResponseCache()
    breaker = CircuitBreaker(threshold=15)
    company_metadata = CompanyMetadata()
    retry_queue = RetryQueue()
    health_tracker = HealthTracker()
    health_tracker.start_run()

    # ── Process Retry Queue ───────────────────────────────────────────
    # Get companies that are ready for retry and add them to the scrape list.
    retry_companies = retry_queue.get_ready_retries()
    if retry_companies:
        _log(f"Retry queue: {len(retry_companies)} companies ready for retry")
        # Merge with registry (avoid duplicates)
        existing_keys = {f"{c['ats']}:{c['slug']}" for c in registry}
        for rc in retry_companies:
            key = f"{rc['ats']}:{rc['slug']}"
            if key not in existing_keys:
                registry.append(rc)
    _log(retry_queue.get_queue_summary())

    # ── Skip Unchanged Companies ──────────────────────────────────────
    # Filter out companies that were recently scraped and haven't changed.
    # This is the biggest optimization: 12k → ~2-3k companies per cycle.
    companies_to_scrape = []
    for c in registry:
        should_scrape, reason = company_metadata.should_scrape(c["ats"], c["slug"])
        if should_scrape:
            companies_to_scrape.append(c)
    
    skip_stats = company_metadata.get_stats()
    _log(f"Skip-unchanged filter: {skip_stats['skipped']}/{skip_stats['checked']} skipped "
         f"({skip_stats['skip_rate']}), {len(companies_to_scrape)} to scrape")

    # Group companies by ATS platform (including Workday → WorkdayAdapter)
    by_platform = defaultdict(list)
    for c in companies_to_scrape:
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
        # Shuffle companies within each platform for randomization (stealth)
        worker_tasks = []
        for platform, companies in by_platform.items():
            # Shuffle to avoid predictable scraping patterns
            random.shuffle(companies)
            
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
                        circuit_breaker=breaker,
                        company_metadata=company_metadata,
                        retry_queue=retry_queue,
                    )
                )
                worker_tasks.append(task)

        # Wait for all workers to drain their queues
        await asyncio.gather(*worker_tasks, return_exceptions=True)

    # Save company metadata after scraping
    company_metadata.save()
    final_stats = company_metadata.get_stats()
    _log(f"Company metadata: {final_stats['scraped']} companies scraped, metadata saved")

    # Save retry queue and log stats
    retry_queue.save()
    retry_stats = retry_queue.get_stats()
    _log(f"Retry queue: added={retry_stats['added']}, retried={retry_stats['retried']}, "
         f"success={retry_stats['success']}, dropped={retry_stats['dropped']}, "
         f"queue_size={retry_stats['queue_size']}")

    # Log circuit breaker health
    _log(f"Circuit breaker: {breaker.summary()}")

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

    # Always apply time filter — on GitHub Actions the DB is ephemeral,
    # so "first run" detection doesn't make sense for CI.
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

    # ── Health Tracking ───────────────────────────────────────────────
    # Record run metrics for monitoring and alerts
    error_counts = {}
    for err in errors:
        # Categorize errors
        if "429" in err or "rate" in err.lower():
            error_counts["429"] = error_counts.get("429", 0) + 1
        elif "timeout" in err.lower():
            error_counts["timeout"] = error_counts.get("timeout", 0) + 1
        else:
            error_counts["other"] = error_counts.get("other", 0) + 1
    
    health_tracker.end_run(
        companies_scraped=final_stats["scraped"],
        companies_skipped=skip_stats["skipped"],
        jobs_found=len(all_jobs),
        new_jobs=new_jobs_inserted,
        errors=error_counts,
        retry_queue_size=retry_stats["queue_size"],
    )
    
    # Check for alerts
    alerts = health_tracker.get_alerts()
    if alerts:
        for alert in alerts:
            level = "ERROR" if alert["level"] == "critical" else "WARN"
            _log(f"HEALTH ALERT: {alert['message']}", level)

    _log(
        f">>> ATS Scraper Complete. "
        f"New={new_jobs_inserted}, Candidates={len(time_filtered)}, "
        f"Errors={len(errors)}, Duration={duration}s"
    )

    return {"workday_companies": []}


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_ats_scraper(24))
