"""
ZERO-MISS Scraper Orchestrator — guaranteed full coverage.

Strategy: EVERY tier scrapes ATS companies. Shard rotation guarantees
all companies are covered within 4 consecutive runs.

Tiers:
  fast:   RSS + GitHub + ATS (1 rotating shard)                ~2 min
  medium: RSS + GitHub + Enterprise + ATS (1 shard)            ~4 min
  deep:   Everything + Brave Search (ALL shards, no rotation)  ~15 min

Usage:
    python scripts/ingestion/run_all_scrapers.py --tier fast
    python scripts/ingestion/run_all_scrapers.py --tier deep
"""

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.logger import _log
from scripts.database.db_utils import get_connection, get_next_shard_from_db


def get_next_shard(scraper_name: str, total_shards: int = 4) -> int:
    """Read shard from DB to ensure rotation persists even in ephemeral runners."""
    conn = get_connection()
    try:
        shard = get_next_shard_from_db(conn, scraper_name, total_shards)
        _log(f"[shard-rotation] {scraper_name} -> Shard {shard}/{total_shards}")
        return shard
    finally:
        conn.close()


async def _run_with_timing(name: str, coro):
    """Run a scraper coroutine and return (name, duration, error_or_None, status)."""
    start = time.time()
    try:
        result = await coro
        dur = round(time.time() - start, 1)
        status = result.get("status", "success") if isinstance(result, dict) else "success"
        if status == "degraded":
            reason = result.get("failures", {}) if isinstance(result, dict) else {}
            _log(f"[orchestrator] DEGRADED {name} finished in {dur}s: {reason}", "WARN")
            return (name, dur, "degraded", status)
        _log(f"[orchestrator] OK {name} finished in {dur}s")
        return (name, dur, None, status)
    except Exception as e:
        dur = round(time.time() - start, 1)
        _log(f"[orchestrator] FAIL {name} after {dur}s: {e}", "ERROR")
        return (name, dur, str(e), "failed")


