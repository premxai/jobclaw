"""
Discord Job Bot for AI Job Agent.

Runs a Discord bot that:
  1. Scrapes Google + Microsoft Careers via OpenClaw every 10 minutes
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
# CAREER SITES CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════

CAREER_SITES = [
    {
        "name": "Google",
        "color": 0x4285F4,
        "emoji": "🔵",
        "prompt": (
            "Search Google Careers at https://careers.google.com/jobs/results/?q=software+engineer "
            "and find jobs posted within the LAST 24 HOURS only. "
            "Return up to 15 job listings as a JSON array. Each object must have: "
            "title, location, url, date_posted (when posted, e.g. '3 hours ago' or 'today'), "
            "company (always 'Google'). "
            "Return ONLY the raw JSON array, no markdown, no explanation."
        ),
    },
    {
        "name": "Microsoft",
        "color": 0x00A4EF,
        "emoji": "🟦",
        "prompt": (
            "Search Microsoft Careers at https://careers.microsoft.com/global/en/search?q=software+engineer "
            "and find jobs posted within the LAST 24 HOURS only. "
            "Return up to 15 job listings as a JSON array. Each object must have: "
            "title, location, url, date_posted (when posted, e.g. '3 hours ago' or 'today'), "
            "company (always 'Microsoft'). "
            "Return ONLY the raw JSON array, no markdown, no explanation."
        ),
    },
]

COMPANY_COLORS = {s["name"]: s["color"] for s in CAREER_SITES}
COMPANY_EMOJIS = {s["name"]: s["emoji"] for s in CAREER_SITES}


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


def load_posted_jobs() -> set[str]:
    if not POSTED_JOBS_FILE.exists():
        return set()
    try:
        data = json.loads(POSTED_JOBS_FILE.read_text(encoding="utf-8"))
        return set(data.get("posted_urls", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_posted_jobs(urls: set[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "posted_urls": list(urls),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_posted": len(urls),
    }
    POSTED_JOBS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _parse_agent_output(output: str) -> list[dict]:
    """Extract a JSON array from OpenClaw agent output."""
    cleaned = re.sub(r'```json\s*', '', output)
    cleaned = re.sub(r'```\s*', '', cleaned)
    cleaned = cleaned.strip()
    start = cleaned.find('[')
    end = cleaned.rfind(']')
    if start != -1 and end != -1:
        json_str = cleaned[start:end + 1]
        jobs = json.loads(json_str)
        if isinstance(jobs, list):
            return jobs
    return []


# ═══════════════════════════════════════════════════════════════════════
# SCRAPING
# ═══════════════════════════════════════════════════════════════════════

def scrape_site(site: dict) -> list[dict]:
    """Scrape a single career site via OpenClaw."""
    name = site["name"]
    log(f"Scraping {name} Careers...")

    try:
        result = subprocess.run(
            ["openclaw.cmd", "agent", "--agent", "main", "--local", "--message", site["prompt"]],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(PROJECT_ROOT),
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        output = stdout if stdout else stderr
        if not output:
            output = stdout + "\n" + stderr

        log(f"[{name}] stdout: {len(stdout)} chars, stderr: {len(stderr)} chars")

        jobs = _parse_agent_output(output)
        if jobs:
            for job in jobs:
                job.setdefault("company", name)
            log(f"[{name}] Found {len(jobs)} listings")
            return jobs

        log(f"[{name}] No parseable JSON. Output (first 300): {output[:300]}", "WARN")
        return []

    except subprocess.TimeoutExpired:
        log(f"[{name}] Timed out after 120s", "ERROR")
        return []
    except Exception as e:
        log(f"[{name}] Failed: {e}", "ERROR")
        return []


def scrape_all_sites() -> list[dict]:
    """Scrape all career sites sequentially and return combined list."""
    all_jobs = []
    for site in CAREER_SITES:
        jobs = scrape_site(site)
        all_jobs.extend(jobs)
    log(f"Total jobs across all sites: {len(all_jobs)}")
    return all_jobs


def build_embed(job: dict, index: int, total: int) -> discord.Embed:
    """Create a rich Discord embed for a job listing."""
    date_posted = job.get("date_posted", "Unknown")
    company = job.get("company", "Unknown")
    color = COMPANY_COLORS.get(company, 0x808080)
    emoji = COMPANY_EMOJIS.get(company, "⬜")

    embed = discord.Embed(
        title=f"💼 {job.get('title', 'Unknown Position')}",
        url=job.get("url", ""),
        description=f"🕐 **Posted:** {date_posted}",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="📍 Location", value=job.get("location", "Not specified"), inline=True)
    embed.add_field(name=f"{emoji} Company", value=company, inline=True)
    embed.set_footer(text=f"JobClaw Agent • {index}/{total} • Last 24hrs")
    return embed


# ═══════════════════════════════════════════════════════════════════════
# SCHEDULED TASK — every 10 minutes
# ═══════════════════════════════════════════════════════════════════════

@tasks.loop(minutes=10)
async def scrape_and_post():
    log("========== SCHEDULED SCRAPE START ==========")

    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        log(f"Channel {CHANNEL_ID} not found!", "ERROR")
        return

    jobs = await asyncio.get_event_loop().run_in_executor(None, scrape_all_sites)

    if not jobs:
        log("No jobs returned from any site.")
        return

    posted = load_posted_jobs()
    new_jobs = [j for j in jobs if j.get("url") not in posted]

    if not new_jobs:
        log("No new jobs — all already posted.")
        await channel.send("🔄 **Scan complete** — no new listings from Google or Microsoft this cycle.")
        return

    log(f"Posting {len(new_jobs)} new job(s) to Discord...")

    # Count per company
    companies = {}
    for j in new_jobs:
        c = j.get("company", "Unknown")
        companies[c] = companies.get(c, 0) + 1
    breakdown = " + ".join(f"**{count}** {name}" for name, count in companies.items())

    scan_time = datetime.now().strftime("%I:%M %p")
    await channel.send(
        f"🚀 **{len(new_jobs)} New Job Listing{'s' if len(new_jobs) != 1 else ''} Found!** (scanned at {scan_time})\n"
        f"📅 Last 24 hours only • {breakdown}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    for i, job in enumerate(new_jobs, 1):
        embed = build_embed(job, i, len(new_jobs))
        await channel.send(embed=embed)
        posted.add(job.get("url", ""))
        await asyncio.sleep(1)

    save_posted_jobs(posted)
    log(f"Posted {len(new_jobs)} new jobs. Total tracked: {len(posted)}")
    log("========== SCHEDULED SCRAPE COMPLETE ==========")


@scrape_and_post.before_loop
async def before_scrape():
    await client.wait_until_ready()


# ═══════════════════════════════════════════════════════════════════════
# BOT EVENTS
# ═══════════════════════════════════════════════════════════════════════

@client.event
async def on_ready():
    log(f"Bot connected as {client.user} (ID: {client.user.id})")
    sites = ", ".join(s["name"] for s in CAREER_SITES)

    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(
            f"🦞 **JobClaw Bot is online!**\n"
            f"Scanning **{sites}** Careers every **10 minutes** (last 24hrs only).\n"
            f"Commands: `!scan` (immediate scan), `!status` (stats)"
        )
        scrape_and_post.start()
    else:
        log(f"Could not find channel {CHANNEL_ID}!", "ERROR")


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    if message.content.strip().lower() == "!scan":
        await message.channel.send("🔍 **Scanning Google + Microsoft Careers...**")
        jobs = await asyncio.get_event_loop().run_in_executor(None, scrape_all_sites)

        if not jobs:
            await message.channel.send("❌ No jobs returned. Check logs.")
            return

        posted = load_posted_jobs()
        new_jobs = [j for j in jobs if j.get("url") not in posted]

        if not new_jobs:
            await message.channel.send("✅ No new listings — all previously posted.")
            return

        companies = {}
        for j in new_jobs:
            c = j.get("company", "Unknown")
            companies[c] = companies.get(c, 0) + 1
        breakdown = " + ".join(f"**{count}** {name}" for name, count in companies.items())

        scan_time = datetime.now().strftime("%I:%M %p")
        await message.channel.send(
            f"🚀 **{len(new_jobs)} New Listing{'s' if len(new_jobs) != 1 else ''}!** ({scan_time})\n"
            f"📅 Last 24hrs • {breakdown}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        for i, job in enumerate(new_jobs, 1):
            embed = build_embed(job, i, len(new_jobs))
            await message.channel.send(embed=embed)
            posted.add(job.get("url", ""))
            await asyncio.sleep(1)
        save_posted_jobs(posted)

    elif message.content.strip().lower() == "!status":
        posted = load_posted_jobs()
        sites = ", ".join(s["name"] for s in CAREER_SITES)
        await message.channel.send(
            f"📊 **JobClaw Status**\n"
            f"• Sites: **{sites}**\n"
            f"• Jobs tracked: **{len(posted)}**\n"
            f"• Scan interval: **10 minutes** (last 24hrs only)\n"
            f"• Commands: `!scan`, `!status`"
        )


# ═══════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log("Starting JobClaw Discord bot...")
    client.run(BOT_TOKEN)
