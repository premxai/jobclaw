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
import json
import os
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.database.db_utils import (
    claim_adaptive_companies_for_scrape,
    get_connection,
    insert_job,
    is_postgres,
    log_scraper_run,
    mark_stale_jobs,
    get_companies_by_tier,
    get_companies_for_scrape,
    get_due_companies_for_scrape,
    release_company_leases,
    clear_company_validated_metadata_key,
    update_company_last_scraped,
    update_company_validated_metadata,
)
from scripts.ingestion.ats_adapters import NormalizedJob, consume_target_metadata, fetch_company_jobs
from scripts.ingestion.parallel_ingestor import is_within_window
from scripts.ingestion.role_filter import matches_target_role
from scripts.ingestion.us_filter import is_us_location
from scripts.utils.company_metadata import CompanyMetadata
from scripts.utils.health_tracker import HealthTracker
from scripts.utils.http_client import RateLimiter, consume_last_failure, create_session, set_response_cache
from scripts.utils.logger import _log
from scripts.utils.platform_budgets import (
    DEFAULT_WORKERS,
    PLATFORM_WORKERS,
    apply_platform_budgets,
    platform_target_cap,
)
from scripts.utils.response_cache import ResponseCache
from scripts.utils.retry_queue import RetryQueue
from scripts.utils.target_diagnostics import apply_cached_target_metadata, classify_failure

# ── Platforms to skip by default ───────────────────────────────────────
# v4: Workday and Workable are now scrapable via curl_cffi TLS impersonation.
# Set to empty — all 8 ATS platforms are active.
DEFAULT_SKIP_PLATFORMS: set[str] = set()

# ── Concurrency ───────────────────────────────────────────────────────
# Workers per platform — NOT coroutines-per-platform. Each worker pulls
# from a queue, so memory stays bounded regardless of registry size.
# Workers per platform — lower bounds are better for 24/7 stealth scraping
QUEUE_MODES = {"shadow", "active"}


def _queue_mode() -> str:
    mode = os.getenv("JOBCLAW_QUEUE_MODE", "active").strip().lower()
    return mode if mode in QUEUE_MODES else "off"


def _target_key(target: dict) -> str:
    return f"{str(target.get('ats') or '').lower()}:{target.get('slug') or ''}"


def _load_previous_selected_keys(conn) -> set[str]:
    """Load selected target keys from the most recent ATS run summary."""
    cursor = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"
    try:
        cursor.execute(
            f"""
            SELECT summary_json
            FROM scraper_runs
            WHERE scraper = {placeholder}
              AND COALESCE(summary_json, '') <> ''
            ORDER BY run_at DESC, id DESC
            LIMIT 5
            """,
            ("scrape_ats",),
        )
        for row in cursor.fetchall():
            raw = row[0] if not isinstance(row, dict) else row.get("summary_json")
            if not raw:
                continue
            try:
                summary = json.loads(raw)
            except Exception:
                continue
            selected = summary.get("queue", {}).get("selected_keys") or []
            if selected:
                return set(str(k) for k in selected)
    except Exception:
        return set()
    return set()


def _platform_claim_multiplier() -> int:
    return max(1, int(os.getenv("JOBCLAW_PLATFORM_CLAIM_MULTIPLIER", "4")))


def _claim_active_targets_by_platform(
    conn,
    target_limit: int,
    platforms: set[str] | None,
    lease_owner: str,
    lease_seconds: int,
) -> tuple[list[dict], dict[str, int]]:
    """Claim due targets fairly across requested platforms before budgeting.

    A global claim can be dominated by one high-score platform. Claiming a
    multiple of each platform's budget cap first gives every requested ATS a
    chance, while apply_platform_budgets still controls final request volume.
    """
    if not platforms or len(platforms) <= 1:
        rows = claim_adaptive_companies_for_scrape(
            conn,
            limit=target_limit,
            platforms=platforms,
            lease_owner=lease_owner,
            lease_seconds=lease_seconds,
            include_not_due=False,
        )
        key = next(iter(platforms)) if platforms and len(platforms) == 1 else "all"
        return rows, {str(key): len(rows)}

    multiplier = _platform_claim_multiplier()
    registry: list[dict] = []
    claim_counts: dict[str, int] = {}
    for platform in sorted(str(p).lower() for p in platforms):
        claim_limit = min(target_limit, platform_target_cap(platform) * multiplier)
        claimed = claim_adaptive_companies_for_scrape(
            conn,
            limit=claim_limit,
            platforms={platform},
            lease_owner=lease_owner,
            lease_seconds=lease_seconds,
            include_not_due=False,
        )
        registry.extend(claimed)
        claim_counts[platform] = len(claimed)
    return registry, claim_counts


