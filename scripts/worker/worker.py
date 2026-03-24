"""
ARQ Worker — async task definitions for the Railway persistent worker.

Each function here is an ARQ task. The worker picks tasks off the Redis
queue and runs them. No timeouts, no ephemeral runners — just tasks that
run to completion.

WorkerSettings controls concurrency (max_jobs), per-task timeout, and retry
behaviour. Scrapers themselves are unchanged — this is purely a thin wrapper.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import arq
import arq.connections

from scripts.utils.logger import _log


# ── Task functions ───────────────────────────────────────────────────────────


async def task_hot(ctx):
    """Scrape 192 hot companies (every 5 min)."""
    from scripts.ingestion.scrape_hot import run_hot_scraper

    _log("[worker] Starting task_hot")
    await run_hot_scraper()


async def task_fast(ctx):
    """Fast tier: Greenhouse + Lever + Ashby, 4-shard rotation (every hour)."""
    from scripts.ingestion.run_all_scrapers import run_all

    _log("[worker] Starting task_fast")
    await run_all(
        tier="fast",
        skip_ats=False,
        skip_github=False,
        run_brave=False,
        window_hours=24,
        skip_platforms={"gem"},
        platforms={"greenhouse", "lever", "ashby"},
    )


async def task_medium(ctx):
    """Medium tier: Workday + Rippling + SmartRecruiters, 8-shard rotation (every hour)."""
    from scripts.ingestion.run_all_scrapers import run_all, get_next_shard

    _log("[worker] Starting task_medium")
    _MEDIUM_SHARDS = 8
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
    )


async def task_deep(ctx):
    """Deep tier: all platforms + Brave + AI pipeline (daily at 11PM UTC)."""
    from scripts.ingestion.run_all_scrapers import run_all

    _log("[worker] Starting task_deep")
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
    # AI pipeline runs automatically inside run_all when run_brave=True


async def task_discord_push(ctx):
    """Push unposted jobs to Discord (every 15 min)."""
    from scripts.discord_push import push_new_jobs_to_discord

    _log("[worker] Starting task_discord_push")
    n = await push_new_jobs_to_discord()
    _log(f"[worker] task_discord_push: pushed {n} jobs")


# ── Worker settings ──────────────────────────────────────────────────────────

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")  # fallback for local dev only


class WorkerSettings:
    functions = [task_hot, task_fast, task_medium, task_deep, task_discord_push]
    redis_settings = arq.connections.RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379"))

    # Allow up to 5 scraper tasks to run concurrently (they're I/O bound)
    max_jobs = 5

    # 30 minutes per task — scrapers run until done, no artificial kills
    job_timeout = 1800

    # Retry failed tasks once after 60s
    retry_jobs = True
    max_tries = 2
    retry_delay = 60
