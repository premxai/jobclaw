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

import asyncio
import os
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.logger import _log

# ── Shard Rotation Counter ───────────────────────────────────────────
SHARD_COUNTER_FILE = PROJECT_ROOT / "data" / ".shard_counter"


def get_next_shard(total_shards: int = 4) -> int:
    """Deterministic shard rotation: 0 → 1 → 2 → 3 → 0 → ...
    
    Uses a file-based counter so it persists across runs.
    Guarantees full registry coverage every `total_shards` runs.
    """
    current = 0
    if SHARD_COUNTER_FILE.exists():
        try:
            current = int(SHARD_COUNTER_FILE.read_text().strip())
        except (ValueError, OSError):
            current = 0
    
    shard = current % total_shards
    
    # Increment for next run
    SHARD_COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    SHARD_COUNTER_FILE.write_text(str(current + 1))
    
    _log(f"[shard-rotation] Shard {shard}/{total_shards} (run #{current + 1})")
    return shard


async def _run_with_timing(name: str, coro):
    """Run a scraper coroutine and return (name, duration, error_or_None)."""
    start = time.time()
    try:
        await coro
        dur = round(time.time() - start, 1)
        _log(f"[orchestrator] OK {name} finished in {dur}s")
        return (name, dur, None)
    except Exception as e:
        dur = round(time.time() - start, 1)
        _log(f"[orchestrator] FAIL {name} after {dur}s: {e}", "ERROR")
        return (name, dur, str(e))


