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
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.database.db_utils import get_connection, get_unposted_jobs, mark_jobs_posted, get_hot_slugs
from scripts.utils.dedup_file import is_already_posted, load_posted_hashes, mark_as_posted, save_posted_hashes
from scripts.utils.logger import _log

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

# Per-category Discord webhook URLs — one webhook per channel.
# Set these secrets in GitHub repo settings → Secrets → Actions.
_CATEGORY_WEBHOOKS = {
    "AI/ML":           os.getenv("DISCORD_WEBHOOK_AI", ""),
    "Data Science":    os.getenv("DISCORD_WEBHOOK_DATA", ""),
    "Data Engineering":os.getenv("DISCORD_WEBHOOK_DATA", ""),
    "Data Analyst":    os.getenv("DISCORD_WEBHOOK_DATA", ""),
    "SWE":             os.getenv("DISCORD_WEBHOOK_SWE", ""),
    "New Grad":        os.getenv("DISCORD_WEBHOOK_NEWGRAD", ""),
    "Product":         os.getenv("DISCORD_WEBHOOK_PRODUCT", ""),
    "Research":        os.getenv("DISCORD_WEBHOOK_RESEARCH", ""),
}

# First configured webhook used as fallback for uncategorized jobs
_FALLBACK_WEBHOOK = next((v for v in _CATEGORY_WEBHOOKS.values() if v), "")

_missing_webhooks = [k for k, v in _CATEGORY_WEBHOOKS.items() if not v]
if len(_missing_webhooks) == len(_CATEGORY_WEBHOOKS):
    log("No DISCORD_WEBHOOK_* env vars set — Discord push will be skipped.", "WARN")

CATEGORY_EMOJIS = {
    "AI/ML": "🤖",
    "Data Science": "🔬",
    "Data Engineering": "🔧",
    "Data Analyst": "📊",
    "SWE": "💻",
    "New Grad": "🎓",
    "Product": "📦",
    "Research": "🧪",
    "Uncategorized": "💼",
}

CATEGORY_COLORS = {
    "AI/ML": 0x9B59B6,  # Purple
    "Data Science": 0x3498DB,  # Blue
    "Data Engineering": 0x1ABC9C,  # Teal
    "Data Analyst": 0x2ECC71,  # Green
    "SWE": 0xE67E22,  # Orange
    "New Grad": 0xF1C40F,  # Yellow
    "Product": 0xE74C3C,  # Red
    "Research": 0x95A5A6,  # Gray
    "Uncategorized": 0x546E7A,  # Dark gray
}

ATS_LABELS = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "workday": "Workday",
    "ashby": "Ashby",
    "smartrecruiters": "SmartRecruiters",
    "rippling": "Rippling",
    "workable": "Workable",
    "icims": "iCIMS",
    "github-swe-newgrad": "GitHub",
    "github-ai-newgrad": "GitHub",
    "github-internship": "GitHub",
    "github-new-grad": "GitHub",
    "remoteok": "RemoteOK",
    "remotive": "Remotive",
    "wwr": "WWR",
    "dice": "Dice",
    "wellfound": "Wellfound",
    "ycombinator": "Y Combinator",
    "linkedin": "LinkedIn",
    "indeed": "Indeed",
    "glassdoor": "Glassdoor",
}


