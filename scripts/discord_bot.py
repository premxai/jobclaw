"""
Discord Job Bot for AI Job Agent.

Runs a Discord bot that:
  1. Scrapes Google Careers via OpenClaw every 10 minutes
  2. Detects new jobs (not previously posted)
  3. Posts formatted job listings to a Discord channel
  4. Tracks posted jobs to avoid duplicates

Usage:
    python scripts/discord_bot.py
"""

import asyncio
import json
import os
import subprocess
import sys
import re
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import tasks
from dotenv import load_dotenv

# ── Project paths ─────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
POSTED_JOBS_FILE = DATA_DIR / "posted_jobs.json"
RAW_JOBS_FILE = DATA_DIR / "google_jobs_raw.json"

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


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════

def log(msg: str, level: str = "INFO") -> None:
    """Log to console and logs/system.log."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"{ts} | {level} | [discord_bot] {msg}"
    print(entry)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOGS_DIR / "system.log", "a", encoding="utf-8") as f:
        f.write(entry + "\n")


def load_posted_jobs() -> set[str]:
    """Load set of previously posted job URLs."""
    if not POSTED_JOBS_FILE.exists():
        return set()
    try:
        data = json.loads(POSTED_JOBS_FILE.read_text(encoding="utf-8"))
        return set(data.get("posted_urls", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_posted_jobs(urls: set[str]) -> None:
    """Save the set of posted job URLs."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "posted_urls": list(urls),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_posted": len(urls),
    }
    POSTED_JOBS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def scrape_jobs_via_openclaw() -> list[dict]:
    """Run OpenClaw agent to scrape Google Careers and return job list."""
    log("Running OpenClaw agent to scrape Google Careers...")

    try:
        prompt = (
            "Search Google Careers at https://careers.google.com/jobs/results/?q=software+engineer "
            "and find jobs posted within the LAST 24 HOURS only. "
            "Return up to 15 job listings as a JSON array. Each object must have fields: "
            "title, location, url, date_posted (the date/time the job was posted, "
            "e.g. 2026-02-20 or 3 hours ago or today). "
            "Return ONLY the raw JSON array, no markdown fences, no explanation."
        )
        result = subprocess.run(
            ["openclaw.cmd", "agent", "--agent", "main", "--local", "--message", prompt],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(PROJECT_ROOT),
        )

        # OpenClaw may write to stdout OR stderr — check both
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        output = stdout if stdout else stderr
        if not output:
            output = stdout + "\n" + stderr  # Merge both

        log(f"Agent stdout: {len(stdout)} chars, stderr: {len(stderr)} chars")

        # Try to extract JSON array from output
        # Remove markdown code fences if present
        cleaned = re.sub(r'```json\s*', '', output)
        cleaned = re.sub(r'```\s*', '', cleaned)
        cleaned = cleaned.strip()

        # Find the JSON array in the output
        start = cleaned.find('[')
        end = cleaned.rfind(']')
        if start != -1 and end != -1:
            json_str = cleaned[start:end + 1]
            jobs = json.loads(json_str)
            if isinstance(jobs, list):
                log(f"Parsed {len(jobs)} job listings")
                return jobs

        # Log what we got so we can debug
        log(f"Could not parse JSON. Raw output (first 500 chars): {output[:500]}", "WARN")
        return []

    except subprocess.TimeoutExpired:
        log("OpenClaw agent timed out after 120s", "ERROR")
        return []
    except Exception as e:
        log(f"Scraping failed: {e}", "ERROR")
        return []


def build_embed(job: dict, index: int, total: int) -> discord.Embed:
    """Create a rich Discord embed for a job listing."""
    date_posted = job.get("date_posted", "Unknown")
    embed = discord.Embed(
        title=f"💼 {job.get('title', 'Unknown Position')}",
        url=job.get("url", ""),
        description=f"🕐 **Posted:** {date_posted}",
        color=0x4285F4,  # Google blue
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="📍 Location", value=job.get("location", "Not specified"), inline=True)
    embed.add_field(name="🏢 Company", value="Google", inline=True)
    embed.set_footer(text=f"JobClaw Agent • Listing {index}/{total} • Last 24hrs only")
    return embed


# ═══════════════════════════════════════════════════════════════════════
# SCHEDULED TASK — runs every 10 minutes
# ═══════════════════════════════════════════════════════════════════════

