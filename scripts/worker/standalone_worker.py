import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from scripts.discord_push import push_new_jobs_to_discord
from scripts.ingestion.run_all_scrapers import get_next_shard, run_all
from scripts.ingestion.scrape_hot import run_hot_scraper
from scripts.utils.logger import _log


async def execute_hot():
    _log("[standalone-worker] Starting Hot Scraper...")
    try:
        await run_hot_scraper()
    except Exception as e:
        _log(f"[standalone-worker] Hot Scraper failed: {e}", "ERROR")


async def execute_fast():
    _log("[standalone-worker] Starting Fast Scraper...")
    try:
        _FAST_SHARDS = 4
        shard = get_next_shard("fast_ats_ghla", _FAST_SHARDS)
        await run_all(
            tier="fast",
            skip_ats=False,
            skip_github=False,
            run_brave=False,
            window_hours=24,
            skip_platforms={"gem"},
            platforms={"greenhouse", "lever", "ashby"},
            shard=shard,
            total_shards=_FAST_SHARDS,
        )
    except Exception as e:
        _log(f"[standalone-worker] Fast Scraper failed: {e}", "ERROR")


async def execute_medium():
    _log("[standalone-worker] Starting Medium Scraper...")
    try:
        _MEDIUM_SHARDS = int(os.getenv("JOBCLAW_WORKDAY_SHARDS", "16"))
        shard = get_next_shard("medium_ats_workday", _MEDIUM_SHARDS)
        await run_all(
            tier="medium",
            skip_ats=False,
            skip_github=False,
            run_brave=False,
            window_hours=8,
            skip_platforms={"gem"},
            platforms={"workday", "rippling", "smartrecruiters", "bamboohr"},
            shard=shard,
            total_shards=_MEDIUM_SHARDS,
            target_limit=int(os.getenv("JOBCLAW_MEDIUM_TARGET_LIMIT", "800")),
        )
    except Exception as e:
        _log(f"[standalone-worker] Medium Scraper failed: {e}", "ERROR")


async def execute_deep():
    _log("[standalone-worker] Starting Deep Scraper...")
    try:
        await run_all(
            tier="deep",
            skip_ats=False,
            skip_github=False,
            run_brave=True,
            window_hours=24,
            skip_platforms={"gem"},
            platforms=None,
            shard=None,
            total_shards=4,
        )
    except Exception as e:
        _log(f"[standalone-worker] Deep Scraper failed: {e}", "ERROR")


async def execute_discord_push():
    _log("[standalone-worker] Starting Discord Push...")
    try:
        n = await push_new_jobs_to_discord()
        _log(f"[standalone-worker] Discord Push complete: posted {n} jobs.")
    except Exception as e:
        _log(f"[standalone-worker] Discord Push failed: {e}", "ERROR")


async def execute_validate_targets():
    _log("[standalone-worker] Starting target validation...")
    try:
        from scripts.ingestion.validate_targets import validate_targets

        result = await validate_targets(limit=500, concurrency=6)
        _log(f"[standalone-worker] Target validation complete: {result}")
    except Exception as e:
        _log(f"[standalone-worker] Target validation failed: {e}", "ERROR")


async def main():
    _log("[standalone-worker] JobClaw Standalone Persistent Worker starting...")

    try:
        from scripts.database.db_utils import get_companies_for_scrape, get_connection
        from scripts.database.seed_companies import seed_companies

        conn = get_connection()
        try:
            has_companies = bool(get_companies_for_scrape(conn, shard=0, total_shards=1))
        finally:
            conn.close()
        if not has_companies:
            _log("[standalone-worker] Companies table empty — seeding canonical targets.")
            seed_companies()
    except Exception as e:
        _log(f"[standalone-worker] Company seed check failed: {e}", "WARN")

    scheduler = AsyncIOScheduler(timezone="UTC")

    # 1. Hot companies — every 15 minutes
    scheduler.add_job(
        execute_hot,
        IntervalTrigger(minutes=15),
        id="hot",
        name="Hot Scraper (every 15 min)",
        replace_existing=True,
    )

    # 2. Fast tier — every hour at :00
    scheduler.add_job(
        execute_fast,
        CronTrigger(minute=0),
        id="fast",
        name="Fast Tier (hourly)",
        replace_existing=True,
    )

    # 3. Medium tier — every hour at :02 (offset to avoid DB collisions)
    scheduler.add_job(
        execute_medium,
        CronTrigger(minute=2),
        id="medium",
        name="Medium Tier (hourly, offset 2 min)",
        replace_existing=True,
    )

    # 4. Discord push — every 15 minutes (offset by 5 min to push fresh scraped jobs)
    scheduler.add_job(
        execute_discord_push,
        CronTrigger(minute="5,20,35,50"),
        id="discord_push",
        name="Discord Push (every 15 min, offset 5)",
        replace_existing=True,
    )

    # 5. Target validation — every 6 hours, offset away from scraper starts
    scheduler.add_job(
        execute_validate_targets,
        CronTrigger(hour="*/6", minute=40),
        id="validate_targets",
        name="Target Validation (every 6 hours)",
        replace_existing=True,
    )

    # 6. Deep tier — daily at 23:00 UTC
    scheduler.add_job(
        execute_deep,
        CronTrigger(hour=23, minute=0),
        id="deep",
        name="Deep Tier (daily 23:00 UTC)",
        replace_existing=True,
    )

    scheduler.start()
    _log("[standalone-worker] Scheduler started and running. Press Ctrl+C to exit.")

    # Keep the process alive
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        _log("[standalone-worker] Shutting down...")
        scheduler.shutdown()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