def _is_fresh(job: dict, cutoff: datetime) -> bool:
    """Return True if the job is newer than cutoff. Falls back to first_seen if date_posted is unparseable."""
    import dateutil.parser

    # Try date_posted first
    raw = job.get("date_posted", "")
    if raw:
        try:
            dt = dateutil.parser.parse(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt >= cutoff
        except Exception:
            pass
    # Fall back to first_seen
    raw = job.get("first_seen", "")
    if raw:
        try:
            dt = dateutil.parser.parse(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt >= cutoff
        except Exception:
            pass
    return True  # Unknown age: include (over-inclusive is safer)


def _urgency_color(date_posted: str, base_color: int) -> int:
    """Override embed color based on how fresh the job is.

    Green  = posted < 2 hours ago (hot/fresh)
    Yellow = posted < 12 hours ago (recent)
    default = category color (older)
    """
    try:
        posted = datetime.fromisoformat(date_posted.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - posted
        if age < timedelta(hours=2):
            return 0x2ECC71  # Bright green — hot/fresh
        if age < timedelta(hours=12):
            return 0xF1C40F  # Yellow — recent
    except (ValueError, TypeError, AttributeError):
        pass
    return base_color


def _quality_score(job: dict) -> float:
    """Return the quality score from the DB, or a basic calculation if missing."""
    return float(job.get("quality_score", 0))


def _get_category(job: dict) -> str:
    """Get the primary category for a job."""
    cats = job.get("keywords_matched", [])
    if isinstance(cats, str):
        try:
            cats = json.loads(cats)
        except (json.JSONDecodeError, TypeError):
            cats = []
    return cats[0] if cats else "Uncategorized"


def _get_webhook_url(category: str) -> str:
    """Resolve a category to its Discord webhook URL. Falls back to first configured webhook."""
    return _CATEGORY_WEBHOOKS.get(category, "") or _FALLBACK_WEBHOOK


def _format_date(date_str: str | None) -> str:
    """Format a date string for display."""
    if not date_str:
        return "Unknown"
    try:
        d = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return d.strftime("%b %d, %Y")
    except (ValueError, TypeError):
        return date_str[:10] if len(date_str) >= 10 else date_str


def _urgency_prefix(job: dict) -> str:
    """Return an urgency prefix string based on job age.

    < 2 hours  → "⚡ "
    2–12 hours → "🟡 "
    12–48 hours → "" (no prefix)
    """
    import dateutil.parser

    raw = job.get("date_posted", "") or job.get("first_seen", "")
    if raw:
        try:
            dt = dateutil.parser.parse(str(raw))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - dt
            if age < timedelta(hours=2):
                return "⚡ "
            if age < timedelta(hours=12):
                return "🟡 "
        except Exception:
            pass
    return ""


def _build_job_embed(job: dict) -> dict:
    """Build a single Discord embed card for one job."""
    title = job.get("title", "Unknown Role")
    company = job.get("company", "Unknown")
    location = job.get("location", "Remote")
    url = job.get("url", "")
    date_posted = job.get("date_posted") or job.get("first_seen", "")
    source_ats = job.get("source_ats", "")
    hot_slugs = get_hot_slugs()
    is_hot = source_ats.lower() in hot_slugs or company.lower().strip() in hot_slugs

    # Categorization (Phase 3 matching)
    category = _get_category(job)

    emoji = CATEGORY_EMOJIS.get(category, "💼")
    if is_hot:
        emoji = "🔥"

    base_color = CATEGORY_COLORS.get(category, 0x546E7A)
    # Brighten color for hot companies
    if is_hot:
        base_color = 0xF1C40F  # Gold/Yellow

    # Override color based on posting age (green = fresh, yellow = recent)
    color = _urgency_color(date_posted, base_color)
    ats_label = ATS_LABELS.get(source_ats.lower(), source_ats) if source_ats else "Direct"

    # Truncate location if too long
    if location and len(location) > 40:
        location = location[:37] + "..."

    urgency = _urgency_prefix(job)

    embed = {
        "title": f"{urgency}{emoji} {title}",
        "color": color,
        "fields": [
            {"name": "🏢 Company", "value": f"**{company}** {' ✅' if is_hot else ''}", "inline": True},
            {"name": "📍 Location", "value": location or "Remote", "inline": True},
            {"name": "📅 Posted", "value": _format_date(date_posted), "inline": True},
            {"name": "🔗 Source", "value": ats_label, "inline": True},
            {"name": "🏷️ Category", "value": category, "inline": True},
        ],
        "footer": {"text": f"JobClaw • {ats_label} • {datetime.now(timezone.utc).strftime('%H:%M UTC')}"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if url:
        embed["url"] = url
        embed["fields"].append({"name": "📎 Apply", "value": f"[Click here to apply]({url})", "inline": False})

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

    # Experience requirement if available (extracted during ATS ingestion)
    experience_years = job.get("experience_years")
    if experience_years is not None:
        embed["fields"].append({"name": "🎯 Experience", "value": f"{experience_years}+ yrs", "inline": True})

    # All matched categories (if more than one)
    all_cats = job.get("keywords_matched") or []
    if isinstance(all_cats, str):
        try:
            all_cats = json.loads(all_cats)
        except (json.JSONDecodeError, TypeError):
            all_cats = [all_cats] if all_cats else []
    if len(all_cats) > 1:
        embed["fields"].append({"name": "🏷️ Tags", "value": " · ".join(all_cats), "inline": False})

    # Remote/hybrid/onsite indicator prepended to title
    remote_ok = job.get("remote_ok")
    if remote_ok == "remote":
        embed["title"] = f"🌐 {embed['title']}"
    elif remote_ok == "hybrid":
        embed["title"] = f"🏠 {embed['title']}"

    # Seniority badge
    seniority = job.get("seniority_level")
    _SENIORITY_DISPLAY = {
        "intern": "Internship",
        "entry": "Entry Level",
        "mid": "Mid Level",
        "senior": "Senior",
        "staff": "Staff",
        "principal": "Principal",
        "director": "Director",
    }
    if seniority and seniority in _SENIORITY_DISPLAY:
        embed["fields"].append({"name": "📊 Level", "value": _SENIORITY_DISPLAY[seniority], "inline": True})

    # Visa sponsorship signal
    visa = job.get("visa_sponsorship")
    if visa == 1:
        embed["fields"].append({"name": "✈️ Visa", "value": "Sponsors H1B", "inline": True})
    elif visa == 0:
        embed["fields"].append({"name": "✈️ Visa", "value": "No sponsorship", "inline": True})

    # Top 5 tech stack tags
    stack = job.get("tech_stack")
    if stack:
        if isinstance(stack, str):
            try:
                stack = json.loads(stack)
            except (json.JSONDecodeError, TypeError):
                stack = []
        if stack:
            embed["fields"].append({"name": "🛠️ Stack", "value": " · ".join(stack[:5]), "inline": False})

    # Description snippet (first 200 chars gives context before clicking Apply)
    desc = (job.get("description") or "").strip()
    if desc:
        snippet = desc[:200] + ("…" if len(desc) > 200 else "")
        embed["description"] = snippet

    return embed


# ═══════════════════════════════════════════════════════════════════════
# SENDING — Bot API (multi-channel) or Webhook (single-channel)
# ═══════════════════════════════════════════════════════════════════════

# Shared headers — User-Agent is required or Cloudflare returns 1010
_DISCORD_HEADERS = {
    "User-Agent": "JobClaw/1.0 (https://github.com/premxai/jobclaw)",
    "Content-Type": "application/json",
}


async def _post_to_webhook(session, webhook_url: str, embed: dict) -> bool:
    """POST a single embed to a Discord webhook with 3-retry exponential backoff."""
    import asyncio

    for attempt in range(3):
        resp = await session.post(webhook_url, headers=_DISCORD_HEADERS, json={"embeds": [embed]})

        if resp.status in (200, 204):
            return True

        if resp.status == 429:
            try:
                data = await resp.json()
                wait = data.get("retry_after", 2.0)
            except Exception:
                wait = 2.0
            backoff = max(wait, 2.0) * (2**attempt)
            log(f"Rate limited — waiting {backoff:.1f}s (attempt {attempt + 1}/3)", "WARN")
            await asyncio.sleep(backoff)
            continue

        log(f"Webhook returned HTTP {resp.status}", "WARN")
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

    from scripts.database.db_utils import purge_stale_unposted

    if not _FALLBACK_WEBHOOK:
        log("No DISCORD_WEBHOOK_* secrets configured — cannot push. Set at least one webhook.", "ERROR")
        return 0

    # Load persistent dedup hashes from git-tracked file
    posted_hashes = load_posted_hashes()
    log(f"Loaded {len(posted_hashes)} previously-posted hashes from dedup file.")

    conn = get_connection()
    try:
        # Archive jobs too old to post so they don't pile up
        purged = purge_stale_unposted(conn)
        if purged:
            log(f"Archived {purged} stale unposted jobs (>48hr).")

        # SQL already filters to last 48hr window
        jobs = get_unposted_jobs(conn)
        log(f"Found {len(jobs)} unposted jobs within 48hr window.")
        if not jobs:
            log("No unposted jobs — nothing to push.")
            return 0

        # Disk-based dedup: skip jobs already posted in a previous run
        fresh_jobs = [j for j in jobs if not is_already_posted(posted_hashes, j["internal_hash"])]
        log(f"{len(fresh_jobs)} jobs to push after dedup ({len(jobs) - len(fresh_jobs)} already posted).")

        if not fresh_jobs:
            log("All unposted jobs already posted (dedup). Nothing new.")
            return 0

        # Sort newest first
        fresh_jobs.sort(key=lambda x: str(x.get("first_seen", "")), reverse=True)

        sent_count = 0
        failed_count = 0
        sent_hashes = []

        async with aiohttp.ClientSession() as session:
            for job in fresh_jobs:
                category = _get_category(job)
                webhook_url = _get_webhook_url(category)

                if not webhook_url:
                    log(f"No webhook for category '{category}' — skipping job.", "WARN")
                    failed_count += 1
                    continue

                embed = _build_job_embed(job)
                try:
                    ok = await _post_to_webhook(session, webhook_url, embed)
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

    except Exception:
        import traceback

        log(f"Discord push failed: {traceback.format_exc()}", "ERROR")
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
        self._queue: _asyncio.Queue = _asyncio.Queue()
        self._stop = _asyncio.Event()
        self._total_pushed = 0
        self._enabled = bool(_FALLBACK_WEBHOOK or webhook_url)
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
                except TimeoutError:
                    if self._stop.is_set() and self._queue.empty():
                        break
                    continue

                try:
                    category = _get_category(job)
                    webhook_url = _get_webhook_url(category)
                    embed = _build_job_embed(job)

                    ok = await _post_to_webhook(session, webhook_url, embed) if webhook_url else False

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
