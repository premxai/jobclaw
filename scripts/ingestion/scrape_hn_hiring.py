"""
Hacker News "Who's Hiring?" Scraper

Uses the Algolia HN search API to find the current monthly "Who's Hiring?"
Ask HN thread, then fetches all top-level comments and parses them as job
postings.

Algolia endpoints:
  Search:  https://hn.algolia.com/api/v1/search?query=who%27s%20hiring&tags=ask_hn&hitsPerPage=1
  Item:    https://hn.algolia.com/api/v1/items/{post_id}

Source tag: hn_hiring
"""

import asyncio
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.database.db_utils import get_connection, insert_job, log_scraper_run
from scripts.ingestion.role_filter import matches_target_role
from scripts.ingestion.us_filter import is_us_location
from scripts.utils.logger import _log

SOURCE_ATS = "hn_hiring"

ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search?query=who%27s%20hiring&tags=ask_hn&hitsPerPage=1"
ALGOLIA_ITEM_URL = "https://hn.algolia.com/api/v1/items/{post_id}"
HN_ITEM_URL = "https://news.ycombinator.com/item?id={item_id}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Regex patterns for parsing comment text
_URL_RE = re.compile(r"https?://[^\s\)\]>\"']+", re.IGNORECASE)
_REMOTE_RE = re.compile(r"\bremote\b", re.IGNORECASE)
_ONSITE_RE = re.compile(r"\bon[\s-]?site\b|\bin[\s-]?office\b", re.IGNORECASE)
_HYBRID_RE = re.compile(r"\bhybrid\b", re.IGNORECASE)

# US state abbreviations for location detection
_US_STATE_RE = re.compile(
    r"\b(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|"
    r"MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|"
    r"VT|VA|WA|WV|WI|WY|DC)\b",
    re.IGNORECASE,
)

_US_CITIES_RE = re.compile(
    r"\b(?:San Francisco|New York|NYC|Los Angeles|Seattle|Austin|Boston|Chicago|"
    r"Denver|Atlanta|Portland|Miami|Dallas|Houston|Phoenix|San Jose|San Diego|"
    r"Washington DC|Raleigh|Minneapolis|Detroit|Philadelphia|Pittsburgh|"
    r"Salt Lake City|Las Vegas|Nashville|Charlotte|Columbus|Indianapolis)\b",
    re.IGNORECASE,
)


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = re.sub(r"<p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#x27;|&#39;", "'", text)
    text = re.sub(r"&nbsp;", " ", text)
    return text.strip()


def _extract_urls(text: str) -> list[str]:
    """Return all HTTP(S) URLs found in the text."""
    return _URL_RE.findall(text)


def _detect_location(text: str) -> str:
    """
    Heuristically determine location from comment text.
    Priority: explicit Remote > city/state mention > "Remote" default.
    """
    if _REMOTE_RE.search(text):
        # Could still have a physical location; keep it simple
        return "Remote"

    city_m = _US_CITIES_RE.search(text)
    if city_m:
        city = city_m.group(0)
        state_m = _US_STATE_RE.search(text[city_m.start() : city_m.start() + 60])
        if state_m:
            return f"{city}, {state_m.group(0).upper()}"
        return city

    state_m = _US_STATE_RE.search(text)
    if state_m:
        return state_m.group(0).upper()

    return "Remote"


def _parse_first_line(first_line: str) -> tuple[str, str]:
    """
    Parse the first line of an HN hiring comment into (company, title).

    Common formats:
      "Acme Corp | Software Engineer | Remote | Full-time"
      "Acme Corp (YC S22) - Backend Engineer"
      "Acme Corp: we are hiring a Data Scientist"
      "Software Engineer at Acme Corp"
    """
    line = first_line.strip()

    # Format: "Company | Title | ..."
    if "|" in line:
        parts = [p.strip() for p in line.split("|")]
        company = parts[0] if parts else "Unknown"
        title = parts[1] if len(parts) > 1 else ""
        return company, title

    # Format: "Company - Title" or "Company — Title"
    dash_m = re.match(r"^(.+?)\s+[-—–]\s+(.+)$", line)
    if dash_m:
        return dash_m.group(1).strip(), dash_m.group(2).strip()

    # Format: "Title at Company"
    at_m = re.match(r"^(.+?)\s+at\s+(.+)$", line, re.IGNORECASE)
    if at_m:
        return at_m.group(2).strip(), at_m.group(1).strip()

    # Format: "Company: description" (company only, no title)
    colon_m = re.match(r"^([^:]{2,60}):\s+(.+)$", line)
    if colon_m:
        return colon_m.group(1).strip(), ""

    # Default: treat whole first line as company, no title
    return line[:80], ""


