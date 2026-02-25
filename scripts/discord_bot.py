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

# Discord embed description limit is 4096 chars. We cap per-page to stay safe.
DIGEST_PAGE_CHAR_LIMIT = 3800


def _job_line(job: dict) -> str:
    """Format a single job as a compact one-liner for the digest."""
    title = job.get("title", "Unknown Role")
    company = job.get("company", "Unknown")
    location = job.get("location", "")
    url = job.get("url", "")

    # Shorten location for compactness
    loc = location.split(",")[0].strip() if location else ""
    if loc and len(loc) > 25:
        loc = loc[:22] + "..."

    if url:
        line = f"• **{title}** @ {company}"
    else:
        line = f"• **{title}** @ {company}"

    if loc:
        line += f" — {loc}"
    if url:
        line += f" — [Apply]({url})"
    return line


def _group_by_category(jobs: list[dict]) -> dict[str, list[dict]]:
    """Group jobs by their primary keyword category."""
    groups = defaultdict(list)
    for job in jobs:
        cats = job.get("keywords_matched", [])
        category = cats[0] if cats else "Uncategorized"
        groups[category].append(job)
    return dict(groups)


def _paginate_lines(lines: list[str], char_limit: int = DIGEST_PAGE_CHAR_LIMIT) -> list[str]:
    """Split lines into pages that fit within the char limit."""
    pages = []
    current = []
    current_len = 0
    for line in lines:
        line_len = len(line) + 1  # +1 for newline
        if current and current_len + line_len > char_limit:
            pages.append("\n".join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len
    if current:
        pages.append("\n".join(current))
    return pages


async def post_jobs_to_channel(channel, unposted_jobs: list[dict]):
    if not unposted_jobs:
        return

    hashes_to_mark = [job["internal_hash"] for job in unposted_jobs]
    by_category = _group_by_category(unposted_jobs)

    # Sort categories so the biggest groups come first
    sorted_cats = sorted(by_category.items(), key=lambda x: len(x[1]), reverse=True)

    ts = datetime.now().strftime("%b %d, %I:%M %p")
    await channel.send(
        f"🚀 **JobClaw Digest — {ts}**\n"
        f"📡 **{len(unposted_jobs)}** new roles across **{len(by_category)}** categories • 🇺🇸 US Only\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    for category, jobs in sorted_cats:
        emoji = CATEGORY_EMOJIS.get(category, "💼")
        lines = [_job_line(j) for j in jobs]
        pages = _paginate_lines(lines)

        for page_idx, page_text in enumerate(pages):
            embed = discord.Embed(
                description=page_text,
                color=discord.Color.brand_green(),
            )
            if page_idx == 0:
                header = f"{emoji} {category} — {len(jobs)} roles"
                embed.set_author(name=header)
            else:
                embed.set_author(name=f"{emoji} {category} (cont.)")

            await channel.send(embed=embed)
            await asyncio.sleep(0.3)

    await channel.send(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n✅ **Digest complete — {len(unposted_jobs)} roles posted.**")

    # Mark all as posted
    conn = get_connection()
    try:
        mark_jobs_posted(conn, hashes_to_mark)
    finally:
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
