"""
Hot Company Fast Scraper — 5-minute real-time job monitoring.

Scrapes only the ~200 highest-signal companies every 5 minutes.
Fires instant Discord alerts with job freshness ("🔥 2 min ago").
Designed to make users consistently be among the first 5-10 applicants.

Run via:
  python scripts/ingestion/scrape_hot.py       (one-shot)
  GitHub Actions: .github/workflows/scrape_hot.yml (every 5 min)
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from scripts.database.db_utils import get_connection, insert_job, log_scraper_run
from scripts.ingestion.ats_adapters import get_adapter
from scripts.ingestion.role_filter import matches_target_role
from scripts.ingestion.us_filter import is_us_location
from scripts.utils.http_client import create_session
from scripts.utils.logger import _log

HOT_COMPANIES_FILE = PROJECT_ROOT / "config" / "hot_companies.json"
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")

# How old can a job be to still be considered "fresh" for hot-alerts
# (jobs older than this from the DB's first_seen are already known)
HOT_ALERT_WINDOW_MINUTES = 10


def _log_hot(msg: str, level: str = "INFO"):
    _log(msg, level, "hot_scraper")


def _minutes_ago(dt_str: str) -> float:
    """Return how many minutes ago a datetime string was."""
    try:
        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return delta.total_seconds() / 60
    except Exception:
        return 999


def _format_freshness(minutes: float) -> str:
    """Format freshness label for Discord."""
    if minutes < 2:
        return "🔥🔥🔥 Just posted"
    elif minutes < 5:
        return f"🔥🔥 {int(minutes)} min ago"
    elif minutes < 15:
        return f"🔥 {int(minutes)} min ago"
    elif minutes < 60:
        return f"⚡ {int(minutes)} min ago"
    else:
        return f"⏰ {int(minutes / 60)}h ago"


async def _send_hot_discord_alert(job: dict, minutes_old: float):
    """Fire an instant Discord alert for a freshly discovered hot-company job."""
    if not DISCORD_WEBHOOK:
        return

    freshness = _format_freshness(minutes_old)
    category = ""
    if job.get("keywords_matched"):
        try:
            cats = (
                json.loads(job["keywords_matched"])
                if isinstance(job["keywords_matched"], str)
                else job["keywords_matched"]
            )
            if cats:
                category = f" · {cats[0]}"
        except Exception:
            pass

    # Build a compact, actionable alert embed
    embed = {
        "title": f"{job['title']}",
        "url": job["url"],
        "color": 0xFF6B35,  # JobClaw orange
        "fields": [
            {"name": "🏢 Company", "value": job["company"], "inline": True},
            {"name": "📍 Location", "value": job.get("location", "United States"), "inline": True},
            {"name": "⏱ Freshness", "value": freshness, "inline": True},
            {"name": "🔗 Apply Now", "value": f"[Open Application →]({job['url']})", "inline": False},
        ],
        "footer": {"text": f"JobClaw Hot Alert{category} · Be one of the first applicants!"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    payload = {"embeds": [embed]}

    try:
        import urllib.request

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            DISCORD_WEBHOOK,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                _log_hot(f"Discord alert failed: HTTP {resp.status}", "WARN")
    except Exception as e:
        _log_hot(f"Discord alert error: {e}", "WARN")


async def run_hot_scraper():
    """
    Fast scraper for hot companies. Runs in <2 minutes typically.
    Reports freshness labels for instant user action.
    """
    start_time = time.time()

    # Load hot company list
    if not HOT_COMPANIES_FILE.exists():
        _log_hot("hot_companies.json not found — aborting", "ERROR")
        return

    with open(HOT_COMPANIES_FILE, encoding="utf-8") as f:
        config = json.load(f)
    hot_list = config.get("companies", [])
    _log_hot(f"🔥 Hot Scraper starting — monitoring {len(hot_list)} companies")

    conn = get_connection()
    new_jobs = 0
    alert_jobs = []

    from scripts.utils.http_client import RateLimiter

    rate_limiter = RateLimiter()

    async with create_session(rate_limiter) as session:
        tasks = []
        for company in hot_list:
            ats = company.get("ats")
            slug = company.get("slug")
            name = company.get("company", slug)
            if not ats or not slug:
                continue

            adapter = get_adapter(ats)
            if adapter is None:
                continue

            tasks.append((name, ats, adapter.fetch(session, slug, name)))

        # Run all in parallel — cap at 90s so the workflow never times out
        task_futures = [asyncio.ensure_future(t[2]) for t in tasks]
        done, pending = await asyncio.wait(task_futures, timeout=90)
        for p in pending:
            p.cancel()
        # Build results list aligned with tasks (pending → TimeoutError)
        results = []
        for f in task_futures:
            if f in done:
                results.append(f.exception() if f.exception() else f.result())
            else:
                results.append(Exception("timeout"))
        if pending:
            _log_hot(f"{len(pending)}/{len(tasks)} companies timed out (>90s) — skipped", "WARN")

        for (name, ats, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                _log_hot(f"[{ats}/{name}] Error: {result}", "WARN")
                continue

            for job in result:
                # Role filter
                if not matches_target_role(job.title):
                    continue
                # Location filter
                if not is_us_location(job.location):
                    continue

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
                    new_jobs += 1
                    # All new hot-company jobs are by definition fresh — alert immediately
                    alert_jobs.append((j_dict, 0))  # 0 minutes old = just found

    # Batch-send Discord alerts (don't spam — at most 20 per run)
    if alert_jobs:
        _log_hot(f"🔔 Sending {min(len(alert_jobs), 20)} instant Discord alerts...")
        for job_dict, mins_old in alert_jobs[:20]:
            await _send_hot_discord_alert(job_dict, mins_old)
            await asyncio.sleep(0.3)  # Prevent Discord rate-limiting

    duration = round(time.time() - start_time, 2)

    try:
        log_scraper_run(conn, "scrape_hot", len(hot_list), new_jobs, duration, "")
    finally:
        conn.close()

    _log_hot(
        f"🔥 Hot Scraper Complete. "
        f"New={new_jobs}, Companies={len(hot_list)}, "
        f"Alerts={min(len(alert_jobs), 20)}, Duration={duration}s"
    )
    return new_jobs


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_hot_scraper())
