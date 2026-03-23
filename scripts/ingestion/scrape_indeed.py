"""
Indeed Public Job Search Scraper (Deep Tier).

Searches Indeed's public job listing pages for tech roles using category-specific
queries.  No authentication required.  Uses Scrapling's Fetcher (stealth mode)
to bypass bot-detection; falls back to aiohttp if Scrapling is unavailable or
returns an unexpected response.

Search URL pattern:
  https://www.indeed.com/jobs?q={query}&l=United+States&fromage=1&sort=date
  (fromage=1 → last 24 hours, sort=date → newest first)

Source tag: indeed
Tier:       deep (5-second inter-query delay, conservative)
"""

import asyncio
import hashlib
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlencode, urlparse

import aiohttp

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.database.db_utils import get_connection, insert_job, log_scraper_run
from scripts.ingestion.role_filter import matches_target_role
from scripts.ingestion.us_filter import is_us_location
from scripts.utils.logger import _log

# ═══════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════

SOURCE_ATS = "indeed"

SEARCH_QUERIES: list[str] = [
    "software engineer",
    "machine learning engineer",
    "data engineer",
    "data scientist",
    "product manager",
    "new grad software engineer",
]

INDEED_BASE_URL = "https://www.indeed.com"
INDEED_SEARCH_URL = INDEED_BASE_URL + "/jobs?" + urlencode({"l": "United States", "fromage": "1", "sort": "date"})

# Delay between consecutive search queries (seconds)
INTER_QUERY_DELAY: float = 5.0

# HTTP headers used when falling back to aiohttp
FALLBACK_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════


def _build_search_url(query: str) -> str:
    """Return the Indeed search URL for a given query string."""
    return f"{INDEED_SEARCH_URL}&q={quote_plus(query)}"


def _extract_jk(url: str) -> str:
    """Extract the `jk` (job key) query parameter from an Indeed URL."""
    try:
        params = parse_qs(urlparse(url).query)
        jks = params.get("jk", [])
        if jks:
            return jks[0]
    except Exception:
        pass
    return ""


def _make_job_id(url: str, company: str, title: str) -> str:
    """
    Generate a stable job_id.
    Prefer the `jk=` parameter from the URL; otherwise fall back to a
    short SHA-256 of company + title.
    """
    jk = _extract_jk(url)
    if jk:
        return f"indeed_{jk}"
    digest = hashlib.sha256(f"{company}|{title}".encode()).hexdigest()[:16]
    return f"indeed_{digest}"


def _normalise_url(href: str) -> str:
    """Ensure the URL is absolute (prepend Indeed base if relative)."""
    href = href.strip()
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return INDEED_BASE_URL + href
    return href


