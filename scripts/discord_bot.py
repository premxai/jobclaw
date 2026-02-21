"""
Discord Job Bot — ATS Ingestion Edition.

Posts new AI/ML/SWE/Data jobs every 30 minutes by querying ATS platforms
(Greenhouse, Lever, Ashby, SmartRecruiters, BambooHR) in parallel.

Usage:
    python scripts/discord_bot.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

import discord
from discord.ext import tasks
from dotenv import load_dotenv

# ── Fix imports ───────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ingestion.parallel_ingestor import run_cycle, load_registry
from scripts.ingestion.ats_adapters import NormalizedJob

# ── Project paths ─────────────────────────────────────────────────────
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"

# ── Load environment ──────────────────────────────────────────────────
load_dotenv(PROJECT_ROOT / ".env")

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))

if not BOT_TOKEN:
    print("ERROR: DISCORD_BOT_TOKEN not set in .env")
    sys.exit(1)
if not CHANNEL_ID:
    print("ERROR: DISCORD_CHANNEL_ID not set in .env")
    sys.exit(1)

# ── Bot setup ─────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# ── Category colors ───────────────────────────────────────────────────
CATEGORY_COLORS = {
    "AI/ML": 0x7C3AED,          # Purple
    "SWE": 0x2563EB,            # Blue
    "Data Science": 0x059669,    # Green
    "Data Engineering": 0x0891B2,# Teal
    "Data Analyst": 0x65A30D,    # Lime
    "New Grad": 0xF59E0B,       # Amber
    "Product": 0xEC4899,         # Pink
    "Research": 0x8B5CF6,        # Violet
}
ATS_EMOJIS = {
    "greenhouse": "🌿",
    "lever": "🔧",
    "ashby": "🟢",
    "smartrecruiters": "📋",
    "bamboohr": "🎋",
}


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════

def log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"{ts} | {level} | [discord_bot] {msg}"
    print(entry)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOGS_DIR / "system.log", "a", encoding="utf-8") as f:
        f.write(entry + "\n")


def build_embed(job: dict, index: int, total: int) -> discord.Embed:
    """Build a Discord embed for a job listing."""
    categories = job.get("keywords_matched", [])
    primary_cat = categories[0] if categories else "SWE"
    color = CATEGORY_COLORS.get(primary_cat, 0x6B7280)
    ats_emoji = ATS_EMOJIS.get(job.get("source_ats", ""), "📌")

    embed = discord.Embed(
        title=f"💼 {job.get('title', 'Unknown')}",
        url=job.get("url", ""),
        description=f"🕐 **Posted:** {job.get('date_posted', 'Unknown')}",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="🏢 Company", value=job.get("company", "Unknown"), inline=True)
    embed.add_field(name="📍 Location", value=job.get("location", "Unknown"), inline=True)
    embed.add_field(
        name=f"{ats_emoji} Source",
        value=job.get("source_ats", "unknown").capitalize(),
        inline=True,
    )
    if categories:
        embed.add_field(name="🏷️ Category", value=" • ".join(categories), inline=True)

    embed.set_footer(text=f"JobClaw • {index}/{total} • Last 24hrs")
    return embed


async def post_jobs_to_channel(channel, new_jobs: list[dict], scan_time: str) -> None:
    """Post all new jobs to Discord, grouped by company."""
    if not new_jobs:
        return

    # Group by company
    by_company = defaultdict(list)
    for job in new_jobs:
        by_company[job.get("company", "Unknown")].append(job)

    # Category breakdown
    cat_counts = defaultdict(int)
    for job in new_jobs:
        for cat in job.get("keywords_matched", ["Other"]):
            cat_counts[cat] += 1
    cat_breakdown = " • ".join(f"**{count}** {cat}" for cat, count in sorted(cat_counts.items()))

    # Header
    await channel.send(
        f"🚀 **{len(new_jobs)} New Job{'s' if len(new_jobs) != 1 else ''} Found!** (scanned at {scan_time})\n"
        f"📅 Last 24 hours • {len(by_company)} companies • {cat_breakdown}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    # Post jobs grouped by company
    i = 0
    for company, jobs in sorted(by_company.items()):
        if len(by_company) > 1 and len(jobs) > 1:
            await channel.send(f"\n**── {company} ({len(jobs)} roles) ──**")

        for job in jobs:
            i += 1
            embed = build_embed(job, i, len(new_jobs))
            await channel.send(embed=embed)
            await asyncio.sleep(0.5)  # Rate limit safety

    await channel.send(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n✅ **Scan complete.** Next scan in 30 minutes.")


# ═══════════════════════════════════════════════════════════════════════
# SCHEDULED TASK — every 30 minutes
# ═══════════════════════════════════════════════════════════════════════

@tasks.loop(minutes=30)
async def ingest_and_post():
    log("========== INGESTION CYCLE START ==========")

    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        log(f"Channel {CHANNEL_ID} not found!", "ERROR")
        return

    # Run ingestion cycle in executor (it uses asyncio internally)
    try:
        result = await run_cycle()
    except Exception as e:
        log(f"Ingestion cycle failed: {e}", "ERROR")
        await channel.send(f"❌ **Ingestion error:** {str(e)[:200]}")
        return

    new_jobs = result.get("new_jobs", [])
    scan_time = datetime.now().strftime("%I:%M %p")

    # Stats message
    stats = (
        f"📊 **Cycle Stats:** "
        f"{result['companies_succeeded']} companies queried • "
        f"{result['total_fetched']} jobs fetched • "
        f"{result['total_filtered']} matched roles • "
        f"{result['total_new']} new • "
        f"{result['duration_seconds']}s"
    )

    if not new_jobs:
        log("No new jobs this cycle.")
        await channel.send(
            f"🔄 **Scan complete** — no new listings this cycle ({scan_time})\n{stats}"
        )
        return

    log(f"Posting {len(new_jobs)} new jobs to Discord...")
    await channel.send(stats)
    await post_jobs_to_channel(channel, new_jobs, scan_time)

    if result.get("errors"):
        error_count = len(result["errors"])
        await channel.send(f"⚠️ {error_count} company fetch{'es' if error_count != 1 else ''} failed. Check logs for details.")

    log(f"Posted {len(new_jobs)} jobs. Cycle complete.")
    log("========== INGESTION CYCLE COMPLETE ==========")


@ingest_and_post.before_loop
async def before_ingest():
    await client.wait_until_ready()


# ═══════════════════════════════════════════════════════════════════════
# BOT EVENTS
# ═══════════════════════════════════════════════════════════════════════

@client.event
async def on_ready():
    log(f"Bot connected as {client.user} (ID: {client.user.id})")

    registry = load_registry()
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        ats_counts = defaultdict(int)
        for c in registry:
            ats_counts[c["ats"]] += 1
        ats_summary = " • ".join(f"{count} {ats}" for ats, count in sorted(ats_counts.items()))

        await channel.send(
            f"🦞 **JobClaw Bot v2 is online!**\n"
            f"📡 Monitoring **{len(registry)}** companies ({ats_summary})\n"
            f"🎯 Targeting: AI/ML, SWE, Data Science roles\n"
            f"⏰ Scanning every **30 minutes** (last 24hrs only)\n"
            f"Commands: `!scan` `!status` `!companies`"
        )
        ingest_and_post.start()
    else:
        log(f"Could not find channel {CHANNEL_ID}!", "ERROR")


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    cmd = message.content.strip().lower()

    if cmd == "!scan":
        await message.channel.send("🔍 **Starting manual ingestion cycle...** This may take 10-30 seconds.")
        try:
            result = await run_cycle()
            new_jobs = result.get("new_jobs", [])
            scan_time = datetime.now().strftime("%I:%M %p")

            stats = (
                f"📊 {result['companies_succeeded']} companies • "
                f"{result['total_fetched']} fetched • "
                f"{result['total_filtered']} matched • "
                f"{result['total_new']} new • "
                f"{result['duration_seconds']}s"
            )
            await message.channel.send(stats)

            if new_jobs:
                await post_jobs_to_channel(message.channel, new_jobs, scan_time)
            else:
                await message.channel.send("✅ No new listings — all previously ingested.")
        except Exception as e:
            await message.channel.send(f"❌ Error: {str(e)[:200]}")

    elif cmd == "!status":
        registry = load_registry()
        jobs_db_file = DATA_DIR / "jobs.json"
        total_jobs = 0
        if jobs_db_file.exists():
            try:
                db = json.loads(jobs_db_file.read_text(encoding="utf-8"))
                total_jobs = len(db.get("jobs", {}))
            except Exception:
                pass

        await message.channel.send(
            f"📊 **JobClaw Status**\n"
            f"• Companies monitored: **{len(registry)}**\n"
            f"• Total jobs tracked: **{total_jobs}**\n"
            f"• Scan interval: **30 minutes**\n"
            f"• Target roles: AI/ML, SWE, Data Science\n"
            f"• Commands: `!scan`, `!status`, `!companies`"
        )

    elif cmd == "!companies":
        registry = load_registry()
        by_ats = defaultdict(list)
        for c in registry:
            by_ats[c["ats"]].append(c["company"])

        msg = "🏢 **Monitored Companies**\n"
        for ats, companies in sorted(by_ats.items()):
            emoji = ATS_EMOJIS.get(ats, "📌")
            names = ", ".join(sorted(companies))
            msg += f"\n{emoji} **{ats.capitalize()}** ({len(companies)}): {names}"

        # Discord message limit is 2000 chars
        if len(msg) > 1900:
            msg = msg[:1900] + "\n... (truncated)"
        await message.channel.send(msg)


# ═══════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log("Starting JobClaw Discord bot v2 (ATS Ingestion)...")
    client.run(BOT_TOKEN)
