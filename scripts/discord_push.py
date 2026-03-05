"""
Discord Job Card Pusher — posts individual job cards to category channels.

Each job is posted as a rich embed card to the appropriate Discord channel
based on its keyword category (AI, SWE, Data, etc.). If the category can't
be determined, jobs go to the general fallback channel.

Card fields: Title, Company, Location, Date Posted, ATS Source, Apply link.

Setup:
  Bot Token + Channel IDs in .env (see .env.example)
  OR: DISCORD_WEBHOOK_URL for single-channel webhook mode.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.logger import _log
from scripts.database.db_utils import get_connection, get_unposted_jobs, mark_jobs_posted
from scripts.utils.dedup_file import load_posted_hashes, save_posted_hashes, is_already_posted, mark_as_posted

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


def log(msg: str, level: str = "INFO"):
    _log(msg, level, "discord_push")


# ═══════════════════════════════════════════════════════════════════════
# CHANNEL ROUTING
# ═══════════════════════════════════════════════════════════════════════

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
GENERAL_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")

# Category → Channel ID mapping
CATEGORY_CHANNELS = {
    "AI/ML":             os.getenv("DISCORD_CHANNEL_AI"),
    "Data Science":      os.getenv("DISCORD_CHANNEL_DATA"),
    "Data Engineering":  os.getenv("DISCORD_CHANNEL_DATA"),
    "Data Analyst":      os.getenv("DISCORD_CHANNEL_DATA"),
    "SWE":               os.getenv("DISCORD_CHANNEL_SWE"),
    "New Grad":          os.getenv("DISCORD_CHANNEL_NEWGRAD"),
    "Product":           os.getenv("DISCORD_CHANNEL_PRODUCT"),
    "Research":          os.getenv("DISCORD_CHANNEL_RESEARCH"),
}

CATEGORY_EMOJIS = {
    "AI/ML": "🤖", "Data Science": "🔬", "Data Engineering": "🔧",
    "Data Analyst": "📊", "SWE": "💻", "New Grad": "🎓",
    "Product": "📦", "Research": "🧪", "Uncategorized": "💼",
}

CATEGORY_COLORS = {
    "AI/ML": 0x9B59B6,        # Purple
    "Data Science": 0x3498DB,  # Blue
    "Data Engineering": 0x1ABC9C, # Teal
    "Data Analyst": 0x2ECC71,  # Green
    "SWE": 0xE67E22,           # Orange
    "New Grad": 0xF1C40F,      # Yellow
    "Product": 0xE74C3C,       # Red
    "Research": 0x95A5A6,      # Gray
    "Uncategorized": 0x546E7A, # Dark gray
}

ATS_LABELS = {
    "greenhouse": "Greenhouse", "lever": "Lever", "workday": "Workday",
    "ashby": "Ashby", "smartrecruiters": "SmartRecruiters",
    "rippling": "Rippling", "workable": "Workable", "icims": "iCIMS",
    "github-swe-newgrad": "GitHub", "github-ai-newgrad": "GitHub",
    "github-internship": "GitHub", "github-new-grad": "GitHub",
    "remoteok": "RemoteOK", "remotive": "Remotive", "wwr": "WWR",
    "dice": "Dice", "wellfound": "Wellfound", "ycombinator": "Y Combinator",
    "linkedin": "LinkedIn", "indeed": "Indeed", "glassdoor": "Glassdoor",
}


def _get_category(job: dict) -> str:
    """Get the primary category for a job."""
    cats = job.get("keywords_matched", [])
    if isinstance(cats, str):
        try:
            cats = json.loads(cats)
        except (json.JSONDecodeError, TypeError):
            cats = []
    return cats[0] if cats else "Uncategorized"


def _get_channel_id(category: str) -> str | None:
    """Resolve a category to a Discord channel ID. Falls back to general."""
    channel = CATEGORY_CHANNELS.get(category)
    if channel:
        return channel
    return GENERAL_CHANNEL_ID


def _format_date(date_str: str | None) -> str:
    """Format a date string for display."""
    if not date_str:
        return "Unknown"
    try:
        d = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return d.strftime("%b %d, %Y")
    except (ValueError, TypeError):
        return date_str[:10] if len(date_str) >= 10 else date_str


def _build_job_embed(job: dict) -> dict:
    """Build a single Discord embed card for one job."""
    title = job.get("title", "Unknown Role")
    company = job.get("company", "Unknown")
    location = job.get("location", "Remote")
    url = job.get("url", "")
    date_posted = job.get("date_posted") or job.get("first_seen", "")
    source_ats = job.get("source_ats", "")
    category = _get_category(job)

    emoji = CATEGORY_EMOJIS.get(category, "💼")
    color = CATEGORY_COLORS.get(category, 0x546E7A)
    ats_label = ATS_LABELS.get(source_ats.lower(), source_ats) if source_ats else "Direct"

    # Truncate location if too long
    if location and len(location) > 40:
        location = location[:37] + "..."

    embed = {
        "title": f"{emoji}  {title}",
        "color": color,
        "fields": [
            {"name": "🏢 Company", "value": company, "inline": True},
            {"name": "📍 Location", "value": location or "Remote", "inline": True},
            {"name": "📅 Posted", "value": _format_date(date_posted), "inline": True},
            {"name": "🔗 Source", "value": ats_label, "inline": True},
            {"name": "🏷️ Category", "value": category, "inline": True},
        ],
        "footer": {"text": f"JobClaw • {ats_label}"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if url:
        embed["url"] = url
        embed["fields"].append(
            {"name": "📎 Apply", "value": f"[Click here to apply]({url})", "inline": False}
        )

    # Salary if available
    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")
    if salary_min or salary_max:
        if salary_min and salary_max:
            salary = f"${int(salary_min / 1000)}k – ${int(salary_max / 1000)}k"
        elif salary_min:
            salary = f"${int(salary_min / 1000)}k+"
        else:
            salary = f"Up to ${int(salary_max / 1000)}k"
        # Insert salary as the 3rd field (after Company, Location)
        embed["fields"].insert(2, {"name": "💰 Salary", "value": salary, "inline": True})

    return embed


# ═══════════════════════════════════════════════════════════════════════
# SENDING — Bot API (multi-channel) or Webhook (single-channel)
# ═══════════════════════════════════════════════════════════════════════

# Shared headers — User-Agent is required or Cloudflare returns 1010
_DISCORD_HEADERS = {
    "User-Agent": "JobClaw/1.0 (https://github.com/premxai/jobclaw)",
    "Content-Type": "application/json",
}


async def _send_card_via_bot(session, channel_id: str, embed: dict) -> bool:
    """Send a single job card to a specific channel via Bot API (3-retry exponential backoff)."""
    import asyncio
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        **_DISCORD_HEADERS,
        "Authorization": f"Bot {BOT_TOKEN}",
    }

    for attempt in range(3):
        resp = await session.post(url, headers=headers, json={"embeds": [embed]})

        if resp.status in (200, 201):
            return True

        if resp.status == 429:
            try:
                data = await resp.json()
                wait = data.get("retry_after", 2.0)
            except Exception:
                wait = 2.0
            backoff = max(wait, 2.0) * (2 ** attempt)
            log(f"Rate limited — waiting {backoff:.1f}s (attempt {attempt + 1}/3)", "WARN")
            await asyncio.sleep(backoff)
            continue

        log(f"Bot API returned {resp.status} for channel {channel_id}", "WARN")
        return False

    log(f"Bot API — retries exhausted for channel {channel_id}", "WARN")
    return False


async def _send_card_via_webhook(session, embed: dict) -> bool:
    """Send a single job card via webhook (3-retry exponential backoff)."""
    import asyncio

    for attempt in range(3):
        resp = await session.post(WEBHOOK_URL, headers=_DISCORD_HEADERS, json={"embeds": [embed]})

        if resp.status in (200, 204):
            return True

        if resp.status == 429:
            try:
                data = await resp.json()
                wait = data.get("retry_after", 2.0)
            except Exception:
                wait = 2.0
            backoff = max(wait, 2.0) * (2 ** attempt)
            log(f"Rate limited — waiting {backoff:.1f}s (attempt {attempt + 1}/3)", "WARN")
            await asyncio.sleep(backoff)
            continue

        log(f"Webhook returned {resp.status}", "WARN")
        return False

    log("Webhook — retries exhausted", "WARN")
    return False


# ═══════════════════════════════════════════════════════════════════════
# MAIN PUSH FUNCTION
# ═══════════════════════════════════════════════════════════════════════

async def push_new_jobs_to_discord():
    """
    Called by the orchestrator IMMEDIATELY after scraping finishes.
    Posts each job as an individual embed card to the correct category channel.
    Uses file-based dedup to avoid re-posting across ephemeral CI runs.
    Returns the number of jobs posted.
    """
    import asyncio
    import aiohttp

    # Load persistent dedup hashes from git-tracked file
    posted_hashes = load_posted_hashes()
    log(f"Loaded {len(posted_hashes)} previously-posted hashes from dedup file.")

    conn = get_connection()
    try:
        jobs = get_unposted_jobs(conn)
        if not jobs:
            log("No unposted jobs — nothing to push.")
            return 0

        # Filter out jobs we already posted in previous runs
        fresh_jobs = [j for j in jobs if not is_already_posted(posted_hashes, j["internal_hash"])]
        skipped = len(jobs) - len(fresh_jobs)
        if skipped > 0:
            log(f"Skipped {skipped} already-posted jobs (dedup file).")
        
        if not fresh_jobs:
            log("All jobs already posted in previous runs — nothing new.")
            return 0

        log(f"Pushing {len(fresh_jobs)} new jobs to Discord as individual cards...")
        sent_hashes = []

        # Group jobs by target channel for efficient sending
        channel_jobs: dict[str, list[dict]] = defaultdict(list)
        for job in fresh_jobs:
            category = _get_category(job)
            channel_id = _get_channel_id(category)

            if BOT_TOKEN and channel_id:
                channel_jobs[channel_id].append(job)
            elif WEBHOOK_URL:
                channel_jobs["__webhook__"].append(job)
            else:
                log("No Discord credentials configured — skipping.", "WARN")
                return 0

        sent_count = 0
        failed_count = 0

        async with aiohttp.ClientSession() as session:
            for channel_id, ch_jobs in channel_jobs.items():
                for job in ch_jobs:
                    embed = _build_job_embed(job)
                    try:
                        if channel_id == "__webhook__":
                            ok = await _send_card_via_webhook(session, embed)
                        else:
                            ok = await _send_card_via_bot(session, channel_id, embed)

                        if ok:
                            sent_count += 1
                            mark_as_posted(posted_hashes, job["internal_hash"])
                            sent_hashes.append(job["internal_hash"])
                        else:
                            failed_count += 1
                    except Exception as e:
                        log(f"Failed to send card: {e}", "WARN")
                        failed_count += 1

                    # Respect Discord rate limits: ~1 msg/sec
                    await asyncio.sleep(1.0)

        log(f"Sent {sent_count} cards ({failed_count} failed)")

        # Mark only successfully-sent jobs as posted in the DB
        if sent_hashes:
            mark_jobs_posted(conn, sent_hashes)
            log(f"Marked {len(sent_hashes)}/{len(fresh_jobs)} jobs as posted in DB.")
        
        # Persist dedup hashes to disk for cross-run dedup
        save_posted_hashes(posted_hashes)
        log(f"Saved {len(posted_hashes)} hashes to dedup file.")
        
        return sent_count

    except Exception as e:
        log(f"Discord push failed: {e}", "ERROR")
        return 0
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# STREAMING WATERFALL — push jobs as they're discovered (real-time)
# ═══════════════════════════════════════════════════════════════════════

import asyncio as _asyncio


class StreamingJobPusher:
    """
    Real-time Discord job pusher — posts individual cards as jobs are discovered.

    Each job gets its own embed card. If BOT_TOKEN is set, cards are routed
    to the appropriate category channel. Otherwise, falls back to webhook.
    """

    RATE_LIMIT_DELAY = 1.0  # Seconds between webhook calls

    def __init__(self, webhook_url: str = None):
        self._webhook_url = webhook_url or WEBHOOK_URL
        self._queue: _asyncio.Queue = _asyncio.Queue()
        self._stop = _asyncio.Event()
        self._total_pushed = 0
        self._enabled = bool(self._webhook_url or BOT_TOKEN)
        # Load persistent dedup hashes
        self._posted_hashes = load_posted_hashes() if self._enabled else {}

    @property
    def total_pushed(self) -> int:
        return self._total_pushed

    def push(self, job_dict: dict) -> None:
        """Queue a job for streaming push. Non-blocking. Skips already-posted jobs."""
        if self._enabled:
            h = job_dict.get("internal_hash", "")
            if h and is_already_posted(self._posted_hashes, h):
                return  # Already posted in a previous run
            self._queue.put_nowait(job_dict)

    async def stop(self) -> None:
        """Signal the consumer to flush remaining jobs and exit."""
        self._stop.set()

    async def run(self) -> None:
        """Background consumer: posts each job as a card in real-time."""
        if not self._enabled:
            log("StreamingJobPusher disabled — no Discord credentials configured.")
            return

        import aiohttp
        log("🌊 Streaming waterfall started — jobs will hit Discord in real-time.")

        async with aiohttp.ClientSession() as session:
            while True:
                # Wait for a job or stop signal
                try:
                    job = await _asyncio.wait_for(self._queue.get(), timeout=10.0)
                except _asyncio.TimeoutError:
                    if self._stop.is_set() and self._queue.empty():
                        break
                    continue

                try:
                    category = _get_category(job)
                    channel_id = _get_channel_id(category)
                    embed = _build_job_embed(job)

                    if BOT_TOKEN and channel_id:
                        ok = await _send_card_via_bot(session, channel_id, embed)
                    elif self._webhook_url:
                        ok = await _send_card_via_webhook(session, embed)
                    else:
                        ok = False

                    if ok:
                        self._total_pushed += 1
                        mark_as_posted(self._posted_hashes, job.get("internal_hash", ""))
                except Exception as e:
                    log(f"Streaming push failed: {e}", "WARN")

                await _asyncio.sleep(self.RATE_LIMIT_DELAY)

                if self._stop.is_set() and self._queue.empty():
                    break

        if self._total_pushed > 0:
            log(f"🌊 Streaming waterfall complete — {self._total_pushed} cards pushed live.")
            # Save dedup hashes after streaming
            save_posted_hashes(self._posted_hashes)
            log(f"Saved {len(self._posted_hashes)} hashes to dedup file.")


if __name__ == "__main__":
    """Test: push any unposted jobs right now."""
    import asyncio
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    count = asyncio.run(push_new_jobs_to_discord())
    print(f"Pushed {count} job cards to Discord.")