# ── Circuit Breaker ───────────────────────────────────────────────────
# Lightweight per-platform circuit breaker. No external dependencies.
# If too many consecutive failures happen on a platform, skip remaining
# companies to avoid wasting time on unresponsive hosts.


class CircuitBreaker:
    """Per-platform circuit breaker for ATS scraping.

    Opens (skips) after `threshold` consecutive errors on a platform.
    Tracks per-platform failure counts and provides skip decisions.
    Instead of skipping ALL remaining companies once open, skips only the
    next 50 companies (half-open cooldown) before retrying.
    """

    # Persisted state so a platform banned on one (ephemeral) runner stays tripped on
    # the next run instead of wasting `threshold` requests re-discovering the ban.
    STATE_PATH = Path(__file__).resolve().parent.parent.parent / "state" / "circuit_breaker.json"
    RECOVERY_SECONDS = int(os.getenv("JOBCLAW_CIRCUIT_RECOVERY_SECONDS", "3600"))

    def __init__(self, threshold: int = 15, state_path: Path | None = None):
        self.threshold = threshold
        self.state_path = state_path or self.STATE_PATH
        self._failures: dict[str, int] = defaultdict(int)
        self._total_skipped: dict[str, int] = defaultdict(int)
        self._skip_remaining: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}  # platform -> epoch when circuit opened
        self._load()

    def _load(self) -> None:
        """Restore platforms still inside their recovery window as open (skip them)."""
        try:
            if not self.state_path.exists():
                return
            with open(self.state_path, encoding="utf-8") as f:
                data = json.load(f)
            now = time.time()
            for platform, st in (data.get("open") or {}).items():
                opened_at = float(st.get("opened_at") or 0)
                if now - opened_at < self.RECOVERY_SECONDS:
                    self._failures[platform] = int(st.get("failures") or self.threshold)
                    self._opened_at[platform] = opened_at
                    # Skip this platform for the remainder of the run; recovery is
                    # time-based and re-evaluated on the next run's _load().
                    self._skip_remaining[platform] = 10**9
        except Exception:
            pass  # never let breaker state corruption break a scrape run

    def save(self) -> None:
        """Persist currently-open platforms (failures >= threshold)."""
        try:
            now = time.time()
            open_state = {
                p: {"failures": f, "opened_at": self._opened_at.get(p, now)}
                for p, f in self._failures.items()
                if f >= self.threshold
            }
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"_comment": "Open ATS circuit breakers (persisted across runs)", "open": open_state}
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass

    def record_failure(self, platform: str) -> None:
        """Record a failure for a platform."""
        self._failures[platform] += 1
        if self._failures[platform] >= self.threshold and platform not in self._skip_remaining:
            self._skip_remaining[platform] = 50
            self._opened_at[platform] = time.time()

    def record_success(self, platform: str) -> None:
        """Reset failure count on success (half-open → closed)."""
        self._failures[platform] = 0
        self._skip_remaining.pop(platform, None)
        self._opened_at.pop(platform, None)

    def should_skip(self, platform: str) -> bool:
        """Check if the platform circuit is open (too many failures).

        Returns True only for the next 50 companies after the circuit opens,
        then allows retries (half-open behaviour).
        """
        remaining = self._skip_remaining.get(platform, 0)
        if remaining > 0:
            self._skip_remaining[platform] = remaining - 1
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
        canonical_ats = company["ats"]
        canonical_slug = company["slug"]
        ats, slug, used_cached_metadata = apply_cached_target_metadata(company)

        # Circuit breaker: skip if platform is in half-open cooldown
        if circuit_breaker and circuit_breaker.should_skip(ats):
            remaining = circuit_breaker._skip_remaining.get(ats, 0)
            _log(f"Circuit half-open for {ats}: skipping {cname} (remaining: {remaining})", "DEBUG")
            queue.task_done()
            continue

        # Check cache first
        cached_data = cache.get(ats, slug)
        if cached_data is not None:
            try:
                jobs = [NormalizedJob(**j) for j in cached_data]
                results.append((cname, canonical_ats, canonical_slug, jobs, None, None, None))
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
            failure = consume_last_failure()
            target_metadata = consume_target_metadata()
            if used_cached_metadata:
                target_metadata = dict(target_metadata or {})
                target_metadata["_used_cached_metadata"] = True
            if jobs:
                cache.put(ats, slug, [j.to_dict() for j in jobs])
            results.append((cname, canonical_ats, canonical_slug, jobs, None, failure, target_metadata))
            if circuit_breaker:
                circuit_breaker.record_success(ats)
            if used_cached_metadata:
                _log(f"[{canonical_ats}/{canonical_slug}] Used cached target {ats}/{slug}", "DEBUG")
            # Update company metadata with scrape results
            if company_metadata and jobs:
                job_ids = [j.job_id for j in jobs] if jobs else []
                company_metadata.update_after_scrape(canonical_ats, canonical_slug, len(jobs), job_ids)
            # Mark success in retry queue only for clean runs.
            if retry_queue and jobs and not failure:
                retry_queue.mark_success(canonical_ats, canonical_slug)
        except TimeoutError:
            failure = classify_failure(error="timeout", ats=ats, slug=slug)
            _log(f"[{ats}/{slug}] Hard timeout", "WARN")
            results.append((cname, canonical_ats, canonical_slug, [], "timeout", failure, None))
            if circuit_breaker:
                circuit_breaker.record_failure(ats)
            # Add to retry queue
            if retry_queue:
                retry_queue.add_failure(
                    cname, canonical_ats, canonical_slug, "timeout", failure_type=failure["category"], status_code=None
                )
        except Exception as e:
            failure = consume_last_failure() or classify_failure(error=e, ats=ats, slug=slug)
            _log(
                f"[{ats}/{slug}] Fetch failed: {failure['category']}:{failure.get('status_code') or 'n/a'}:{failure.get('error') or e}",
                "ERROR",
            )
            results.append((cname, canonical_ats, canonical_slug, [], str(e), failure, None))
            if circuit_breaker:
                circuit_breaker.record_failure(ats)
            # Add to retry queue
            if retry_queue:
                retry_queue.add_failure(
                    cname,
                    canonical_ats,
                    canonical_slug,
                    str(e),
                    failure_type=failure["category"],
                    status_code=failure.get("status_code"),
                    retry_after=failure.get("retry_after"),
                )

        queue.task_done()