def _parse_comment(comment: dict, month_str: str) -> dict | None:
    """
    Convert a single HN comment dict (from Algolia) into a job dict.
    Returns None if the comment cannot be meaningfully parsed.
    """
    raw_text = comment.get("text") or ""
    if not raw_text or len(raw_text) < 20:
        return None

    item_id = str(comment.get("id") or comment.get("objectID") or "")
    plain_text = _strip_html(raw_text)
    lines = [ln.strip() for ln in plain_text.splitlines() if ln.strip()]

    if not lines:
        return None

    first_line = lines[0]
    company, title = _parse_first_line(first_line)

    # If title is empty, scan subsequent lines for role keywords
    if not title:
        for line in lines[1:5]:
            kw = matches_target_role(line)
            if kw:
                title = line[:120]
                break

    if not title:
        return None

    location = _detect_location(plain_text)

    # Extract a job URL from the comment (prefer non-HN links)
    urls = _extract_urls(plain_text)
    job_url = next(
        (u for u in urls if "ycombinator.com" not in u and "news.ycombinator.com" not in u),
        HN_ITEM_URL.format(item_id=item_id) if item_id else "",
    )
    if not job_url:
        job_url = HN_ITEM_URL.format(item_id=item_id) if item_id else ""

    # Build a stable job_id: company slug + month
    company_slug = re.sub(r"[^a-z0-9]+", "_", company.lower().strip())[:40]
    job_id = f"hn_{company_slug}_{month_str}"

    keywords = matches_target_role(title)

    return {
        "job_id": job_id,
        "title": title.strip()[:200],
        "company": company.strip()[:200],
        "location": location,
        "url": job_url,
        "date_posted": "",
        "source_ats": SOURCE_ATS,
        "description": plain_text[:4000],
        "keywords_matched": keywords,
    }


async def _find_latest_hiring_post(session: aiohttp.ClientSession) -> str | None:
    """Search Algolia for the most recent 'Who's Hiring?' thread and return its ID."""
    try:
        async with session.get(
            ALGOLIA_SEARCH_URL,
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                _log(f"[hn_hiring] Algolia search HTTP {resp.status}", "WARNING")
                return None
            data = await resp.json()
    except Exception as e:
        _log(f"[hn_hiring] Algolia search error: {e}", "ERROR")
        return None

    hits = data.get("hits", [])
    if not hits:
        _log("[hn_hiring] No 'Who's Hiring?' threads found.", "WARNING")
        return None

    post_id = str(hits[0].get("objectID") or hits[0].get("id") or "")
    title = hits[0].get("title", "")
    _log(f"[hn_hiring] Found thread: '{title}' (ID: {post_id})")
    return post_id or None


async def _fetch_post_comments(session: aiohttp.ClientSession, post_id: str) -> list[dict]:
    """Fetch the full HN thread item and return its top-level children (comments)."""
    url = ALGOLIA_ITEM_URL.format(post_id=post_id)
    try:
        async with session.get(
            url,
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                _log(f"[hn_hiring] Item fetch HTTP {resp.status} for post {post_id}", "WARNING")
                return []
            data = await resp.json()
    except Exception as e:
        _log(f"[hn_hiring] Item fetch error: {e}", "ERROR")
        return []

    children = data.get("children") or []
    _log(f"[hn_hiring] Thread has {len(children)} top-level comments.")
    return children


async def fetch_hn_hiring_jobs(session: aiohttp.ClientSession | None = None) -> list[dict]:
    """
    Fetch and parse the HN Who's Hiring thread.
    Returns a list of NormalizedJob-compatible dicts.
    """
    if session is None:
        async with aiohttp.ClientSession() as session:
            return await fetch_hn_hiring_jobs(session)
    month_str = datetime.now(timezone.utc).strftime("%Y-%m")

    post_id = await _find_latest_hiring_post(session)
    if not post_id:
        return []

    comments = await _fetch_post_comments(session, post_id)
    if not comments:
        return []

    results: list[dict] = []
    seen_ids: set[str] = set()

    for comment in comments:
        job = _parse_comment(comment, month_str)
        if job is None:
            continue

        # Role filter
        if not job["keywords_matched"] and not matches_target_role(job["description"][:500]):
            continue

        # US location filter
        if not is_us_location(job["location"]):
            continue

        # Deduplicate by job_id (company slug + month)
        if job["job_id"] in seen_ids:
            continue
        seen_ids.add(job["job_id"])

        # Ensure keywords_matched populated
        if not job["keywords_matched"]:
            job["keywords_matched"] = matches_target_role(job["description"][:500])

        results.append(job)

    _log(f"[hn_hiring] {len(results)} jobs passed role + US filters.")

    # DB insertion
    conn = get_connection()
    inserted = 0
    try:
        for job in results:
            if insert_job(conn, job):
                inserted += 1
        log_scraper_run(conn, "scrape_hn_hiring", 1, inserted, 0, "")
    finally:
        conn.close()
    _log(f"[hn_hiring] Inserted {inserted} new jobs into DB.")
    return results


async def main():
    """Standalone runner — prints filtered HN hiring jobs to stdout."""
    start = time.time()
    _log("=== HN Who's Hiring Scraper ===")

    async with aiohttp.ClientSession() as session:
        jobs = await fetch_hn_hiring_jobs(session)

    for job in jobs:
        print(f"[{job['source_ats']}] {job['company']} | {job['title']} | {job['location']} | {job['url']}")

    elapsed = round(time.time() - start, 2)
    _log(f"=== Done: {len(jobs)} jobs found in {elapsed}s ===")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
