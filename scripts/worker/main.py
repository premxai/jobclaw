"""
Worker entrypoint — starts the ARQ worker + APScheduler in one process.

Usage:
    python scripts/worker/main.py

Railway deployment: set startCommand to this file.
Local dev: docker compose up worker

The process blocks on run_worker() which processes tasks from Redis.
The scheduler runs concurrently inside the same event loop.
"""

import asyncio
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

from arq import run_worker
from arq.connections import RedisSettings, create_pool

from scripts.utils.logger import _log
from scripts.worker.scheduler import start_scheduler
from scripts.worker.worker import WorkerSettings

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


async def main():
    _log("[worker] JobClaw persistent worker starting...")
    _log(f"[worker] Connecting to Redis: {REDIS_URL.split('@')[-1]}")  # hide credentials

    redis_settings = RedisSettings.from_dsn(REDIS_URL)

    # Create pool for the scheduler to enqueue jobs
    pool = await create_pool(redis_settings)

    # Start APScheduler (enqueues tasks on schedule)
    scheduler = await start_scheduler(pool)

    _log("[worker] Scheduler running. Starting ARQ worker loop...")

    try:
        # run_worker blocks indefinitely, processing tasks from the Redis queue
        await run_worker(WorkerSettings, exit_on_exc=False)
    finally:
        scheduler.shutdown(wait=False)
        await pool.aclose()
        _log("[worker] Shutdown complete.")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