async def run_all(
    skip_ats: bool = False,
    skip_github: bool = False,
    run_brave: bool = False,
    window_hours: int = 24,
    skip_platforms: set = None,
    shard: int = None,
    total_shards: int = 4,
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

    # ── Always run: RSS (fastest) ───────────────────────────────────
    from scripts.ingestion.scrape_rss import run_rss_scraper
    tasks.append(_run_with_timing("RSS/Aggregators", run_rss_scraper(window_hours)))

    # ── Always run: Enterprise (8 big companies) ────────────────────
    from scripts.ingestion.scrape_enterprise import run_enterprise_scraper
    tasks.append(_run_with_timing("Enterprise (Apple/Amazon/Google...)", run_enterprise_scraper()))

    # ── GitHub repos ────────────────────────────────────────────────
    if not skip_github:
        from scripts.ingestion.scrape_github import run_github_scraper
        tasks.append(_run_with_timing("GitHub Repos", run_github_scraper(window_hours)))

    # ── ATS boards (~10,500 companies with curl_cffi TLS impersonation) ──
    # All ATS platforms handled by direct API scraper with TLS impersonation
    if not skip_ats:
        from scripts.ingestion.scrape_ats import run_ats_scraper
        ats_skip = skip_platforms if skip_platforms is not None else set()
        
        shard_label = f", shard={shard}/{total_shards}" if shard is not None else ""
        label = f"ATS Boards ({'filtered' if ats_skip else 'all'}{shard_label})"
        tasks.append(_run_with_timing(
            label,
            run_ats_scraper(
                window_hours,
                skip_platforms=ats_skip,
                shard=shard,
                total_shards=total_shards,
            )
        ))

    # ── Brave Search (LinkedIn/Indeed/Glassdoor) — deep tier only ──────
    # Searches job boards that can't be scraped directly.
    # Budget: 30 queries/day = 900/month (free tier: 2,000/month).
    if run_brave:
        brave_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
        if brave_key:
            from scripts.ingestion.scrape_brave import run_brave_scraper
            tasks.append(_run_with_timing("Brave Search (LinkedIn/Indeed/Glassdoor)", run_brave_scraper()))
        else:
            _log("[orchestrator] BRAVE_SEARCH_API_KEY not set — skipping Brave Search")

    # NOTE: StreamingJobPusher disabled — no scraper currently calls pusher.push().
    # The batch push_new_jobs_to_discord() at the end handles all Discord notifications.
    # StreamingJobPusher can be re-enabled when scrapers are wired to call push() per job.

    # Fire all scrapers at once — each has its own session + rate limiter
    # Global 20-minute timeout so nothing can hang forever
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=20 * 60,  # 20 minutes max
        )
    except asyncio.TimeoutError:
        _log("[orchestrator] GLOBAL TIMEOUT after 20 minutes -- aborting remaining scrapers", "ERROR")
        results = []

    # ── Summary ─────────────────────────────────────────────────────
    total_dur = round(time.time() - start_time, 1)
    _log(f"[orchestrator] === ALL SCRAPERS COMPLETE in {total_dur}s ===")

    successes = 0
    failures = 0
    for r in results:
        if isinstance(r, Exception):
            _log(f"[orchestrator] Unhandled exception: {r}", "ERROR")
            failures += 1
        else:
            name, dur, err = r
            if err:
                failures += 1
            else:
                successes += 1

    _log(f"[orchestrator] Results: {successes} succeeded, {failures} failed, total {total_dur}s")

    # ── INSTANT Discord Push — post the moment scraping finishes ────
    jobs_pushed = 0
    try:
        from scripts.discord_push import push_new_jobs_to_discord
        jobs_pushed = await push_new_jobs_to_discord()
        if jobs_pushed:
            _log(f"[orchestrator] >> Pushed {jobs_pushed} new jobs to Discord INSTANTLY.")
        else:
            _log(f"[orchestrator] No new unposted jobs to push.")
    except Exception as e:
        _log(f"[orchestrator] Discord push failed (non-fatal): {e}", "WARN")

    return {
        "duration_s": total_dur,
        "successes": successes,
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
    parser.add_argument("--tier", type=str, default=None,
                        choices=["fast", "medium", "heavy", "deep"],
                        help="Scheduling tier preset (fast/medium/heavy/deep)")
    parser.add_argument("--fast", action="store_true",
                        help="Legacy: same as --tier fast")
    parser.add_argument("--hourly", action="store_true",
                        help="Legacy: 1hr window, skip slow platforms")
    parser.add_argument("--daily", action="store_true",
                        help="Legacy: 24hr window, all platforms")
    parser.add_argument("--no-github", action="store_true",
                        help="Skip GitHub repo parsing")
    parser.add_argument("--skip-ats", dest="skip_ats", action="store_true",
                        help="Skip all ATS board scrapers (Greenhouse, Lever, etc.)")
    parser.add_argument("--window", type=int, default=None,
                        help="Time window in hours (overrides tier default)")
    parser.add_argument("--shard", type=str, default=None,
                        help="ATS shard: 0-3 or 'auto' for time-based rotation")
    parser.add_argument("--total-shards", type=int, default=4,
                        help="Number of registry shards (default: 4)")
    args = parser.parse_args()

    # ── Tier-based presets (ZERO-MISS: every tier includes ATS) ────────
    tier = args.tier
    total_shards = args.total_shards

    # Legacy flag mapping
    if not tier:
        if args.fast:
            tier = "fast"
        elif args.hourly:
            tier = "medium"
        elif args.daily:
            tier = "deep"

    if tier == "fast":
        # RSS + GitHub + ATS (1 rotating shard) — ~2 min
        skip_ats = False
        run_brave = False
        skip_github = False
        window = args.window or 4
        skip_platforms = set()
        shard_val = get_next_shard(total_shards)  # Deterministic rotation
    elif tier == "medium":
        # RSS + GitHub + Enterprise + ATS (1 rotating shard) — ~4 min
        skip_ats = False
        run_brave = False
        skip_github = False
        window = args.window or 8
        skip_platforms = set()
        shard_val = get_next_shard(total_shards)
    elif tier == "deep":
        # Everything: ALL shards + Brave Search — ~15 min
        skip_ats = False
        run_brave = True
        skip_github = False
        window = args.window or 24
        skip_platforms = set()
        shard_val = None  # No sharding — full sweep of all companies
    else:
        # No tier specified — default to medium behavior
        skip_ats = False
        run_brave = False
        skip_github = args.no_github
        window = args.window or 24
        skip_platforms = None
        shard_val = get_next_shard(total_shards)

    # Override shard from CLI if explicitly set
    if args.shard is not None:
        if args.shard.lower() == 'auto':
            shard_val = get_next_shard(total_shards)
        else:
            shard_val = int(args.shard)

    # CLI flags can override tier defaults
    if args.skip_ats:
        skip_ats = True
    if args.no_github:
        skip_github = True

    _log(f"[orchestrator] Tier={tier or 'default'}, Window={window}hr, "
         f"Shard={shard_val if shard_val is not None else 'ALL'}/{total_shards}, "
         f"ATS={'OFF' if skip_ats else 'ON'}, "
         f"Brave={'ON' if run_brave else 'OFF'}")

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(run_all(
        skip_ats=skip_ats,
        skip_github=skip_github,
        run_brave=run_brave,
        window_hours=window,
        skip_platforms=skip_platforms,
        shard=shard_val,
        total_shards=args.total_shards,
    ))


if __name__ == "__main__":
    main()