@tasks.loop(minutes=10)
async def scrape_and_post():
    """Scrape Google Careers and post new jobs to Discord."""
    log("========== SCHEDULED SCRAPE START ==========")

    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        log(f"Channel {CHANNEL_ID} not found!", "ERROR")
        return

    # Run scraping in a thread to not block the event loop
    jobs = await asyncio.get_event_loop().run_in_executor(None, scrape_jobs_via_openclaw)

    if not jobs:
        log("No jobs returned from scrape.")
        return

    # Check for new jobs
    posted = load_posted_jobs()
    new_jobs = [j for j in jobs if j.get("url") not in posted]

    if not new_jobs:
        log("No new jobs to post — all already posted.")
        await channel.send("🔄 **Job scan complete** — no new listings found this cycle.")
        return

    # Post new jobs
    log(f"Posting {len(new_jobs)} new job(s) to Discord...")

    # Header message
    scan_time = datetime.now().strftime("%I:%M %p")
    await channel.send(
        f"🚀 **{len(new_jobs)} New Google Job Listing{'s' if len(new_jobs) != 1 else ''} Found!** (scanned at {scan_time})\n"
        f"📅 Showing jobs posted in the **last 24 hours** only\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    for i, job in enumerate(new_jobs, 1):
        embed = build_embed(job, i, len(new_jobs))
        await channel.send(embed=embed)
        posted.add(job.get("url", ""))
        await asyncio.sleep(1)  # Rate limit safety

    # Save updated posted set
    save_posted_jobs(posted)
    log(f"Posted {len(new_jobs)} new jobs. Total tracked: {len(posted)}")
    log("========== SCHEDULED SCRAPE COMPLETE ==========")


@scrape_and_post.before_loop
async def before_scrape():
    """Wait until the bot is ready before starting the loop."""
    await client.wait_until_ready()


# ═══════════════════════════════════════════════════════════════════════
# BOT EVENTS
# ═══════════════════════════════════════════════════════════════════════

@client.event
async def on_ready():
    log(f"Bot connected as {client.user} (ID: {client.user.id})")
    log(f"Target channel: {CHANNEL_ID}")

    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(
            "🦞 **JobClaw Bot is online!**\n"
            "I'll scan Google Careers every **10 minutes** and post new listings here.\n"
            "Use `!scan` to trigger an immediate scan."
        )
        # Run first scan immediately
        scrape_and_post.start()
    else:
        log(f"Could not find channel {CHANNEL_ID}!", "ERROR")


@client.event
async def on_message(message: discord.Message):
    # Ignore own messages
    if message.author == client.user:
        return

    # Manual scan trigger
    if message.content.strip().lower() == "!scan":
        await message.channel.send("🔍 **Starting manual job scan...**")
        jobs = await asyncio.get_event_loop().run_in_executor(None, scrape_jobs_via_openclaw)

        if not jobs:
            await message.channel.send("❌ No jobs returned. Check logs for errors.")
            return

        posted = load_posted_jobs()
        new_jobs = [j for j in jobs if j.get("url") not in posted]

        if not new_jobs:
            await message.channel.send("✅ No new listings — all previously posted.")
            return

        scan_time = datetime.now().strftime("%I:%M %p")
        await message.channel.send(
            f"🚀 **{len(new_jobs)} New Listing{'s' if len(new_jobs) != 1 else ''} Found!** (scanned at {scan_time})\n"
            f"📅 Last 24 hours only\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        for i, job in enumerate(new_jobs, 1):
            embed = build_embed(job, i, len(new_jobs))
            await message.channel.send(embed=embed)
            posted.add(job.get("url", ""))
            await asyncio.sleep(1)

        save_posted_jobs(posted)

    # Status command
    elif message.content.strip().lower() == "!status":
        posted = load_posted_jobs()
        await message.channel.send(
            f"📊 **JobClaw Status**\n"
            f"• Jobs tracked: **{len(posted)}**\n"
            f"• Scan interval: **10 minutes**\n"
            f"• Next scan: auto-scheduled\n"
            f"• Commands: `!scan` (manual scan), `!status` (this)"
        )


# ═══════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log("Starting JobClaw Discord bot...")
    client.run(BOT_TOKEN)