async def _with_timeout(coro, name: str, timeout_sec: int):
    """Wrap a scraper coroutine with a per-scraper timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_sec)
    except asyncio.TimeoutError:
        _log(
            f"SCRAPER_TIMEOUT: {name} exceeded {timeout_sec}s — partial results may be missing",
            "ERROR",
        )
        return (name, timeout_sec, f"timeout after {timeout_sec}s", "degraded")


async def run_all(
    skip_ats: bool = False,
    skip_github: bool = False,
    run_brave: bool = False,
    window_hours: int = 24,
    skip_platforms: set = None,
    shard: int = None,
    total_shards: int = 4,
    tier: str = None,
    platforms: set = None,
    target_limit: int = None,
):
    """
    Launch all scrapers in parallel — ZERO-MISS coverage.

    Every tier includes ATS. Shard rotation guarantees full
    company coverage every 4 runs.

    Priority order (by speed):
      1. RSS/Aggregators  (~30s)   -- cheapest, fastest signal
      2. GitHub repos     (~1-2m)  -- static markdown parsing
      3. Enterprise APIs  (~2-5m)  -- 8 companies, REST APIs
      4. ATS boards       (~2-8m)  -- companies per shard
      5. Brave Search     (~1m)    -- LinkedIn/Indeed/Glassdoor (deep tier only)

    All run concurrently — no scraper blocks another.
    """
    start_time = time.time()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _log(f"[orchestrator] === SPEED SCRAPE STARTED at {ts} (window={window_hours}hr) ===")

    tasks = []
    if target_limit is None:
        if tier == "medium":
            target_limit = int(os.getenv("JOBCLAW_MEDIUM_TARGET_LIMIT", "800"))
        elif tier == "fast":
            target_limit = int(os.getenv("JOBCLAW_FAST_TARGET_LIMIT", "3000"))
        elif tier == "deep":
            target_limit = int(os.getenv("JOBCLAW_DEEP_TARGET_LIMIT", "3000"))
        else:
            target_limit = int(os.getenv("JOBCLAW_ATS_TARGET_LIMIT", "3000"))

    # ── Always run: RSS (fastest) ───────────────────────────────────
    from scripts.ingestion.scrape_rss import run_rss_scraper

    tasks.append(
        _with_timeout(
            _run_with_timing("RSS/Aggregators", run_rss_scraper(window_hours)),
            "RSS/Aggregators",
            120,
        )
    )

    # ── Always run: Enterprise (8 big companies) ────────────────────
    from scripts.ingestion.scrape_enterprise import run_enterprise_scraper

    tasks.append(
        _with_timeout(
            _run_with_timing("Enterprise (Apple/Amazon/Google...)", run_enterprise_scraper()),
            "Enterprise (Apple/Amazon/Google...)",
            300,
        )
    )

    # ── GitHub repos ────────────────────────────────────────────────
    if not skip_github:
        from scripts.ingestion.scrape_github import run_github_scraper

        tasks.append(
            _with_timeout(
                _run_with_timing("GitHub Repos", run_github_scraper(window_hours)),
                "GitHub Repos",
                180,
            )
        )

    # ── ATS boards (~10,500 companies with curl_cffi TLS impersonation) ──
    # All ATS platforms handled by direct API scraper with TLS impersonation
    if not skip_ats:
        from scripts.ingestion.scrape_ats import run_ats_scraper

        ats_skip = skip_platforms if skip_platforms is not None else set()

        shard_label = f", shard={shard}/{total_shards}" if shard is not None else ""
        label = f"ATS Boards ({'filtered' if ats_skip else 'all'}{shard_label})"
        company_tier = tier if tier in {"P0", "P1", "P2", "P3"} else None
        tasks.append(
            _with_timeout(
                _run_with_timing(
                    label,
                    run_ats_scraper(
                        window_hours,
                        skip_platforms=ats_skip,
                        shard=shard,
                        total_shards=total_shards,
                        tier=company_tier,
                        platforms=platforms,
                        target_limit=target_limit,
                    ),
                ),
                label,
                900,  # Reduced from 1200s (20min) to 900s (15min) for faster failure detection
            )
        )

    # ── Brave Search (LinkedIn/Indeed/Glassdoor) — deep tier only ──────
    # Searches job boards that can't be scraped directly.
    # Budget: 30 queries/day = 900/month (free tier: 2,000/month).
    if run_brave:
        brave_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
        if brave_key:
            from scripts.ingestion.scrape_brave import run_brave_scraper

            tasks.append(
                _with_timeout(
                    _run_with_timing("Brave Search (LinkedIn/Indeed/Glassdoor)", run_brave_scraper()),
                    "Brave Search (LinkedIn/Indeed/Glassdoor)",
                    int(os.getenv("JOBCLAW_BRAVE_TIMEOUT_SECONDS", "240")),
                )
            )
        else:
            _log("[orchestrator] BRAVE_SEARCH_API_KEY not set — skipping Brave Search")

        # ── YC Startups (workatastartup.com) — deep tier only ───────────
        from scripts.ingestion.scrape_yc import fetch_yc_jobs

        tasks.append(
            _with_timeout(
                _run_with_timing("YC Startups (workatastartup.com)", fetch_yc_jobs()),
                "YC Startups (workatastartup.com)",
                120,
            )
        )

        # ── HN Who's Hiring — deep tier only ────────────────────────────
        from scripts.ingestion.scrape_hn_hiring import fetch_hn_hiring_jobs

        tasks.append(
            _with_timeout(
                _run_with_timing("HN Who's Hiring (Algolia API)", fetch_hn_hiring_jobs()),
                "HN Who's Hiring (Algolia API)",
                120,
            )
        )

        # ── Indeed Public Search — deep tier only ───────────────────────
        from scripts.ingestion.scrape_indeed import fetch_indeed_jobs

        tasks.append(
            _with_timeout(
                _run_with_timing("Indeed Public Search", fetch_indeed_jobs()),
                "Indeed Public Search",
                300,
            )
        )

    # NOTE: StreamingJobPusher disabled — no scraper currently calls pusher.push().
    # The batch push_new_jobs_to_discord() at the end handles all Discord notifications.
    # StreamingJobPusher can be re-enabled when scrapers are wired to call push() per job.

    # Fire all scrapers at once — each has its own session + rate limiter
    # Global 25-minute timeout so nothing can hang forever
    global_timed_out = False
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=25 * 60,  # Increased from 20min to 25min to accommodate reduced ATS timeout
        )
    except TimeoutError:
        _log("[orchestrator] GLOBAL TIMEOUT after 25 minutes -- aborting remaining scrapers", "ERROR")
        global_timed_out = True
        results = []

    # ── Summary ─────────────────────────────────────────────────────
    total_dur = round(time.time() - start_time, 1)
    _log(f"[orchestrator] === ALL SCRAPERS COMPLETE in {total_dur}s ===")

    successes = 0
    failures = 0
    degraded = 0
    for r in results:
        if isinstance(r, Exception):
            _log(f"[orchestrator] Unhandled exception: {r}", "ERROR")
            failures += 1
        else:
            name, dur, err, status = r
            if status == "degraded":
                degraded += 1
            elif err:
                failures += 1
            else:
                successes += 1
    if global_timed_out:
        degraded += 1

    run_status = "failed" if failures else "degraded" if degraded else "success"
    _log(
        f"[orchestrator] Results: {successes} succeeded, {degraded} degraded, {failures} failed, "
        f"status={run_status}, total {total_dur}s"
    )

    # ── AI Pipeline — dedup + salary backfill (deep tier only) ─────
    if run_brave:  # run_brave=True is the deep-tier flag
        try:
            from scripts.ai.run_ai_pipeline import run_ai_pipeline

            await run_ai_pipeline()
        except Exception as e:
            _log(f"[orchestrator] AI pipeline failed (non-fatal): {e}", "WARN")

    # ── INSTANT Discord Push — post the moment scraping finishes ────
    jobs_pushed = 0
    try:
        from scripts.discord_push import push_new_jobs_to_discord

        jobs_pushed = await push_new_jobs_to_discord()
        if jobs_pushed:
            _log(f"[orchestrator] >> Pushed {jobs_pushed} new jobs to Discord INSTANTLY.")
        else:
            _log("[orchestrator] No new unposted jobs to push.")
    except Exception as e:
        _log(f"[orchestrator] Discord push failed (non-fatal): {e}", "WARN")

    return {
        "duration_s": total_dur,
        "status": run_status,
        "successes": successes,
        "degraded": degraded,
        "failures": failures,
        "jobs_pushed": jobs_pushed,
    }


def main():
    parser = argparse.ArgumentParser(
        description="JobClaw v4 Speed Scraper — find jobs FAST with tiered scheduling",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Tier presets (recommended):
  --tier fast     RSS + GitHub + ATS (1 shard)       (~2 min,  every hour)
  --tier medium   + Enterprise APIs + ATS (1 shard)  (~4 min,  every hour)
  --tier deep     Everything + Brave Search           (~15 min, daily)

Legacy flags still work:
  --fast          Same as --tier fast
  --hourly        1hr window for ATS
  --daily         24hr window for everything
        """,
    )
    parser.add_argument(
        "--tier",
        type=str,
        default=None,
        choices=["fast", "medium", "heavy", "deep"],
        help="Scheduling tier preset (fast/medium/heavy/deep)",
    )
    parser.add_argument("--fast", action="store_true", help="Legacy: same as --tier fast")
    parser.add_argument("--hourly", action="store_true", help="Legacy: 1hr window, skip slow platforms")
    parser.add_argument("--daily", action="store_true", help="Legacy: 24hr window, all platforms")
    parser.add_argument("--no-github", action="store_true", help="Skip GitHub repo parsing")
    parser.add_argument(
        "--skip-ats", dest="skip_ats", action="store_true", help="Skip all ATS board scrapers (Greenhouse, Lever, etc.)"
    )
    parser.add_argument("--window", type=int, default=None, help="Time window in hours (overrides tier default)")
    parser.add_argument("--shard", type=str, default=None, help="ATS shard: 0-3 or 'auto' for time-based rotation")
    parser.add_argument("--total-shards", type=int, default=4, help="Number of registry shards (default: 4)")
    args = parser.parse_args()

    # ── Tier-based presets (ZERO-MISS: every tier includes ATS) ────────
    tier = args.tier
    total_shards = args.total_shards  # may be overridden per-tier below

    # Legacy flag mapping
    if not tier:
        if args.fast:
            tier = "fast"
        elif args.hourly:
            tier = "medium"
        elif args.daily:
            tier = "deep"

    # Gem DNS is permanently dead — skip on every tier
    _GEM_SKIP = {"gem"}

    if tier == "fast":
        # Group A: Fast REST APIs only (Greenhouse, Lever, Ashby)
        # 10,801 companies / 4 shards = ~2,700/run → finishes in ~8 min
        # DB-persisted rotation guarantees full coverage every 4 hourly runs
        _FAST_SHARDS = 4
        skip_ats = False
        run_brave = False
        skip_github = False
        window = args.window or 24
        skip_platforms = _GEM_SKIP
        platforms = {"greenhouse", "lever", "ashby"}
        shard_val = get_next_shard("fast_ats_ghla", _FAST_SHARDS)
        total_shards = _FAST_SHARDS
        db_tier = None
        target_limit = int(os.getenv("JOBCLAW_FAST_TARGET_LIMIT", "3000"))
    elif tier == "medium":
        # Group B: Workday-heavy platforms across a 16-shard rotation by default.
        # Workday-heavy platforms are slow; keep each run small and reliable.
        _MEDIUM_SHARDS = int(os.getenv("JOBCLAW_WORKDAY_SHARDS", "16"))
        skip_ats = False
        run_brave = False
        skip_github = False
        window = args.window or 8
        skip_platforms = _GEM_SKIP
        platforms = {"workday", "rippling", "smartrecruiters", "bamboohr"}
        shard_val = get_next_shard("medium_ats_workday", _MEDIUM_SHARDS)
        total_shards = _MEDIUM_SHARDS  # must match shard key — do not use args.total_shards here
        db_tier = None
        target_limit = int(os.getenv("JOBCLAW_MEDIUM_TARGET_LIMIT", "800"))
    elif tier == "deep":
        # Everything: ALL platforms + Workable + Brave Search — daily full sweep
        skip_ats = False
        run_brave = True
        skip_github = False
        window = args.window or 24
        skip_platforms = _GEM_SKIP  # Gem still dead in deep
        platforms = None  # All platforms including workable
        shard_val = None  # No sharding — full sweep of all companies
        db_tier = None
        target_limit = int(os.getenv("JOBCLAW_DEEP_TARGET_LIMIT", "3000"))
    else:
        # No tier specified — default to medium behavior
        skip_ats = False
        run_brave = False
        skip_github = args.no_github
        window = args.window or 24
        skip_platforms = _GEM_SKIP
        platforms = None
        shard_val = get_next_shard("custom_ats", total_shards)
        db_tier = "P2"
        target_limit = int(os.getenv("JOBCLAW_ATS_TARGET_LIMIT", "3000"))

    # Override shard from CLI if explicitly set
    if args.shard is not None:
        if args.shard.lower() == "auto":
            shard_val = get_next_shard("cli_auto_ats", total_shards)
        else:
            shard_val = int(args.shard)

    # CLI flags can override tier defaults
    if args.skip_ats:
        skip_ats = True
    if args.no_github:
        skip_github = True

    _log(
        f"[orchestrator] Tier={tier or 'default'}, Window={window}hr, "
        f"Shard={shard_val if shard_val is not None else 'ALL'}/{total_shards if shard_val is not None else 'N/A'}, "
        f"ATS={'OFF' if skip_ats else 'ON'}, "
        f"Platforms={sorted(platforms) if platforms else 'ALL'}, "
        f"TargetLimit={target_limit}, "
        f"Brave={'ON' if run_brave else 'OFF'}"
    )

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    result = asyncio.run(
        run_all(
            skip_ats=skip_ats,
            skip_github=skip_github,
            run_brave=run_brave,
            window_hours=window,
            skip_platforms=skip_platforms,
            shard=shard_val,
            total_shards=total_shards,
            tier=db_tier,
            platforms=platforms,
            target_limit=target_limit,
        )
    )
    if result.get("status") == "degraded" and os.getenv("JOBCLAW_DEGRADED_FAILS_WORKFLOW", "0").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        sys.exit(2)


if __name__ == "__main__":
    main()