async def run_ats_scraper(
    window_hours: int = 24,
    skip_platforms: set = None,
    shard: int = -1,
    total_shards: int = 4,
    tier: str = None,
    platforms: set = None,
    due_only: bool = True,
    target_limit: int = None,
):
    """
    Micro-scraper exclusively for Direct ATS APIs (Greenhouse, Lever, etc.)

    Pipeline:
      1. Load registry (~11,800 companies)
      2. Apply platform filter (optional: restrict to specific ATS types)
      3. Apply shard filter (optional: split registry into N rotating chunks)
      4. Group by ATS platform → build per-platform queues
      5. Launch N workers per platform (bounded, NOT 11,800 coroutines)
      6. Fetch with caching + rate limiting + TLS fingerprint rotation
      7. Filter: target role → US location → time window
      8. Insert into SQLite with description + salary enrichment
      9. Mark vanished jobs as inactive (lifecycle tracking)

    Args:
        window_hours: Time window for filtering (default 24h)
        skip_platforms: Set of platform names to skip (default: none)
        shard: Which shard to process (0 to total_shards-1).
               -1 = auto-detect based on current 15-minute time slot.
               None = no sharding (process entire registry).
        total_shards: Number of shards to split registry into (default 4).
        tier: Optional DB tier to fetch (P0, P1, P2). Kept for manual compatibility.
        platforms: Whitelist of ATS platform names to include (e.g. {"greenhouse", "lever"}).
                   None = all platforms. Used to bucket platforms by speed/tier.
        due_only: Prefer targets whose next_scrape_at is due. Disable only for manual full sweeps.
        target_limit: Maximum due targets to claim in one run. Defaults from JOBCLAW_ATS_TARGET_LIMIT.
    """
    start_time = time.time()
    _log(">>> Starting ATS Micro-Scraper v4 (curl_cffi TLS impersonation)")

    if skip_platforms is None:
        skip_platforms = DEFAULT_SKIP_PLATFORMS

    queue_mode = _queue_mode()
    lease_owner = f"ats:{os.getpid()}:{int(start_time)}"
    queue_metrics = {
        "mode": queue_mode,
        "lease_owner": lease_owner if queue_mode == "active" else "",
        "claimed": 0,
        "claimed_sample": [],
        "released_skipped": 0,
        "budget_dropped": 0,
        "budgets": {},
        "selected_keys": [],
        "selected_sample": [],
        "deferred_sample": [],
        "previous_overlap": 0,
        "previous_overlap_sample": [],
    }

    conn = get_connection()
    try:
        if target_limit is None:
            target_limit = int(os.getenv("JOBCLAW_ATS_TARGET_LIMIT", "3000"))

        if due_only and queue_mode == "active":
            lease_seconds = int(os.getenv("JOBCLAW_QUEUE_LEASE_SECONDS", "300"))
            registry, claim_by_platform = _claim_active_targets_by_platform(
                conn,
                target_limit,
                platforms,
                lease_owner,
                lease_seconds,
            )
            queue_metrics["claimed"] = len(registry)
            queue_metrics["claim_by_platform"] = claim_by_platform
            queue_metrics["claimed_sample"] = [_target_key(c) for c in registry[:20]]
            _log(
                f"Claimed {len(registry)} adaptive queue companies "
                f"(limit={target_limit}, lease={lease_seconds}s, platforms={sorted(platforms) if platforms else 'ALL'}, "
                f"by_platform={claim_by_platform})."
            )
        elif due_only:
            registry = get_due_companies_for_scrape(
                conn,
                limit=target_limit,
                platforms=platforms,
                include_not_due=False,
            )
            _log(
                f"Fetched {len(registry)} due canonical companies from DB "
                f"(limit={target_limit}, platforms={sorted(platforms) if platforms else 'ALL'})."
            )
        elif tier and tier in {"P0", "P1", "P2", "P3"}:
            registry = get_companies_by_tier(conn, tier, shard, total_shards)
            _log(f"Fetched {len(registry)} companies for Tier {tier} (Shard {shard}/{total_shards}) from DB.")
            shard = None  # DB tier helper already applied sharding
        else:
            registry = get_companies_for_scrape(conn, shard=shard, total_shards=total_shards, platforms=platforms)
            _log(
                f"Fetched {len(registry)} canonical companies from DB "
                f"(Shard {shard}/{total_shards} if set, platforms={sorted(platforms) if platforms else 'ALL'})."
            )
    finally:
        conn.close()

    if not registry and due_only:
        conn = get_connection()
        try:
            existing = get_due_companies_for_scrape(
                conn,
                limit=1,
                platforms=platforms,
                include_not_due=True,
            )
        finally:
            conn.close()
        if existing:
            _log("No canonical companies are due for ATS ingestion right now.")
            return

    if not registry:
        _log("Canonical companies table is empty — seeding from config/company_registry.json.", "WARN")
        from scripts.database.seed_companies import seed_companies

        seed_companies()
        conn = get_connection()
        try:
            if due_only:
                registry = get_due_companies_for_scrape(
                    conn,
                    limit=target_limit,
                    platforms=platforms,
                    include_not_due=False,
                )
            elif tier and tier in {"P0", "P1", "P2", "P3"}:
                registry = get_companies_by_tier(conn, tier, shard, total_shards)
            else:
                registry = get_companies_for_scrape(conn, shard=shard, total_shards=total_shards, platforms=platforms)
        finally:
            conn.close()

    if not registry:
        _log("No due canonical companies available for ATS ingestion.", "WARN")
        return

    # Filter out broken/rate-limited platforms
    before_count = len(registry)
    registry = [c for c in registry if c.get("ats", "").lower() not in skip_platforms]
    skipped = before_count - len(registry)
    if skipped:
        _log(f"Skipping {skipped} companies on platforms: {', '.join(sorted(skip_platforms))}")

    # ── Platform whitelist filter ───────────────────────────────────────
    # Allows tiers to target specific ATS types (e.g. fast tier = greenhouse/lever/ashby only)
    if platforms and tier:
        before_platform_filter = len(registry)
        registry = [c for c in registry if c.get("ats", "").lower() in platforms]
        _log(f"Platform filter {sorted(platforms)}: {len(registry)} of {before_platform_filter} companies selected.")

    # ── Registry Sharding ──────────────────────────────────────────────
    # Split 10k+ companies into N rotating shards for shorter runs.
    # Auto-shard selects based on the current 15-min time slot.
    if shard is not None and tier:
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
    set_response_cache(cache)
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

    if queue_mode in QUEUE_MODES:
        before_budget = len(registry)
        registry, budget_dropped, budget_metrics = apply_platform_budgets(registry)
        selected_keys = [_target_key(c) for c in registry]
        deferred_keys = [_target_key(c) for c in budget_dropped]
        queue_metrics["budget_dropped"] += len(budget_dropped)
        queue_metrics["budgets"] = budget_metrics
        queue_metrics["selected_keys"] = selected_keys
        queue_metrics["selected_sample"] = selected_keys[:25]
        queue_metrics["deferred_sample"] = deferred_keys[:25]
        conn = get_connection()
        try:
            previous_selected = _load_previous_selected_keys(conn)
        finally:
            conn.close()
        overlap = sorted(previous_selected & set(selected_keys))
        queue_metrics["previous_overlap"] = len(overlap)
        queue_metrics["previous_overlap_sample"] = overlap[:25]
        _log(
            "Queue selection: "
            f"selected={len(selected_keys)}, deferred={len(deferred_keys)}, "
            f"previous_overlap={len(overlap)}. "
            f"selected_sample={queue_metrics['selected_sample'][:10]}, "
            f"deferred_sample={queue_metrics['deferred_sample'][:10]}"
        )
        if budget_dropped and queue_mode == "active":
            conn = get_connection()
            try:
                queue_metrics["released_skipped"] += release_company_leases(conn, budget_dropped, lease_owner)
            finally:
                conn.close()
        if budget_dropped:
            _log(
                f"Final adaptive platform budgets selected {len(registry)}/{before_budget} targets "
                f"and deferred {len(budget_dropped)}."
            )

    # ── Skip Unchanged Companies ──────────────────────────────────────
    # Filter out companies that were recently scraped and haven't changed.
    # This is the biggest optimization: 12k → ~2-3k companies per cycle.
    companies_to_scrape = []
    for c in registry:
        should_scrape, reason = company_metadata.should_scrape(c["ats"], c["slug"])
        if should_scrape:
            companies_to_scrape.append(c)
    scrape_keys = {f"{x.get('ats')}:{x.get('slug')}" for x in companies_to_scrape}
    metadata_skipped = [c for c in registry if f"{c.get('ats')}:{c.get('slug')}" not in scrape_keys]
    if metadata_skipped and queue_mode == "active":
        conn = get_connection()
        try:
            queue_metrics["released_skipped"] += release_company_leases(conn, metadata_skipped, lease_owner)
        finally:
            conn.close()

    skip_stats = company_metadata.get_stats()
    _log(
        f"Skip-unchanged filter: {skip_stats['skipped']}/{skip_stats['checked']} skipped "
        f"({skip_stats['skip_rate']}), {len(companies_to_scrape)} to scrape"
    )

    # Group companies by ATS platform (including Workday → WorkdayAdapter)
    by_platform = defaultdict(list)
    for c in companies_to_scrape:
        by_platform[c["ats"]].append(c)

    platform_summary = ", ".join(f"{k}={len(v)}" for k, v in sorted(by_platform.items()))
    _log(f"Platform breakdown: {platform_summary}")

    all_results = []
    errors = []
    failure_counts = Counter()
    failure_by_ats = defaultdict(Counter)
    failing_targets = Counter()

    # Proxy support: set PROXY_URL in env for rotating proxies
    proxy = os.environ.get("PROXY_URL")
    if proxy:
        _log(f"Using proxy: {proxy[:30]}...")

    try:
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
                            q,
                            session,
                            rate_limiter,
                            cache,
                            all_results,
                            errors,
                            circuit_breaker=breaker,
                            company_metadata=company_metadata,
                            retry_queue=retry_queue,
                        )
                    )
                    worker_tasks.append(task)

            # Wait for all workers to drain their queues
            await asyncio.gather(*worker_tasks, return_exceptions=True)
    finally:
        set_response_cache(None)

    # Save company metadata after scraping
    company_metadata.save()
    final_stats = company_metadata.get_stats()
    _log(f"Company metadata: {final_stats['scraped']} companies scraped, metadata saved")

    # Save retry queue and log stats
    retry_queue.save()
    retry_stats = retry_queue.get_stats()
    _log(
        f"Retry queue: added={retry_stats['added']}, retried={retry_stats['retried']}, "
        f"success={retry_stats['success']}, dropped={retry_stats['dropped']}, "
        f"queue_size={retry_stats['queue_size']}"
    )

    # Flatten jobs + collect lifecycle data
    all_jobs = []
    all_job_targets = []
    company_job_ids = defaultdict(set)  # (ats, company) → {job_id, ...}
    raw_counts_by_target = defaultdict(int)  # (ats, slug) -> raw jobs fetched

    success_by_ats = defaultdict(int)
    jobs_by_ats = defaultdict(int)
    for name, ats, slug, jobs, err, failure, _target_metadata in all_results:
        target_key = (ats, slug)
        if err:
            errors.append(f"{name}: {err}")
        elif failure:
            errors.append(
                f"{name}: {failure.get('category')}:{failure.get('status_code') or 'n/a'}:{failure.get('error') or ''}"
            )
        if failure:
            category = str(failure.get("category", "unknown"))
            failure_counts[category] += 1
            failure_by_ats[ats][category] += 1
            failing_targets[f"{ats}/{slug}"] += 1
        elif not err:
            success_by_ats[ats] += 1
        jobs_by_ats[ats] += len(jobs)
        for job in jobs:
            all_jobs.append(job)
            all_job_targets.append((job, target_key))
            raw_counts_by_target[target_key] += 1
            company_job_ids[(ats, name)].add(job.job_id)

    # Log circuit breaker health and persist open platforms for the next run.
    _log(f"Circuit breaker: {breaker.summary()}")
    breaker.save()

    cache.log_stats()
    _log(f"Fetched {len(all_jobs)} total raw jobs from ATS APIs.")

    # ── Filtering Pipeline ────────────────────────────────────────────
    role_filtered_pairs = [(j, target) for j, target in all_job_targets if matches_target_role(j.title)]
    role_filtered = [j for j, _target in role_filtered_pairs]
    _log(f"Role filter: {len(role_filtered)}/{len(all_jobs)} matched target tech roles.")

    us_filtered_pairs = [(j, target) for j, target in role_filtered_pairs if is_us_location(j.location)]
    us_filtered = [j for j, _target in us_filtered_pairs]
    _log(f"US filter: {len(us_filtered)}/{len(role_filtered)} in United States.")

    # Always apply time filter — on GitHub Actions the DB is ephemeral,
    # so "first run" detection doesn't make sense for CI.
    time_filtered_pairs = [
        (j, target) for j, target in us_filtered_pairs if is_within_window(j.date_posted, window_hours)
    ]
    time_filtered = [j for j, _target in time_filtered_pairs]
    _log(f"{window_hours}hr filter: {len(time_filtered)}/{len(us_filtered)} within window.")

    relevant_counts_by_target = defaultdict(int)
    for _job, target_key in time_filtered_pairs:
        relevant_counts_by_target[target_key] += 1

    # ── Database Insertion ────────────────────────────────────────────
    conn = get_connection()
    new_jobs_inserted = 0
    try:
        # Feed scheduler metrics back into the canonical companies table.
        for _name, ats, slug, _jobs, err, failure, target_metadata in all_results:
            target_key = (ats, slug)
            raw_count = raw_counts_by_target[target_key]
            relevant_count = relevant_counts_by_target[target_key]
            failure_category = str(failure.get("category", "")) if failure else None
            used_cached_metadata = False
            if target_metadata:
                target_metadata = dict(target_metadata)
                used_cached_metadata = bool(target_metadata.pop("_used_cached_metadata", False))
            update_company_last_scraped(
                conn,
                slug,
                job_found=raw_count > 0,
                ats=ats,
                job_count=raw_count,
                relevant_count=relevant_count,
                failed=bool(err or failure) and raw_count == 0,
                failure_category=failure_category,
            )
            if used_cached_metadata and failure_category in {"bad_target", "parse", "empty_board"} and raw_count == 0:
                clear_company_validated_metadata_key(conn, ats, slug, "workday_site")
                continue
            if target_metadata:
                update_company_validated_metadata(conn, ats, slug, target_metadata)

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
    attempted_by_ats = {ats: len(companies) for ats, companies in sorted(by_platform.items())}
    failure_breakdown = {ats: dict(sorted(counts.items())) for ats, counts in sorted(failure_by_ats.items())}
    platform_metrics = {
        ats: {
            "attempted": attempted_by_ats.get(ats, 0),
            "succeeded": success_by_ats.get(ats, 0),
            "failed": sum(failure_by_ats.get(ats, {}).values()),
            "jobs_fetched": jobs_by_ats.get(ats, 0),
            "timeouts": failure_by_ats.get(ats, {}).get("timeout", 0),
        }
        for ats in sorted(set(attempted_by_ats) | set(success_by_ats) | set(failure_by_ats) | set(jobs_by_ats))
    }
    bad_target_failures = failure_counts.get("bad_target", 0)
    timeout_failures = failure_counts.get("timeout", 0)
    critical_failures = timeout_failures + failure_counts.get("anti_bot", 0) + failure_counts.get("rate_limited", 0)
    run_status = "degraded" if critical_failures or len(errors) >= 25 else "success"
    summary = {
        "status": run_status,
        "platforms": platform_metrics,
        "failures": dict(sorted(failure_counts.items())),
        "bad_targets": bad_target_failures,
        "targets_loaded": len(registry),
        "targets_attempted": len(companies_to_scrape),
        "jobs_fetched": len(all_jobs),
        "candidates": len(time_filtered),
        "queue": queue_metrics,
    }
    _log(f"ATS platform summary: {json.dumps(platform_metrics, sort_keys=True)}")
    if run_status == "degraded":
        _log(f"ATS run marked degraded: {json.dumps(summary, sort_keys=True)}", "WARN")

    err_str = "; ".join(errors[:20]) if errors else ""  # Cap error string length
    try:
        log_scraper_run(
            conn,
            "scrape_ats",
            len(registry),
            new_jobs_inserted,
            duration,
            err_str,
            shard_index=(shard if shard is not None else 0),
            status=run_status,
            summary_json=summary,
        )
    finally:
        conn.close()

    # ── Health Tracking ───────────────────────────────────────────────
    # Record run metrics for monitoring and alerts
    error_counts = dict(sorted(failure_counts.items()))
    if failure_by_ats:
        _log(f"ATS failure breakdown: {failure_breakdown}")
    if failing_targets:
        top_failing = failing_targets.most_common(10)
        _log(f"Top failing targets: {top_failing}")

    health_tracker.end_run(
        companies_scraped=final_stats["scraped"],
        companies_skipped=skip_stats["skipped"],
        jobs_found=len(all_jobs),
        new_jobs=new_jobs_inserted,
        errors=error_counts,
        retry_queue_size=retry_stats["queue_size"],
        failure_breakdown=failure_breakdown,
        top_failures=[{"target": target, "count": count} for target, count in failing_targets.most_common(10)],
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

    return summary


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_ats_scraper(24))
