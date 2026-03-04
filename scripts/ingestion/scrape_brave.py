"""
Brave Search API Scraper — fast, reliable job discovery from LinkedIn/Indeed/Glassdoor.

Replaces the fragile OpenClaw browser automation with simple HTTP API calls.
Brave Search indexes LinkedIn, Indeed, Glassdoor, and other job boards — we search
for recent job postings and extract structured data from the results.

Free tier: 2,000 queries/month (https://brave.com/search/api/)

Setup:
  1. Get API key from https://api.search.brave.com/register
  2. Add to .env: BRAVE_SEARCH_API_KEY=BSA...
"""

import asyncio
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.logger import _log
from scripts.ingestion.role_filter import matches_target_role
from scripts.ingestion.us_filter import is_us_location
from scripts.database.db_utils import get_connection, insert_job, log_scraper_run

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

BRAVE_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

# Job search queries — each gets its own API call
# Designed to maximize coverage across roles and platforms
SEARCH_QUERIES = [
    # AI/ML roles
    {"q": "AI engineer jobs United States posted today", "category": "AI/ML"},
    {"q": "machine learning engineer jobs hiring now USA", "category": "AI/ML"},
    # SWE roles
    {"q": "software engineer jobs United States posted today", "category": "SWE"},
    {"q": "backend engineer jobs USA hiring now 2026", "category": "SWE"},
    {"q": "frontend developer jobs remote United States", "category": "SWE"},
    # Data roles
    {"q": "data scientist jobs United States posted today", "category": "Data Science"},
    {"q": "data engineer jobs hiring USA", "category": "Data Engineering"},
    {"q": "data analyst jobs United States entry level", "category": "Data Analyst"},
    # New Grad / Internship
    {"q": "new grad software engineer 2026 jobs USA", "category": "New Grad"},
    {"q": "software engineering internship 2026 USA", "category": "New Grad"},
    # Product / Research
    {"q": "product manager tech jobs United States", "category": "Product"},
    {"q": "research scientist AI jobs USA", "category": "Research"},
]

# Domains that are job boards — used to identify and parse job listings
JOB_BOARD_DOMAINS = {
    "linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com",
    "monster.com", "dice.com", "wellfound.com", "simplyhired.com",
    "careerbuilder.com", "builtin.com", "levels.fyi",
}

# ATS domains we already scrape — skip these to avoid duplicates
ATS_DOMAINS = {
    "greenhouse.io", "lever.co", "myworkdayjobs.com", "ashbyhq.com",
    "workable.com", "rippling.com", "smartrecruiters.com",
}


def _log_brave(msg: str, level: str = "INFO"):
    _log(msg, level, "brave_search")


def _is_job_board_url(url: str) -> bool:
    """Check if a URL is from a known job board (not an ATS we already scrape)."""
    url_lower = url.lower()
    # Skip ATS domains we already cover
    for domain in ATS_DOMAINS:
        if domain in url_lower:
            return False
    # Check if it's a job board
    for domain in JOB_BOARD_DOMAINS:
        if domain in url_lower:
            return True
    return False


def _extract_job_from_result(result: dict, category: str) -> dict | None:
    """
    Extract a job listing from a Brave Search result.

    Brave returns results like:
    {
        "title": "Senior ML Engineer - Google - Mountain View, CA | LinkedIn",
        "url": "https://www.linkedin.com/jobs/view/123456",
        "description": "Google is hiring a Senior ML Engineer in Mountain View..."
    }
    """
    title_raw = result.get("title", "")
    url = result.get("url", "")
    description = result.get("description", "")

    if not title_raw or not url:
        return None

    # Skip non-job-board URLs
    if not _is_job_board_url(url):
        return None

    # Parse the title — job board titles usually follow patterns:
    # "Senior ML Engineer - Google - Mountain View, CA | LinkedIn"
    # "Software Engineer at Stripe | Indeed.com"
    # "Data Scientist - Meta - New York, NY | Glassdoor"

    # Remove site suffixes
    title_clean = re.sub(r'\s*\|\s*(LinkedIn|Indeed\.com|Glassdoor|ZipRecruiter|Dice|Wellfound).*$', '', title_raw)
    title_clean = re.sub(r'\s*-\s*(LinkedIn|Indeed|Glassdoor).*$', '', title_clean)

    # Try to extract company and location from the title
    company = "Unknown"
    location = ""
    job_title = title_clean

    # Pattern: "Title - Company - Location"
    parts = [p.strip() for p in title_clean.split(" - ")]
    if len(parts) >= 3:
        job_title = parts[0]
        company = parts[1]
        location = parts[2]
    elif len(parts) == 2:
        job_title = parts[0]
        # Second part could be company or "company, location"
        if "," in parts[1]:
            sub = parts[1].split(",", 1)
            company = sub[0].strip()
            location = sub[1].strip()
        else:
            company = parts[1]

    # Pattern: "Title at Company"
    if company == "Unknown" and " at " in title_clean:
        at_parts = title_clean.split(" at ", 1)
        job_title = at_parts[0].strip()
        company = at_parts[1].strip()

    # Try to extract location from description if not in title
    if not location and description:
        # Look for common US location patterns
        loc_match = re.search(
            r'(?:in|location[:\s]+)\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s*[A-Z]{2})',
            description
        )
        if loc_match:
            location = loc_match.group(1)

    if not location:
        location = "United States"

    # Determine source ATS from URL
    source_ats = "brave_search"
    for domain in JOB_BOARD_DOMAINS:
        if domain in url.lower():
            source_ats = domain.split(".")[0]
            break

    # Create hash
    hash_input = f"{job_title}|{company}|{url}"
    internal_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    return {
        "internal_hash": internal_hash,
        "title": job_title,
        "company": company,
        "location": location,
        "url": url,
        "source_ats": source_ats,
        "date_posted": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "keywords_matched": json.dumps([category]),
        "description": description[:500] if description else "",
    }


