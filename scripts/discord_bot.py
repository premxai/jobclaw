import discord
from discord.ext import tasks
import os
import asyncio
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Path fixing
PROJECT_ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.logger import _log
from scripts.database.db_utils import get_connection, get_unposted_jobs, mark_jobs_posted

def log(msg: str, level: str = "INFO"):
    _log(msg, level, "discord_bot")

load_dotenv(PROJECT_ROOT / ".env")
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID_STR = os.getenv("DISCORD_CHANNEL_ID")

if not BOT_TOKEN or not CHANNEL_ID_STR:
    log("CRITICAL ERROR: Missing DISCORD_BOT_TOKEN or DISCORD_CHANNEL_ID in .env", "ERROR")
    sys.exit(1)

CHANNEL_ID = int(CHANNEL_ID_STR)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# ═══════════════════════════════════════════════════════════════════════
# UI HELPERS
# ═══════════════════════════════════════════════════════════════════════

ATS_EMOJIS = {
    "greenhouse": "🌲",
    "lever": " اه",
    "ashby": "🦄",
    "workday": "🏢",
    "bamboohr": "🐼",
    "smartrecruiters": "🎓",
    "github": "🐙",
    "ycombinator": "🟠",
    "remoteok": "🌍",
    "builtin": "🏗️",
    "wellfound": "✌️",
    "unknown": "💼",
}

def build_embed(job: dict, index: int, total: int) -> discord.Embed:
    company = job.get("company", "Unknown")
    title = job.get("title", "Unknown Role")
    url = job.get("url", "")
    ats = job.get("source_ats", "unknown")
    ats_emoji = ATS_EMOJIS.get(ats, "📌")

    embed = discord.Embed(
        title=title,
        url=url if url else None,
        color=discord.Color.brand_green(),
    )
    embed.set_author(name=company)
    embed.add_field(name="📍 Location", value=job.get("location", "Unknown"), inline=True)
    embed.add_field(name=f"{ats_emoji} Source", value=ats.capitalize(), inline=True)
    
    categories = job.get("keywords_matched", [])
    if categories:
        embed.add_field(name="🏷️ Category", value=" • ".join(categories), inline=True)

    embed.set_footer(text=f"JobClaw Broadcaster • {index}/{total}")
    return embed

async def post_jobs_to_channel(channel, unposted_jobs: list[dict]):
    if not unposted_jobs:
        return

    # Group by company
    by_company = defaultdict(list)
    for job in unposted_jobs:
        by_company[job.get("company", "Unknown")].append(job)

    # Header
    await channel.send(
        f"🚀 **{len(unposted_jobs)} New Roles Found!**\n"
        f"📡 Queried deeply from OS Scrapers • 🇺🇸 US Only\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    i = 0
    hashes_to_mark = []
    
    for company, jobs in sorted(by_company.items()):
        if len(by_company) > 1 and len(jobs) > 1:
            await channel.send(f"\n**── {company} ({len(jobs)} roles) ──**")

        for job in jobs:
            i += 1
            embed = build_embed(job, i, len(unposted_jobs))
            await channel.send(embed=embed)
            hashes_to_mark.append(job["internal_hash"])
            await asyncio.sleep(0.5)  # Rate limit safety

    await channel.send(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n✅ **Batch Broadcast Complete.**")
    
    # Safely mark them as posted in the database
    conn = get_connection()
    mark_jobs_posted(conn, hashes_to_mark)
    conn.close()
    log(f"Successfully posted {len(hashes_to_mark)} jobs.")

# ═══════════════════════════════════════════════════════════════════════
# DAEMON LOGIC
# ═══════════════════════════════════════════════════════════════════════

@tasks.loop(minutes=15)
async def broadcast_new_jobs():
    """Wakes up every 15 minutes to check DB for anything new."""
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        log(f"Channel {CHANNEL_ID} not found!", "ERROR")
        return

    log("Checking SQLite for unposted jobs...")
    conn = get_connection()
    try:
        jobs = get_unposted_jobs(conn)
        if not jobs:
            log("No unposted jobs. Going back to sleep.")
            return
            
        await post_jobs_to_channel(channel, jobs)
    except Exception as e:
        log(f"Broadcast failure: {e}", "ERROR")
    finally:
        conn.close()

@broadcast_new_jobs.before_loop
async def before_broadcast():
    await client.wait_until_ready()

# ═══════════════════════════════════════════════════════════════════════
# BOT EVENTS
# ═══════════════════════════════════════════════════════════════════════

@client.event
async def on_ready():
    log(f"Broadcaster connected as {client.user} (ID: {client.user.id})")
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(
            f"🦞 **JobClaw Discord Broadcaster v3 is online!**\n"
            f"📡 Listening to SQLite Database events...\n"
            f"⚡ Micro-scrapers are handled via OS scheduling."
        )
        broadcast_new_jobs.start()
    else:
        log(f"Could not find channel!", "ERROR")

@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    cmd = message.content.strip().lower()

    if cmd == "!status":
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM jobs")
        total_jobs = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'unposted'")
        unposted = cursor.fetchone()[0]
        conn.close()

        await message.channel.send(
            f"📊 **JobClaw Headless Status**\n"
            f"• Scraper Arch: **SQLite Micro-Services**\n"
            f"• DB Size: **{total_jobs} total jobs**\n"
            f"• Backlog: **{unposted} unposted roles**\n"
            f"• Broadcaster Interval: **15 minutes**"
        )

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    log("Starting JobClaw Discord Broadcaster...")
    client.run(BOT_TOKEN)
