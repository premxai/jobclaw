import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

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
from scripts.ops.scrape_schedule_decider import decide as decide_due_jobs
from scripts.utils.logger import _log

SCHEDULER_TIMEZONE = os.getenv("JOBCLAW_SCHEDULER_TIMEZONE", "America/New_York")


def get_scheduler_timezone():
    try:
        return ZoneInfo(SCHEDULER_TIMEZONE)
    except Exception as e:
        _log(f"[standalone-worker] Invalid scheduler timezone {SCHEDULER_TIMEZONE!r}: {e}; falling back to UTC", "WARN")
        return ZoneInfo("UTC")


def env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def discord_configured() -> bool:
    webhook_names = (
        "DISCORD_WEBHOOK_URL",
        "DISCORD_WEBHOOK_AI",
        "DISCORD_WEBHOOK_SWE",
        "DISCORD_WEBHOOK_DATA",
        "DISCORD_WEBHOOK_NEWGRAD",
        "DISCORD_WEBHOOK_PRODUCT",
        "DISCORD_WEBHOOK_RESEARCH",
        "DISCORD_WEBHOOK_GENERAL",
    )
    return any(os.getenv(name) for name in webhook_names) or (
        bool(os.getenv("DISCORD_BOT_TOKEN")) and bool(os.getenv("DISCORD_CHANNEL_ID"))
    )


def add_job_if_enabled(scheduler: AsyncIOScheduler, enabled: bool, *args, **kwargs) -> None:
    job_id = kwargs.get("id", "unknown")
    if enabled:
        kwargs.setdefault("coalesce", True)
        kwargs.setdefault("max_instances", 1)
        kwargs.setdefault("misfire_grace_time", 300)
        scheduler.add_job(*args, **kwargs)
    else:
        _log(f"[standalone-worker] Schedule disabled: {job_id}")


def railway_due_gate_enabled() -> bool:
    return env_flag("JOBCLAW_RAILWAY_DUE_GATE", True)


def should_run_due_job(job_key: str) -> bool:
    """Check the shared DB schedule state before a Railway fallback run."""
    if not railway_due_gate_enabled():
        return True

    try:
        from scripts.database.db_utils import get_connection

        conn = get_connection()
        try:
            payload = decide_due_jobs(conn, datetime.now(timezone.utc))
        finally:
            conn.close()
    except Exception as e:
        _log(f"[standalone-worker] Due gate failed for {job_key}: {e}; skipping fallback run", "WARN")
        return False

    due = bool(payload.get("due", {}).get(job_key))
    _log(
        "[standalone-worker] Due gate "
        f"{job_key}: due={due}, latest={payload.get('latest', {}).get(job_key)}, "
        f"interval={payload.get('interval_minutes', {}).get(job_key)}, "
        f"accepted_unposted_backlog={payload.get('accepted_unposted_backlog')}"
    )
    return due


async def run_due_job(job_key: str, label: str, runner) -> None:
    if not should_run_due_job(job_key):
        _log(f"[standalone-worker] Skipping {label}; DB schedule says it is not due.")
        return
    await runner()


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
            platforms={"workday", "workable", "rippling", "smartrecruiters", "bamboohr"},
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


async def execute_due_hot():
    await run_due_job("hot", "Hot Scraper", execute_hot)


async def execute_due_fast():
    await run_due_job("fast", "Fast Scraper", execute_fast)


async def execute_due_medium():
    await run_due_job("medium", "Medium Scraper", execute_medium)


async def execute_due_discord_push():
    await run_due_job("discord", "Discord Push", execute_discord_push)


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

    scheduler = AsyncIOScheduler(timezone=get_scheduler_timezone())
    _log(f"[standalone-worker] Scheduler timezone: {SCHEDULER_TIMEZONE}")

    # GitHub Actions remains the primary scraper surface, but GitHub cron can lag
    # or skip ticks. The stale fallback wakes on Railway and runs only when the
    # shared DB schedule says GitHub missed the target interval.
    _stale_fallback = env_flag("JOBCLAW_RAILWAY_STALE_FALLBACK", True)
    _bulk_fallback = env_flag("JOBCLAW_RAILWAY_BULK_FALLBACK", False)
    enabled_tasks = {
        "hot": env_flag("JOBCLAW_RAILWAY_ENABLE_HOT", _stale_fallback),
        "fast": env_flag("JOBCLAW_RAILWAY_ENABLE_FAST", _stale_fallback or _bulk_fallback),
        "medium": env_flag("JOBCLAW_RAILWAY_ENABLE_MEDIUM", _stale_fallback or _bulk_fallback),
        "deep": env_flag("JOBCLAW_RAILWAY_ENABLE_DEEP", _bulk_fallback),
        "discord_push": env_flag("JOBCLAW_RAILWAY_ENABLE_DISCORD", _stale_fallback and discord_configured()),
        "validate_targets": env_flag("JOBCLAW_RAILWAY_ENABLE_VALIDATION", False),
    }
    _log(
        f"[standalone-worker] Enabled schedules: {enabled_tasks}; "
        f"stale_fallback={_stale_fallback}, due_gate={railway_due_gate_enabled()}"
    )

    # 1. Hot companies — Railway checks every 15 minutes, but only runs when due.
    add_job_if_enabled(
        scheduler,
        enabled_tasks["hot"],
        execute_due_hot,
        IntervalTrigger(minutes=15),
        id="hot",
        name="Hot Scraper fallback (due-gated every 15 min)",
        replace_existing=True,
    )

    # 2. Fast tier — due-gated stale fallback for missed GitHub ticks.
    add_job_if_enabled(
        scheduler,
        enabled_tasks["fast"],
        execute_due_fast,
        IntervalTrigger(minutes=15),
        id="fast",
        name="Fast Tier fallback (due-gated every 15 min)",
        replace_existing=True,
    )

    # 3. Medium tier — due-gated stale fallback for missed GitHub ticks.
    add_job_if_enabled(
        scheduler,
        enabled_tasks["medium"],
        execute_due_medium,
        IntervalTrigger(minutes=15),
        id="medium",
        name="Medium Tier fallback (due-gated every 15 min)",
        replace_existing=True,
    )

    # 4. Discord push — enabled automatically on Railway when webhooks are configured.
    add_job_if_enabled(
        scheduler,
        enabled_tasks["discord_push"],
        execute_due_discord_push,
        IntervalTrigger(minutes=5),
        id="discord_push",
        name="Discord Push fallback (due-gated every 5 min)",
        replace_existing=True,
    )

    # 5. Target validation — every 6 hours Eastern, offset away from scraper starts
    add_job_if_enabled(
        scheduler,
        enabled_tasks["validate_targets"],
        execute_validate_targets,
        CronTrigger(hour="*/6", minute=40),
        id="validate_targets",
        name="Target Validation (every 6 hours)",
        replace_existing=True,
    )

    # 6. Deep tier — disabled on Railway by default; GitHub Actions owns full sweeps.
    add_job_if_enabled(
        scheduler,
        enabled_tasks["deep"],
        execute_deep,
        CronTrigger(hour=23, minute=0),
        id="deep",
        name="Deep Tier (daily 23:00 Eastern)",
        replace_existing=True,
    )

    scheduler.start()
    _log("[standalone-worker] Scheduler started and running. Press Ctrl+C to exit.")
    for job in scheduler.get_jobs():
        _log(f"[standalone-worker] Scheduled job {job.id}: next_run={job.next_run_time}")

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
