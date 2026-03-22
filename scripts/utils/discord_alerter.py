"""
Discord admin alerter — sends operational alerts to DISCORD_ADMIN_CHANNEL.
Used by scrapers and discord_push to surface errors and daily digests.
"""

import os
import logging
import aiohttp
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

ADMIN_CHANNEL_ID = os.getenv("DISCORD_ADMIN_CHANNEL")
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")


async def send_admin_alert(message: str, level: str = "info") -> bool:
    """Send a plain-text alert to the admin channel. Returns True on success."""
    if not ADMIN_CHANNEL_ID or not BOT_TOKEN:
        logger.debug("DISCORD_ADMIN_CHANNEL or DISCORD_BOT_TOKEN not set — skipping admin alert")
        return False

    emoji = {"info": "ℹ️", "warning": "⚠️", "error": "🚨", "success": "✅"}.get(level, "ℹ️")
    content = f"{emoji} **JobClaw Alert** `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}`\n{message}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://discord.com/api/v10/channels/{ADMIN_CHANNEL_ID}/messages",
                headers={"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"},
                json={"content": content[:2000]},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (200, 201):
                    return True
                logger.warning(f"Admin alert failed: HTTP {resp.status}")
                return False
    except Exception as e:
        logger.warning(f"Admin alert error: {e}")
        return False


async def send_daily_digest(stats: dict) -> bool:
    """Send a formatted daily digest embed to the admin channel."""
    if not ADMIN_CHANNEL_ID or not BOT_TOKEN:
        return False

    # Build digest text
    by_category = stats.get("by_category", {})
    category_str = " | ".join(f"{k}: {v}" for k, v in by_category.items()) or "N/A"

    scraper_status = stats.get("scrapers", {})
    scraper_str = " ".join(f"{name} {'✅' if ok else '⚠️'}" for name, ok in scraper_status.items()) or "N/A"

    lines = [
        f"📊 **JobClaw Daily Digest** — {datetime.now(timezone.utc).strftime('%B %d, %Y')}",
        f"• Companies scraped: {stats.get('companies_scraped', 0):,}",
        f"• New jobs found: {stats.get('new_jobs', 0):,}",
        f"• Posted to Discord: {stats.get('posted', 0):,}",
        f"• Filtered (stale/quality): {stats.get('filtered', 0):,}",
        f"• By category: {category_str}",
        f"• Scrapers: {scraper_str}",
    ]

    content = "\n".join(lines)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://discord.com/api/v10/channels/{ADMIN_CHANNEL_ID}/messages",
                headers={"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"},
                json={"content": content[:2000]},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                return resp.status in (200, 201)
    except Exception as e:
        logger.warning(f"Daily digest error: {e}")
        return False
