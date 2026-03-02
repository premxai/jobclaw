"""
Discord Webhook Poster — sends job digests INSTANTLY after scraping.

Unlike the bot daemon (which polls every 15 min), this module is called
directly by the scraper orchestrator the moment it finishes. Zero delay.

Uses Discord Webhook (simple HTTP POST) — no bot process needed.
Falls back to bot token + channel ID if no webhook URL is set.

Setup:
  1. In Discord: Server Settings → Integrations → Webhooks → New Webhook
  2. Copy the webhook URL
  3. Add to .env: DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
  
  OR: Uses existing DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID as fallback.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.logger import _log
from scripts.database.db_utils import get_connection, get_unposted_jobs, mark_jobs_posted

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")


def log(msg: str, level: str = "INFO"):
    _log(msg, level, "discord_push")


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


def _job_line(job: dict) -> str:
    """One-liner for a job in the digest."""
    title = job.get("title", "Unknown Role")
    company = job.get("company", "Unknown")
    location = job.get("location", "")
    url = job.get("url", "")

    loc = location.split(",")[0].strip() if location else ""
    if loc and len(loc) > 25:
        loc = loc[:22] + "..."

    line = f"• **{title}** @ {company}"
    if loc:
        line += f" — {loc}"
    if url:
        line += f" — [Apply]({url})"
    return line


def _group_by_category(jobs: list[dict]) -> dict[str, list[dict]]:
    groups = defaultdict(list)
    for job in jobs:
        cats = job.get("keywords_matched", [])
        category = cats[0] if cats else "Uncategorized"
        groups[category].append(job)
    return dict(groups)


def _build_embeds(jobs: list[dict]) -> list[dict]:
    """Build Discord embed objects for a job digest."""
    by_category = _group_by_category(jobs)
    sorted_cats = sorted(by_category.items(), key=lambda x: len(x[1]), reverse=True)

    embeds = []
    for category, cat_jobs in sorted_cats:
        emoji = CATEGORY_EMOJIS.get(category, "💼")
        lines = [_job_line(j) for j in cat_jobs]

        # Chunk to 4000 chars per embed (Discord limit is 4096)
        pages = []
        current = []
        current_len = 0
        for line in lines:
            line_len = len(line) + 1
            if current and current_len + line_len > 3800:
                pages.append("\n".join(current))
                current = [line]
                current_len = line_len
            else:
                current.append(line)
                current_len += line_len
        if current:
            pages.append("\n".join(current))

        for i, page_text in enumerate(pages):
            embed = {
                "description": page_text,
                "color": 0x57F287,  # Discord brand green
            }
            if i == 0:
                embed["author"] = {"name": f"{emoji} {category} — {len(cat_jobs)} roles"}
            else:
                embed["author"] = {"name": f"{emoji} {category} (cont.)"}
            embeds.append(embed)

    return embeds


async def _send_via_webhook(webhook_url: str, jobs: list[dict]):
    """Send digest via Discord webhook (simple HTTP POST, no bot needed)."""
    import aiohttp

    ts = datetime.now().strftime("%b %d, %I:%M %p")
    by_category = _group_by_category(jobs)

    header_content = (
        f"🚀 **JobClaw Digest — {ts}**\n"
        f"📡 **{len(jobs)}** new roles across **{len(by_category)}** categories • 🇺🇸 US Only\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    embeds = _build_embeds(jobs)

    # Discord webhooks allow max 10 embeds per message
    async with aiohttp.ClientSession() as session:
        # Send header
        await session.post(webhook_url, json={"content": header_content})

        # Send embeds in batches of 10
        for i in range(0, len(embeds), 10):
            batch = embeds[i:i + 10]
            payload = {"embeds": batch}
            resp = await session.post(webhook_url, json=payload)
            if resp.status != 204:
                log(f"Webhook returned {resp.status}: {await resp.text()}", "WARN")

        # Footer
        await session.post(webhook_url, json={
            "content": f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n✅ **Digest complete — {len(jobs)} roles posted.**"
        })


async def _send_via_bot_api(bot_token: str, channel_id: str, jobs: list[dict]):
    """Send digest via Discord Bot API (REST, no running bot process needed)."""
    import aiohttp

    ts = datetime.now().strftime("%b %d, %I:%M %p")
    by_category = _group_by_category(jobs)
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }

    header_content = (
        f"🚀 **JobClaw Digest — {ts}**\n"
        f"📡 **{len(jobs)}** new roles across **{len(by_category)}** categories • 🇺🇸 US Only\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    embeds = _build_embeds(jobs)

    async with aiohttp.ClientSession() as session:
        # Header message
        await session.post(url, headers=headers, json={"content": header_content})

        # Embeds in batches of 10
        for i in range(0, len(embeds), 10):
            batch = embeds[i:i + 10]
            resp = await session.post(url, headers=headers, json={"embeds": batch})
            if resp.status not in (200, 201):
                log(f"Bot API returned {resp.status}: {await resp.text()}", "WARN")

        # Footer
        await session.post(url, headers=headers, json={
            "content": f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n✅ **Digest complete — {len(jobs)} roles posted.**"
        })


async def push_new_jobs_to_discord():
    """
    Called by the orchestrator IMMEDIATELY after scraping finishes.
    Checks DB for unposted jobs → sends them to Discord → marks as posted.
    Returns the number of jobs posted.
    """
    conn = get_connection()
    try:
        jobs = get_unposted_jobs(conn)
        if not jobs:
            log("No unposted jobs — nothing to push.")
            return 0

        log(f"Pushing {len(jobs)} new jobs to Discord...")

        hashes = [j["internal_hash"] for j in jobs]

        # Prefer webhook (simpler, no bot process), fall back to bot API
        if WEBHOOK_URL:
            await _send_via_webhook(WEBHOOK_URL, jobs)
            log(f"Sent {len(jobs)} jobs via webhook.")
        elif BOT_TOKEN and CHANNEL_ID:
            await _send_via_bot_api(BOT_TOKEN, CHANNEL_ID, jobs)
            log(f"Sent {len(jobs)} jobs via Bot API.")
        else:
            log("No DISCORD_WEBHOOK_URL or BOT_TOKEN configured — skipping push.", "WARN")
            return 0

        # Mark as posted
        mark_jobs_posted(conn, hashes)
        log(f"Marked {len(hashes)} jobs as posted.")
        return len(jobs)

    except Exception as e:
        log(f"Discord push failed: {e}", "ERROR")
        return 0
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# STREAMING WATERFALL — push jobs to Discord AS they're discovered
# ═══════════════════════════════════════════════════════════════════════

import asyncio as _asyncio


class StreamingJobPusher:
    """
    Real-time Discord job pusher that runs alongside scrapers.

    Workers push qualifying jobs into a queue. A background consumer task
    drains the queue in micro-batches (every BATCH_SIZE jobs or FLUSH_INTERVAL
    seconds, whichever comes first) and sends them to Discord via webhook.

    Usage:
        pusher = StreamingJobPusher()
        task = asyncio.create_task(pusher.run())
        ...workers push jobs via pusher.push(job_dict)...
        await pusher.stop()
        await task
    """

    BATCH_SIZE = 5          # Max jobs per micro-batch
    FLUSH_INTERVAL = 10.0   # Seconds between flushes (even if < BATCH_SIZE)
    RATE_LIMIT_DELAY = 1.0  # Seconds between webhook calls (Discord rate limit)

    def __init__(self, webhook_url: str = None):
        self._url = webhook_url or WEBHOOK_URL
        self._queue: _asyncio.Queue = _asyncio.Queue()
        self._stop = _asyncio.Event()
        self._total_pushed = 0
        self._enabled = bool(self._url)

    @property
    def total_pushed(self) -> int:
        return self._total_pushed

    def push(self, job_dict: dict) -> None:
        """Queue a job for streaming push. Non-blocking, safe from any coroutine."""
        if self._enabled:
            self._queue.put_nowait(job_dict)

    async def stop(self) -> None:
        """Signal the consumer to flush remaining jobs and exit."""
        self._stop.set()

    async def run(self) -> None:
        """
        Background consumer: drains queue in micro-batches and sends to Discord.
        Runs until stop() is called and queue is empty.
        """
        if not self._enabled:
            log("StreamingJobPusher disabled — no DISCORD_WEBHOOK_URL configured.")
            return

        import aiohttp
        log("🌊 Streaming waterfall started — jobs will hit Discord in real-time.")

        async with aiohttp.ClientSession() as session:
            while True:
                batch = await self._collect_batch()

                if batch:
                    await self._send_batch(session, batch)
                    self._total_pushed += len(batch)

                if self._stop.is_set() and self._queue.empty():
                    break

        if self._total_pushed > 0:
            log(f"🌊 Streaming waterfall complete — {self._total_pushed} jobs pushed live.")

    async def _collect_batch(self) -> list[dict]:
        """Collect up to BATCH_SIZE jobs, waiting up to FLUSH_INTERVAL."""
        batch = []
        try:
            # Wait for the first item (or until stop is signaled)
            try:
                first = await _asyncio.wait_for(
                    self._queue.get(),
                    timeout=self.FLUSH_INTERVAL,
                )
                batch.append(first)
            except _asyncio.TimeoutError:
                return batch

            # Greedily grab more items without waiting
            while len(batch) < self.BATCH_SIZE:
                try:
                    item = self._queue.get_nowait()
                    batch.append(item)
                except _asyncio.QueueEmpty:
                    break
        except Exception:
            pass

        return batch

    async def _send_batch(self, session, batch: list[dict]) -> None:
        """Send a micro-batch to Discord via webhook."""
        try:
            lines = [_job_line(j) for j in batch]
            text = "\n".join(lines)

            payload = {
                "embeds": [{
                    "description": text,
                    "color": 0x57F287,
                    "footer": {"text": f"⚡ {len(batch)} new • Streaming live"},
                }]
            }
            resp = await session.post(self._url, json=payload)
            if resp.status == 429:
                # Rate limited — wait and retry
                retry_after = 2.0
                try:
                    data = await resp.json()
                    retry_after = data.get("retry_after", 2.0)
                except Exception:
                    pass
                log(f"Discord rate limited — waiting {retry_after}s", "WARN")
                await _asyncio.sleep(retry_after)
                # Retry once
                await session.post(self._url, json=payload)
            elif resp.status not in (200, 204):
                log(f"Webhook returned {resp.status}", "WARN")

            # Respect Discord rate limits
            await _asyncio.sleep(self.RATE_LIMIT_DELAY)

        except Exception as e:
            log(f"Streaming push failed: {e}", "WARN")


if __name__ == "__main__":
    """Test: push any unposted jobs right now."""
    import asyncio
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    count = asyncio.run(push_new_jobs_to_discord())
    print(f"Pushed {count} jobs to Discord.")

