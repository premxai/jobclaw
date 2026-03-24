"""
Worker entrypoint — starts the ARQ worker + APScheduler in one process.

Usage:
    python scripts/worker/main.py

Railway deployment: set startCommand to this file.
Local dev: docker compose up worker

The process blocks on run_worker() which processes tasks from Redis.
The scheduler runs concurrently inside the same event loop.

NOTE: We manage the event loop manually (not asyncio.run) so that ARQ's
sync run_worker() can call loop.run_until_complete() without hitting
"This event loop is already running".
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

REDIS_URL = os.getenv("REDIS_URL", "")

if not REDIS_URL:
    raise RuntimeError(
        "REDIS_URL environment variable is not set. "
        "Set it in Railway → service → Variables with your Upstash rediss:// URL."
    )


def main():
    _log("[worker] JobClaw persistent worker starting...")
    _log(f"[worker] Connecting to Redis: {REDIS_URL.split('@')[-1]}")

    # Create a fresh event loop — NOT asyncio.run() — so that ARQ's sync
    # run_worker can call loop.run_until_complete() without crashing.
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    redis_settings = RedisSettings.from_dsn(REDIS_URL)

    # Async setup: create Redis pool + start APScheduler on the loop.
    # The loop is not yet "running" so run_until_complete works fine here.
    pool = loop.run_until_complete(create_pool(redis_settings))
    scheduler = loop.run_until_complete(start_scheduler(pool))

    _log("[worker] Scheduler running. Starting ARQ worker loop...")

    try:
        # run_worker is sync — it picks up the current event loop and calls
        # loop.run_until_complete(main_task) to block until shutdown.
        run_worker(WorkerSettings)
    finally:
        scheduler.shutdown(wait=False)
        loop.run_until_complete(pool.aclose())
        loop.close()
        _log("[worker] Shutdown complete.")


if __name__ == "__main__":
    main()
