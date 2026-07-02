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

from scripts.database.db_utils import get_connection, insert_job, log_scraper_run, mark_company_failure
from scripts.ingestion.ats_adapters import get_adapter
from scripts.ingestion.role_filter import matches_target_role
from scripts.ingestion.us_filter import is_us_location
from scripts.utils.http_client import create_session
from scripts.utils.logger import _log

HOT_COMPANIES_FILE = PROJECT_ROOT / "config" / "hot_companies.json"

# Per-category Discord webhook URLs — matching discord_push.py
_CATEGORY_WEBHOOKS = {
    "AI/ML": os.getenv("DISCORD_WEBHOOK_AI", ""),
    "Data Science": os.getenv("DISCORD_WEBHOOK_DATA", ""),
    "Data Engineering": os.getenv("DISCORD_WEBHOOK_DATA", ""),
    "Data Analyst": os.getenv("DISCORD_WEBHOOK_DATA", ""),
    "SWE": os.getenv("DISCORD_WEBHOOK_SWE", ""),
    "New Grad": os.getenv("DISCORD_WEBHOOK_NEWGRAD", ""),
    "Product": os.getenv("DISCORD_WEBHOOK_PRODUCT", ""),
    "Research": os.getenv("DISCORD_WEBHOOK_RESEARCH", ""),
}

# Fallback webhook definition
_SINGLE_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")
_GENERAL_WEBHOOK = os.getenv("DISCORD_WEBHOOK_GENERAL", "")
DISCORD_WEBHOOK = _GENERAL_WEBHOOK or _SINGLE_WEBHOOK or next((v for v in _CATEGORY_WEBHOOKS.values() if v), "")
DISCORD_DRY_RUN = os.getenv("JOBCLAW_DISCORD_DRY_RUN", os.getenv("DISCORD_DRY_RUN", "0")).strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}

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


def _unique_webhooks(urls: list[str]) -> list[str]:
    """Return non-empty webhook URLs in order, removing duplicates."""
    seen = set()
    result = []
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        result.append(url)
    return result


def _webhook_candidates(category: str) -> list[str]:
    """Candidate webhooks for hot alerts, from category match to fallback."""
    return _unique_webhooks(
        [
            _CATEGORY_WEBHOOKS.get(category, ""),
            _GENERAL_WEBHOOK,
            _SINGLE_WEBHOOK,
            DISCORD_WEBHOOK,
            *_CATEGORY_WEBHOOKS.values(),
        ]
    )


async def _send_hot_discord_alert(job: dict, minutes_old: float):
    """Fire an instant Discord alert for a freshly discovered hot-company job."""
    cats = []
    if job.get("keywords_matched"):
        try:
            cats = (
                json.loads(job["keywords_matched"])
                if isinstance(job["keywords_matched"], str)
                else job["keywords_matched"]
            )
        except Exception:
            pass

    prim_cat = cats[0] if cats else ""
    webhook_urls = _webhook_candidates(prim_cat)
    if not webhook_urls:
        return

    freshness = _format_freshness(minutes_old)
    category = f" · {prim_cat}" if prim_cat else ""

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

    if DISCORD_DRY_RUN:
        _log_hot(f"DRY_RUN: would send hot alert for {job['company']} — {job['title']}")
        return

    try:
        import urllib.error
        import urllib.request

        data = json.dumps(payload).encode("utf-8")
        for index, webhook_url in enumerate(webhook_urls):
            req = urllib.request.Request(
                webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status in (200, 204):
                        if index > 0:
                            _log_hot(f"Discord hot alert used fallback webhook #{index + 1}.", "WARN")
                        return
                    _log_hot(f"Discord alert failed: HTTP {resp.status}", "WARN")
            except urllib.error.HTTPError as e:
                _log_hot(f"Discord alert webhook #{index + 1} failed: HTTP {e.code}", "WARN")
            except Exception as e:
                _log_hot(f"Discord alert webhook #{index + 1} error: {e}", "WARN")

            if index < len(webhook_urls) - 1:
                _log_hot(f"Trying Discord hot-alert fallback #{index + 2}.", "WARN")
    except Exception as e:
        _log_hot(f"Discord alert error: {e}", "WARN")


async def _delayed_fetch(delay_s, coro):
    """Stagger coroutine startup by a deterministic delay to avoid request bursts."""
    await asyncio.sleep(delay_s)
    return await coro


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

    # HACK 3: Filter out dead companies (persistent 404s) before scraping
    conn_dead = get_connection()
    try:
        cursor = conn_dead.cursor()
        cursor.execute("SELECT slug FROM companies WHERE is_dead = 1")
        dead_slugs = {row[0] for row in cursor.fetchall()}
        hot_list = [c for c in hot_list if c.get("slug") not in dead_slugs]
        if dead_slugs:
            _log_hot(f"Skipping {len(dead_slugs)} dead company slugs (consistent 404s)")
    finally:
        conn_dead.close()

    conn = get_connection()
    new_jobs = 0
    alert_jobs = []

    from scripts.utils.http_client import RateLimiter

    rate_limiter = RateLimiter()

    async with create_session(rate_limiter, max_connections=30, max_per_host=15) as session:
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

            # HACK 4: Stagger requests with a deterministic per-company delay (0–29s)
            delay = (hash(slug) & 0xFFFF) % 30
            tasks.append((name, ats, _delayed_fetch(delay, adapter.fetch(session, slug, name))))

        # Run all in parallel — cap at 200s (well within the 5-min cycle)
        task_futures = [asyncio.ensure_future(t[2]) for t in tasks]
        done, pending = await asyncio.wait(task_futures, timeout=200)
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

        # HACK 3: Track permanent failures (404s) in the DB so dead companies are skipped
        conn_fail = get_connection()
        try:
            for (name, ats, _), result in zip(tasks, results):
                if isinstance(result, Exception):
                    err_str = str(result)
                    if "404" in err_str or "permanent" in err_str.lower():
                        slug = next((c.get("slug") for c in hot_list if c.get("company") == name), None)
                        if slug:
                            mark_company_failure(conn_fail, slug, permanent=True)
                    _log_hot(f"[{ats}/{name}] Error: {result}", "WARN")
                    continue

                for job in result:
                    # Role filter
                    if not matches_target_role(job.title, experience_years=getattr(job, "experience_years", None)):
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
        finally:
            conn_fail.close()

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
