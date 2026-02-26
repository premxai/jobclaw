"""
SPEED-OPTIMIZED Scraper Orchestrator — runs all scrapers in parallel.

Strategy: maximum job discovery speed.
  - RSS + GitHub + Enterprise + ATS all run concurrently
  - Each scraper has its own session / rate limiter (no resource contention)
  - Enterprise (8 companies) and RSS finish in <2 min → you get quick wins
    while ATS grinds through 11,800 companies in the background
  - Discord notification fires the moment ANY scraper finds new jobs

Usage:
    python scripts/ingestion/run_all_scrapers.py              # full blast
    python scripts/ingestion/run_all_scrapers.py --fast        # skip ATS (quick scan only)
    python scripts/ingestion/run_all_scrapers.py --no-openclaw # skip expensive browser automation
"""

import asyncio
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.logger import _log


async def _run_with_timing(name: str, coro):
    """Run a scraper coroutine and return (name, duration, error_or_None)."""
    start = time.time()
    try:
        await coro
        dur = round(time.time() - start, 1)
        _log(f"[orchestrator] ✓ {name} finished in {dur}s")
        return (name, dur, None)
    except Exception as e:
        dur = round(time.time() - start, 1)
        _log(f"[orchestrator] ✗ {name} FAILED after {dur}s: {e}", "ERROR")
        return (name, dur, str(e))


async def run_all(
    skip_ats: bool = False,
    skip_openclaw: bool = False,
    skip_github: bool = False,
    window_hours: int = 24,
):
    """
    Launch all scrapers in parallel for maximum speed.

    Priority order (by speed):
      1. RSS/Aggregators  (~30s)   — cheapest, fastest signal
      2. Enterprise APIs  (~2-5m)  — 8 companies, REST APIs
      3. GitHub repos     (~1-2m)  — static markdown parsing
      4. ATS boards       (~10-30m) — 11,800 companies, the big sweep
      5. OpenClaw browser (~3-5m)  — expensive, uses Minimax API credits

    All run concurrently — the fast ones report results immediately while
    ATS keeps grinding. No scraper blocks another.
    """
    start_time = time.time()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _log(f"[orchestrator] ═══ SPEED SCRAPE STARTED at {ts} ═══")

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

    # ── ATS boards (the big one: 11,800 companies) ──────────────────
    if not skip_ats:
        from scripts.ingestion.scrape_ats import run_ats_scraper
        tasks.append(_run_with_timing("ATS Boards (11,800 cos)", run_ats_scraper(window_hours)))

    # ── OpenClaw browser automation (LinkedIn/Indeed/Glassdoor) ──────
    if not skip_openclaw:
        from scripts.ingestion.scrape_openclaw import run_openclaw_scraper
        tasks.append(_run_with_timing("OpenClaw (LinkedIn/Indeed/Glassdoor)", run_openclaw_scraper()))

    # Fire all at once — each has its own session + rate limiter
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # ── Summary ─────────────────────────────────────────────────────
    total_dur = round(time.time() - start_time, 1)
    _log(f"[orchestrator] ═══ ALL SCRAPERS COMPLETE in {total_dur}s ═══")

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
            _log(f"[orchestrator] ⚡ Pushed {jobs_pushed} new jobs to Discord INSTANTLY.")
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
    parser = argparse.ArgumentParser(description="JobClaw Speed Scraper — find jobs FAST")
    parser.add_argument("--fast", action="store_true",
                        help="Quick scan only: RSS + Enterprise + GitHub (skip ATS)")
    parser.add_argument("--no-openclaw", action="store_true",
                        help="Skip OpenClaw browser automation (saves API credits)")
    parser.add_argument("--no-github", action="store_true",
                        help="Skip GitHub repo parsing")
    parser.add_argument("--window", type=int, default=24,
                        help="Time window in hours for filtering (default: 24)")
    args = parser.parse_args()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(run_all(
        skip_ats=args.fast,
        skip_openclaw=args.no_openclaw,
        skip_github=args.no_github,
        window_hours=args.window,
    ))


if __name__ == "__main__":
    main()
