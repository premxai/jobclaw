"""
YC Startups Scraper — workatastartup.com

Fetches job listings from Y Combinator's Work at a Startup board.
Uses aiohttp to fetch HTML and basic regex/string parsing to extract
company names, job titles, and locations.

Source tag: yc_startups
"""

import asyncio
import hashlib
import re
import sys
import time
from pathlib import Path

import aiohttp

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ingestion.role_filter import matches_target_role
from scripts.ingestion.us_filter import is_us_location
from scripts.utils.logger import _log

SOURCE_ATS = "yc_startups"
BASE_URL = "https://www.workatastartup.com"
JOBS_URL = f"{BASE_URL}/jobs"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
}


def _make_job_id(company: str, title: str, url: str) -> str:
    """Generate a stable unique job ID from company + title, or from URL slug."""
    # Prefer extracting slug from URL if it has meaningful path segments
    slug_match = re.search(r"/jobs/(\d+)", url)
    if slug_match:
        return f"yc_{slug_match.group(1)}"
    # Fall back to hash of company + title
    raw = f"{company.lower().strip()}|{title.lower().strip()}"
    return "yc_" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def _clean_text(text: str) -> str:
    """Strip HTML tags and normalise whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#39;", "'", text)
    text = re.sub(r"&nbsp;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_location(raw: str) -> str:
    """Normalise a raw location string."""
    loc = _clean_text(raw).strip()
    if not loc:
        return "Remote"
    # Collapse common remote variants
    if re.search(r"\bremote\b", loc, re.IGNORECASE):
        return "Remote"
    return loc


def _extract_jobs_from_html(html: str) -> list[dict]:
    """
    Parse job listings from the workatastartup.com HTML.

    The page renders job cards with these approximate patterns:
      - Job title inside an <a> with href="/jobs/<id>"
      - Company name in a nearby element
      - Location as plain text near the card

    Since the page may be JS-rendered, we do best-effort regex extraction.
    """
    jobs: list[dict] = []

    # Strategy 1: extract structured JSON-LD or window.__INITIAL_STATE__ if present
    json_ld_match = re.search(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if json_ld_match:
        import json

        try:
            data = json.loads(json_ld_match.group(1))
            if isinstance(data, list):
                data = data[0] if data else {}
            if data.get("@type") == "JobPosting":
                title = data.get("title", "")
                company = data.get("hiringOrganization", {}).get("name", "")
                location_obj = data.get("jobLocation", {})
                address = location_obj.get("address", {})
                location = address.get("addressLocality", "") or address.get("addressRegion", "")
                url_path = data.get("url", JOBS_URL)
                if title and company:
                    jobs.append(
                        {
                            "title": title,
                            "company": company,
                            "location": _parse_location(location),
                            "url": url_path,
                            "date_posted": data.get("datePosted", ""),
                            "description": _clean_text(data.get("description", "")),
                        }
                    )
        except Exception:
            pass

    # Strategy 2: regex over job card anchors — works when SSR HTML is available
    # Pattern: <a href="/jobs/12345">Job Title</a> ... company info nearby
    card_pattern = re.compile(
        r'<a[^>]+href="(/jobs/(\d+))"[^>]*>\s*(.*?)\s*</a>',
        re.DOTALL | re.IGNORECASE,
    )

    # Also try to find company blocks that wrap job listings
    # e.g. data-company-name="Acme" or <span class="company-name">Acme</span>
    company_block_pattern = re.compile(
        r'(?:data-company(?:-name)?=["\']([^"\']+)["\']'
        r'|class=["\'][^"\']*company[^"\']*["\'][^>]*>\s*([^<]{1,80})<)',
        re.IGNORECASE,
    )

    location_pattern = re.compile(
        r'(?:class=["\'][^"\']*location[^"\']*["\'][^>]*>\s*([^<]{1,80})<'
        r'|data-location=["\']([^"\']+)["\'])',
        re.IGNORECASE,
    )

    seen_ids: set[str] = set()

    for m in card_pattern.finditer(html):
        path, job_num, raw_title = m.group(1), m.group(2), m.group(3)
        title = _clean_text(raw_title)

        # Skip non-job anchors (navigation, company links, etc.)
        if not title or len(title) < 3 or len(title) > 120:
            continue
        if job_num in seen_ids:
            continue
        seen_ids.add(job_num)

        job_url = f"{BASE_URL}{path}"

        # Look for company and location in the surrounding 800 chars of HTML
        start = max(0, m.start() - 600)
        end = min(len(html), m.end() + 600)
        context = html[start:end]

        company = ""
        company_m = company_block_pattern.search(context)
        if company_m:
            company = _clean_text(company_m.group(1) or company_m.group(2) or "")

        location = "Remote"
        loc_m = location_pattern.search(context)
        if loc_m:
            raw_loc = loc_m.group(1) or loc_m.group(2) or ""
            location = _parse_location(raw_loc)

        if not company:
            company = "YC Startup"

        jobs.append(
            {
                "title": title,
                "company": company,
                "location": location,
                "url": job_url,
                "date_posted": "",
                "description": "",
            }
        )

    # Strategy 3: look for the Next.js / React hydration payload (__NEXT_DATA__)
    next_data_match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if next_data_match and not jobs:
        import json

        try:
            payload = json.loads(next_data_match.group(1))
            # Drill into pageProps → jobs (structure varies by site version)
            page_props = payload.get("props", {}).get("pageProps", {})
            raw_jobs = page_props.get("jobs", page_props.get("jobListings", []))
            if isinstance(raw_jobs, list):
                for rj in raw_jobs:
                    title = rj.get("title") or rj.get("job_title") or ""
                    company_obj = rj.get("company") or {}
                    if isinstance(company_obj, dict):
                        company = company_obj.get("name") or company_obj.get("company_name") or ""
                    else:
                        company = str(company_obj)
                    location = rj.get("location") or rj.get("remote_ok") or "Remote"
                    job_id_raw = str(rj.get("id") or rj.get("job_id") or "")
                    url = rj.get("url") or (f"{BASE_URL}/jobs/{job_id_raw}" if job_id_raw else JOBS_URL)
                    desc = _clean_text(rj.get("description") or rj.get("body") or "")
                    date_posted = rj.get("created_at") or rj.get("date_posted") or ""
                    if title:
                        jobs.append(
                            {
                                "title": _clean_text(title),
                                "company": _clean_text(company) or "YC Startup",
                                "location": _parse_location(str(location)),
                                "url": url,
                                "date_posted": date_posted,
                                "description": desc,
                            }
                        )
        except Exception:
            pass

    return jobs


def _build_normalized_job(raw: dict) -> dict:
    """Convert a raw parsed dict into a NormalizedJob-compatible dict."""
    title = raw["title"]
    company = raw["company"]
    location = raw["location"]
    url = raw["url"]
    date_posted = raw.get("date_posted", "")
    description = raw.get("description", "")

    job_id = _make_job_id(company, title, url)
    keywords = matches_target_role(title)

    return {
        "job_id": job_id,
        "title": title,
        "company": company,
        "location": location,
        "url": url,
        "date_posted": date_posted,
        "source_ats": SOURCE_ATS,
        "description": description,
        "keywords_matched": keywords,
    }


async def fetch_yc_jobs(session: aiohttp.ClientSession) -> list[dict]:
    """
    Fetch and parse YC startup jobs from workatastartup.com.
    Returns a list of NormalizedJob-compatible dicts.
    """
    try:
        async with session.get(JOBS_URL, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                _log(f"[yc_startups] HTTP {resp.status} fetching {JOBS_URL}", "WARNING")
                return []
            html = await resp.text(encoding="utf-8", errors="replace")
    except Exception as e:
        _log(f"[yc_startups] Fetch error: {e}", "ERROR")
        return []

    raw_jobs = _extract_jobs_from_html(html)
    _log(f"[yc_startups] Parsed {len(raw_jobs)} raw job entries from HTML.")

    results: list[dict] = []
    seen_ids: set[str] = set()

    for raw in raw_jobs:
        if not raw.get("title") or not raw.get("company"):
            continue

        # Role filter
        if not matches_target_role(raw["title"]):
            continue

        # US location filter
        if not is_us_location(raw["location"]):
            continue

        job = _build_normalized_job(raw)

        if job["job_id"] in seen_ids:
            continue
        seen_ids.add(job["job_id"])

        results.append(job)

    _log(f"[yc_startups] {len(results)} jobs passed role + US filters.")
    return results


async def main():
    """Standalone runner — prints filtered YC jobs to stdout."""
    start = time.time()
    _log("=== YC Startups Scraper ===")

    async with aiohttp.ClientSession() as session:
        jobs = await fetch_yc_jobs(session)

    for job in jobs:
        print(f"[{job['source_ats']}] {job['company']} | {job['title']} | {job['location']} | {job['url']}")

    elapsed = round(time.time() - start, 2)
    _log(f"=== Done: {len(jobs)} jobs found in {elapsed}s ===")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