def _today_iso() -> str:
    """Return today's date in ISO-8601 format (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _safe_text(element) -> str:
    """Extract stripped text from a Scrapling element, or '' on failure."""
    if element is None:
        return ""
    try:
        return element.text.strip()
    except Exception:
        return ""


def _safe_attr(element, attr: str) -> str:
    """Get an attribute from a Scrapling element, or '' on failure."""
    if element is None:
        return ""
    try:
        return (element.attrib.get(attr) or "").strip()
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════════════
# HTML PARSERS
# ═══════════════════════════════════════════════════════════════════════


def _parse_indeed_page_scrapling(page) -> list[dict]:
    """
    Parse an Indeed search result page fetched via Scrapling.

    Tries multiple CSS selectors because Indeed frequently changes its markup.
    Returns a list of partial job dicts (without source_ats / keywords_matched).
    """
    jobs: list[dict] = []

    try:
        # Cards can appear under several container selectors
        cards = page.css(".job_seen_beacon, .resultContent, .tapItem, [data-jk]")
        if not cards:
            # Broad fallback: any list-item that contains a job title heading
            cards = page.css("li")
    except Exception as e:
        _log(f"[indeed] Scrapling CSS select failed: {e}", "ERROR")
        return jobs

    for card in cards:
        try:
            # ── Title ──────────────────────────────────────────────
            title_el = card.css_first("h2 a, .jobTitle a, a[data-jk]")
            title = _safe_text(title_el)
            if not title:
                continue

            # ── URL / job-key ───────────────────────────────────
            href = _safe_attr(title_el, "href")
            jk = _safe_attr(title_el, "data-jk")

            if not href and jk:
                href = f"{INDEED_BASE_URL}/viewjob?jk={jk}"
            elif href:
                href = _normalise_url(href)
            else:
                continue  # no usable URL

            # ── Company ────────────────────────────────────────────
            company_el = card.css_first("[data-testid='company-name'], .companyName, [class*='companyName']")
            company = _safe_text(company_el) or "Unknown"

            # ── Location ───────────────────────────────────────────
            location_el = card.css_first("[data-testid='text-location'], .companyLocation, [class*='companyLocation']")
            location = _safe_text(location_el) or "United States"

            # ── Date posted ────────────────────────────────────────
            date_el = card.css_first(".date, [class*='date'], [data-testid*='date']")
            date_raw = _safe_text(date_el)

            jobs.append(
                {
                    "title": title[:200],
                    "company": company[:200],
                    "location": location,
                    "url": href,
                    "date_raw": date_raw,
                }
            )
        except Exception:
            continue

    return jobs


def _parse_indeed_page_html(html: str) -> list[dict]:
    """
    Fallback HTML parser using plain regex / string operations.
    Indeed's HTML structure is volatile; this attempts several patterns.
    Returns a list of partial job dicts.
    """
    jobs: list[dict] = []

    # Find job cards by locating data-jk anchors
    card_blocks = re.findall(
        r'<div[^>]*class="[^"]*(?:job_seen_beacon|resultContent|tapItem)[^"]*"[^>]*>(.*?)</div>\s*</div>',
        html,
        re.DOTALL,
    )

    if not card_blocks:
        # Broad fallback: hunt for anchor tags with data-jk
        card_blocks = re.findall(
            r'(<a[^>]+data-jk="[^"]+"[^>]*>.*?</a>)',
            html,
            re.DOTALL,
        )

    for block in card_blocks:
        try:
            # job-key / URL
            jk_m = re.search(r'data-jk="([^"]+)"', block)
            href_m = re.search(r'href="(/jobs/[^"]+|/viewjob\?[^"]+)"', block)

            if jk_m:
                jk = jk_m.group(1)
                href = f"{INDEED_BASE_URL}/viewjob?jk={jk}"
            elif href_m:
                href = _normalise_url(href_m.group(1))
            else:
                continue

            # Title — text inside <h2> or <span title="…">
            title_m = re.search(
                r'<h2[^>]*class="[^"]*jobTitle[^"]*"[^>]*>.*?<span[^>]*>([^<]+)</span>',
                block,
                re.DOTALL,
            ) or re.search(r'<span[^>]+title="([^"]+)"', block)
            title = title_m.group(1).strip() if title_m else ""

            if not title:
                # Last resort: text node of the anchor
                text_m = re.search(r">[^<]{3,100}<", block)
                title = text_m.group(0)[1:-1].strip() if text_m else ""

            if not title:
                continue

            # Company
            company_m = re.search(
                r'class="[^"]*companyName[^"]*"[^>]*>\s*(?:<[^>]+>)*([^<]+)',
                block,
                re.DOTALL,
            )
            company = company_m.group(1).strip() if company_m else "Unknown"

            # Location
            location_m = re.search(
                r'class="[^"]*companyLocation[^"]*"[^>]*>\s*(?:<[^>]+>)*([^<]+)',
                block,
                re.DOTALL,
            )
            location = location_m.group(1).strip() if location_m else "United States"

            # Date
            date_m = re.search(
                r'class="[^"]*date[^"]*"[^>]*>\s*(?:<[^>]+>)*([^<]+)',
                block,
                re.DOTALL,
            )
            date_raw = date_m.group(1).strip() if date_m else ""

            jobs.append(
                {
                    "title": title[:200],
                    "company": company[:200],
                    "location": location,
                    "url": href,
                    "date_raw": date_raw,
                }
            )
        except Exception:
            continue

    return jobs


def _normalise_date(date_raw: str) -> str:
    """
    Convert Indeed's relative date strings (e.g. 'PostedJust posted',
    '3 days ago', 'Today') to an ISO-8601 date, or fall back to today.
    """
    today = _today_iso()
    if not date_raw:
        return today

    txt = date_raw.lower().strip()
    if "just" in txt or "today" in txt or "hour" in txt:
        return today

    m = re.search(r"(\d+)\s+day", txt)
    if m:
        days = int(m.group(1))
        dt = datetime.now(timezone.utc) - timedelta(days=days)
        return dt.strftime("%Y-%m-%d")

    return today


def _enrich_job(partial: dict) -> dict:
    """
    Add computed fields to a partial job dict:
      - job_id, date_posted, source_ats, description, keywords_matched
    """
    url = partial["url"]
    company = partial.get("company", "Unknown")
    title = partial.get("title", "")
    date_raw = partial.pop("date_raw", "")

    return {
        "job_id": _make_job_id(url, company, title),
        "title": title,
        "company": company,
        "location": partial.get("location", "United States"),
        "url": url,
        "date_posted": _normalise_date(date_raw),
        "source_ats": SOURCE_ATS,
        "description": "",
        "keywords_matched": matches_target_role(title),
    }


# ═══════════════════════════════════════════════════════════════════════
# FETCH STRATEGIES
# ═══════════════════════════════════════════════════════════════════════


def _fetch_with_scrapling(url: str):
    """
    Synchronous fetch using Scrapling Fetcher (run via asyncio.to_thread).
    Returns the page object or raises.
    """
    from scrapling import Fetcher  # deferred import — optional dependency

    fetcher = Fetcher(auto_match=False)
    return fetcher.get(url, stealthy_headers=True)


async def _fetch_html_aiohttp(url: str, session: aiohttp.ClientSession) -> str | None:
    """Fallback: plain aiohttp GET with browser-like headers."""
    try:
        async with session.get(
            url,
            headers=FALLBACK_HEADERS,
            timeout=aiohttp.ClientTimeout(total=20),
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                _log(f"[indeed] aiohttp HTTP {resp.status} for {url[:80]}", "WARNING")
                return None
            return await resp.text(errors="replace")
    except Exception as e:
        _log(f"[indeed] aiohttp fetch error: {e}", "WARNING")
        return None


async def _fetch_and_parse(url: str, session: aiohttp.ClientSession) -> list[dict]:
    """
    Fetch an Indeed page and return parsed partial job dicts.
    Tries Scrapling first; falls back to aiohttp + regex parser.
    """
    # ── Strategy 1: Scrapling (stealth) ──────────────────────────────
    try:
        page = await asyncio.to_thread(_fetch_with_scrapling, url)
        if page is not None and getattr(page, "status", 200) == 200:
            jobs = _parse_indeed_page_scrapling(page)
            if jobs:
                _log(f"[indeed] Scrapling parsed {len(jobs)} cards from {url[:80]}")
                return jobs
            _log("[indeed] Scrapling returned 0 cards — trying aiohttp fallback")
    except ImportError:
        _log("[indeed] scrapling not available, using aiohttp fallback", "WARNING")
    except Exception as e:
        _log(f"[indeed] Scrapling error ({e}), trying aiohttp fallback", "WARNING")

    # ── Strategy 2: aiohttp + regex parser ───────────────────────────
    html = await _fetch_html_aiohttp(url, session)
    if not html:
        return []
    jobs = _parse_indeed_page_html(html)
    _log(f"[indeed] aiohttp+regex parsed {len(jobs)} cards from {url[:80]}")
    return jobs


# ═══════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════


async def fetch_indeed_jobs(session: aiohttp.ClientSession | None = None) -> list[dict]:
    """
    Search Indeed for tech jobs across SEARCH_QUERIES.

    Args:
        session: An active aiohttp.ClientSession (used as fallback).

    Returns:
        List of job dicts matching the jobs table schema, filtered by
        role and US location.
    """
    if session is None:
        async with aiohttp.ClientSession() as session:
            return await fetch_indeed_jobs(session)

    all_jobs: list[dict] = []
    seen_ids: set[str] = set()

    for i, query in enumerate(SEARCH_QUERIES):
        url = _build_search_url(query)
        _log(f"[indeed] Querying: {query!r} → {url[:100]}")

        partials = await _fetch_and_parse(url, session)

        for partial in partials:
            job = _enrich_job(partial)

            # Role filter
            if not job["keywords_matched"]:
                continue

            # US location filter
            if not is_us_location(job["location"]):
                continue

            # Deduplication
            if job["job_id"] in seen_ids:
                continue
            seen_ids.add(job["job_id"])

            all_jobs.append(job)

        _log(f"[indeed] Running total after {query!r}: {len(all_jobs)} jobs")

        # Rate-limit between queries (skip delay after last query)
        if i < len(SEARCH_QUERIES) - 1:
            _log(f"[indeed] Sleeping {INTER_QUERY_DELAY}s before next query…")
            await asyncio.sleep(INTER_QUERY_DELAY)

    _log(f"[indeed] {len(all_jobs)} jobs passed role + US filters.")

    # DB insertion
    conn = get_connection()
    inserted = 0
    try:
        for job in all_jobs:
            if insert_job(conn, job):
                inserted += 1
        log_scraper_run(conn, "scrape_indeed", len(SEARCH_QUERIES), inserted, 0, "")
    finally:
        conn.close()
    _log(f"[indeed] Inserted {inserted} new jobs into DB.")
    return all_jobs


# ═══════════════════════════════════════════════════════════════════════
# STANDALONE ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════


async def main():
    """Standalone runner — prints filtered Indeed jobs to stdout."""
    start = time.time()
    _log("=== Indeed Job Scraper ===")

    async with aiohttp.ClientSession() as session:
        jobs = await fetch_indeed_jobs(session)

    for job in jobs:
        print(f"[{job['source_ats']}] {job['company']} | {job['title']} | {job['location']} | {job['url']}")

    elapsed = round(time.time() - start, 2)
    _log(f"=== Done: {len(jobs)} jobs found in {elapsed}s ===")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
