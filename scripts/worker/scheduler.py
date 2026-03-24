"""
APScheduler — in-process cron that enqueues ARQ tasks on a schedule.

Runs inside the same Railway process as the ARQ worker. Replaces all
GitHub Actions cron schedules with persistent, always-on scheduling.

Schedule (mirrors the old GitHub Actions crons):
  task_hot          every 5 minutes
  task_fast         every hour (top of hour)
  task_medium       every hour (offset by 2 min to avoid collision)
  task_discord_push every 15 minutes
  task_deep         daily at 23:00 UTC
"""

import asyncio
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from scripts.utils.logger import _log

logging.getLogger("apscheduler").setLevel(logging.WARNING)


def _enqueue(pool, task_name: str):
    """Helper: enqueue a task, swallowing errors so the scheduler keeps running."""

    async def _do():
        try:
            await pool.enqueue_job(task_name)
            _log(f"[scheduler] Enqueued {task_name}")
        except Exception as e:
            _log(f"[scheduler] Failed to enqueue {task_name}: {e}", "WARN")

    asyncio.ensure_future(_do())


async def start_scheduler(pool) -> AsyncIOScheduler:
    """
    Create and start the APScheduler with all cron jobs.
    Returns the scheduler so the caller can shut it down cleanly.
    """
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Hot companies — every 5 minutes
    scheduler.add_job(
        lambda: _enqueue(pool, "task_hot"),
        IntervalTrigger(minutes=5),
        id="hot",
        name="Hot Scraper (every 5 min)",
        replace_existing=True,
    )

    # Fast tier — every hour at :00
    scheduler.add_job(
        lambda: _enqueue(pool, "task_fast"),
        CronTrigger(minute=0),
        id="fast",
        name="Fast Tier (hourly)",
        replace_existing=True,
    )

    # Medium tier — every hour at :02 (slight offset avoids DB collision with fast)
    scheduler.add_job(
        lambda: _enqueue(pool, "task_medium"),
        CronTrigger(minute=2),
        id="medium",
        name="Medium Tier (hourly, offset 2 min)",
        replace_existing=True,
    )

    # Discord push — every 15 minutes
    scheduler.add_job(
        lambda: _enqueue(pool, "task_discord_push"),
        CronTrigger(minute="*/15"),
        id="discord_push",
        name="Discord Push (every 15 min)",
        replace_existing=True,
    )

    # Deep tier — daily at 23:00 UTC
    scheduler.add_job(
        lambda: _enqueue(pool, "task_deep"),
        CronTrigger(hour=23, minute=0),
        id="deep",
        name="Deep Tier (daily 23:00 UTC)",
        replace_existing=True,
    )

    scheduler.start()
    _log("[scheduler] Started — hot/5min, fast/1hr, medium/1hr+2, push/15min, deep/23:00UTC")
    return scheduler