async def _search_brave(session, query: str, count: int = 20) -> list[dict]:
    """Execute a single Brave Search API query."""
    import aiohttp

    params = {
        "q": query,
        "count": count,
        "freshness": "pw",  # past week (wider net for more results)
        "country": "us",
        "text_decorations": 0,  # must be int, not bool (aiohttp restriction)
    }
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_API_KEY,
    }

    try:
        async with session.get(BRAVE_SEARCH_URL, params=params, headers=headers) as resp:
            if resp.status == 429:
                _log_brave("Rate limited by Brave API — waiting 2s", "WARN")
                await asyncio.sleep(2)
                return []
            if resp.status == 401:
                _log_brave("Brave API key invalid or missing", "ERROR")
                return []
            if resp.status != 200:
                _log_brave(f"Brave API returned {resp.status}", "WARN")
                return []

            data = await resp.json()
            results = data.get("web", {}).get("results", [])
            return results
    except Exception as e:
        _log_brave(f"Brave API error: {e}", "ERROR")
        return []


async def run_brave_scraper() -> int:
    """
    Run all Brave Search queries and insert discovered jobs.
    Returns the number of new jobs inserted.
    """
    import aiohttp

    if not BRAVE_API_KEY:
        _log_brave("BRAVE_SEARCH_API_KEY not set — skipping Brave Search scraper.", "WARN")
        return 0

    start = time.time()
    _log_brave(f"Starting Brave Search scraper with {len(SEARCH_QUERIES)} queries...")

    conn = get_connection()
    total_inserted = 0
    total_results = 0
    total_skipped = 0

    try:
        async with aiohttp.ClientSession() as session:
            for i, sq in enumerate(SEARCH_QUERIES):
                query = sq["q"]
                category = sq["category"]

                _log_brave(f"[{i+1}/{len(SEARCH_QUERIES)}] Searching: {query}")
                results = await _search_brave(session, query)
                _log_brave(f"  → {len(results)} results")

                for result in results:
                    total_results += 1
                    job = _extract_job_from_result(result, category)
                    if not job:
                        continue

                    # Filter: US only
                    if not is_us_location(job["location"]):
                        total_skipped += 1
                        continue

                    # Filter: target roles only
                    if not matches_target_role(job["title"]):
                        total_skipped += 1
                        continue

                    # Insert (duplicates rejected by UNIQUE constraint)
                    try:
                        inserted = insert_job(conn, job)
                        if inserted:
                            total_inserted += 1
                    except Exception:
                        pass  # Duplicate hash — skip silently

                # Respect rate limits: 1 query per second (free tier)
                await asyncio.sleep(1.0)

        dur = round(time.time() - start, 1)
        _log_brave(
            f"Done in {dur}s — {total_results} results, "
            f"{total_inserted} new jobs inserted, {total_skipped} filtered out"
        )

        log_scraper_run(conn, "brave_search", total_inserted, 0, dur)

    except Exception as e:
        _log_brave(f"Brave Search scraper failed: {e}", "ERROR")
    finally:
        conn.close()

    return total_inserted


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    count = asyncio.run(run_brave_scraper())
    print(f"Brave Search: {count} new jobs discovered.")
