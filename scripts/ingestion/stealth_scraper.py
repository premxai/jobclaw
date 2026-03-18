"""
Stealth Scraper — replaces broken OpenClaw CLI.

Uses Scrapling's Fetcher with browser-grade headers + fingerprint spoofing
to scrape protected job boards (LinkedIn, Indeed, Glassdoor).

Each board has its own parser because the HTML structure differs wildly.
Results are filtered, deduplicated, and inserted into the SQLite database.

Usage:
    python -m scripts.ingestion.stealth_scraper
    # or via the orchestrator:
    python scripts/ingestion/run_all_scrapers.py --tier deep
"""

import asyncio
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scrapling import Fetcher

from scripts.database.db_utils import get_connection, insert_job, log_scraper_run
from scripts.ingestion.role_filter import matches_target_role
from scripts.ingestion.us_filter import is_us_location
from scripts.utils.logger import _log

# ═══════════════════════════════════════════════════════════════════════
# TARGET DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════

TARGETS = [
    {
        "name": "LinkedIn AI/ML Jobs",
        "urls": [
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=AI+Software+Engineer&location=United+States&f_TPR=r86400&start=0",
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=Machine+Learning+Engineer&location=United+States&f_TPR=r86400&start=0",
        ],
        "source_ats": "linkedin",
        "parser": "parse_linkedin",
    },
    {
        "name": "Indeed SWE",
        "urls": [
            "https://www.indeed.com/jobs?q=Software+Engineer&l=United+States&fromage=1&sort=date",
            "https://www.indeed.com/jobs?q=Machine+Learning+Engineer&l=United+States&fromage=1&sort=date",
        ],
        "source_ats": "indeed",
        "parser": "parse_indeed",
    },
    {
        "name": "Glassdoor Tech",
        "urls": [
            "https://www.glassdoor.com/Job/united-states-software-engineer-jobs-SRCH_IL.0,13_IN1_KO14,31.htm?fromAge=1",
        ],
        "source_ats": "glassdoor",
        "parser": "parse_glassdoor",
    },
]


# ═══════════════════════════════════════════════════════════════════════
# FETCHER — Scrapling with stealth headers
# ═══════════════════════════════════════════════════════════════════════


def create_fetcher():
    """Create a Scrapling Fetcher with anti-detection headers."""
    fetcher = Fetcher(auto_match=False)
    return fetcher


def _safe_text(element) -> str:
    """Extract text from a Scrapling element safely."""
    if element is None:
        return ""
    try:
        return element.text.strip()
    except Exception:
        return ""


def _safe_attr(element, attr: str) -> str:
    """Get an attribute from a Scrapling element safely."""
    if element is None:
        return ""
    try:
        return element.attrib.get(attr, "")
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════════════
# PARSERS — one per job board
# ═══════════════════════════════════════════════════════════════════════


def parse_linkedin(page) -> list[dict]:
    """Parse LinkedIn guest jobs API response (HTML fragment)."""
    jobs = []
    try:
        cards = page.css("li")
        for card in cards:
            try:
                title_el = card.css_first(".base-search-card__title")
                company_el = card.css_first(".base-search-card__subtitle a")
                location_el = card.css_first(".job-search-card__location")
                link_el = card.css_first("a.base-card__full-link")

                title = _safe_text(title_el)
                company = _safe_text(company_el)
                location = _safe_text(location_el)
                url = _safe_attr(link_el, "href")

                if not url:
                    url = _safe_attr(card.css_first("a"), "href")

                if title and url:
                    # Clean up LinkedIn tracking params from URL
                    url = url.split("?")[0] if "?" in url else url
                    jobs.append(
                        {
                            "title": title,
                            "company": company or "Unknown",
                            "location": location or "United States",
                            "url": url,
                            "job_id": url.split("/")[-1] if "/" in url else url,
                            "date_posted": "",
                        }
                    )
            except Exception:
                continue
    except Exception as e:
        _log(f"LinkedIn parse error: {e}", "ERROR")
    return jobs


def parse_indeed(page) -> list[dict]:
    """Parse Indeed job search results page."""
    jobs = []
    try:
        # Indeed uses various card selectors
        cards = page.css(".job_seen_beacon, .resultContent, .tapItem")
        for card in cards:
            try:
                title_el = card.css_first("h2 a, .jobTitle a, a[data-jk]")
                company_el = card.css_first("[data-testid='company-name'], .companyName")
                location_el = card.css_first("[data-testid='text-location'], .companyLocation")

                title = _safe_text(title_el)
                company = _safe_text(company_el)
                location = _safe_text(location_el)

                href = _safe_attr(title_el, "href")
                jk = _safe_attr(title_el, "data-jk")

                if href and not href.startswith("http"):
                    href = f"https://www.indeed.com{href}"
                elif jk:
                    href = f"https://www.indeed.com/viewjob?jk={jk}"

                if title and href:
                    jobs.append(
                        {
                            "title": title,
                            "company": company or "Unknown",
                            "location": location or "United States",
                            "url": href,
                            "job_id": jk or href.split("jk=")[-1].split("&")[0] if "jk=" in href else href,
                            "date_posted": "",
                        }
                    )
            except Exception:
                continue
    except Exception as e:
        _log(f"Indeed parse error: {e}", "ERROR")
    return jobs


def parse_glassdoor(page) -> list[dict]:
    """Parse Glassdoor job listing page."""
    jobs = []
    try:
        # Glassdoor uses React-rendered cards
        cards = page.css("[data-test='jobListing'], .react-job-listing, li[data-id]")
        for card in cards:
            try:
                title_el = card.css_first("[data-test='job-title'] a, .job-title a, a[data-test='job-link']")
                company_el = card.css_first("[data-test='emp-name'], .employer-name")
                location_el = card.css_first("[data-test='emp-location'], .location")

                title = _safe_text(title_el)
                company = _safe_text(company_el)
                location = _safe_text(location_el)

                href = _safe_attr(title_el, "href")
                if href and not href.startswith("http"):
                    href = f"https://www.glassdoor.com{href}"

                if title and href:
                    jobs.append(
                        {
                            "title": title,
                            "company": company or "Unknown",
                            "location": location or "United States",
                            "url": href,
                            "job_id": href.split("?")[0].split("-")[-1].replace(".htm", ""),
                            "date_posted": "",
                        }
                    )
            except Exception:
                continue
    except Exception as e:
        _log(f"Glassdoor parse error: {e}", "ERROR")
    return jobs


# Parser dispatch
PARSERS = {
    "parse_linkedin": parse_linkedin,
    "parse_indeed": parse_indeed,
    "parse_glassdoor": parse_glassdoor,
}


# ═══════════════════════════════════════════════════════════════════════
# MAIN SCRAPER
# ═══════════════════════════════════════════════════════════════════════


async def fetch_target(fetcher: Fetcher, target: dict) -> list[dict]:
    """Fetch and parse a single target's job listings."""
    all_jobs = []

    for url in target["urls"]:
        try:
            _log(f"[stealth] Fetching {target['name']}: {url[:80]}...")
            page = await asyncio.to_thread(fetcher.get, url, stealthy_headers=True)

            if page.status != 200:
                _log(f"[stealth] Got HTTP {page.status} from {target['name']}", "WARN")
                continue

            parser_fn = PARSERS[target["parser"]]
            jobs = parser_fn(page)
            _log(f"[stealth] Parsed {len(jobs)} jobs from {target['name']}")

            for j in jobs:
                j["source_ats"] = target["source_ats"]
            all_jobs.extend(jobs)

        except Exception as e:
            _log(f"[stealth] Failed to fetch {target['name']}: {e}", "ERROR")

    return all_jobs


async def run_stealth_scraper():
    """
    Micro-scraper for protected job boards using Scrapling stealth fetching.
    Replaces the broken OpenClaw CLI with direct HTTP + HTML parsing.
    """
    start_time = time.time()
    _log(">>> Starting Stealth Scraper (LinkedIn/Indeed/Glassdoor)")

    fetcher = create_fetcher()
    all_jobs = []
    errors = []

    for target in TARGETS:
        try:
            jobs = await fetch_target(fetcher, target)
            all_jobs.extend(jobs)
        except Exception as e:
            errors.append(f"{target['name']}: {str(e)}")
            _log(f"[stealth] Target failed: {target['name']}: {e}", "ERROR")

    _log(f"[stealth] Fetched {len(all_jobs)} total raw jobs from protected boards.")

    # ── Filtering ────────────────────────────────────────────────────
    role_filtered = [j for j in all_jobs if matches_target_role(j["title"])]
    _log(f"[stealth] Role filter: {len(role_filtered)}/{len(all_jobs)} matched target roles.")

    us_filtered = [j for j in role_filtered if is_us_location(j["location"])]
    _log(f"[stealth] US filter: {len(us_filtered)}/{len(role_filtered)} in United States.")

    # ── Database Insertion ───────────────────────────────────────────
    conn = get_connection()
    new_jobs_inserted = 0
    try:
        for job in us_filtered:
            if insert_job(conn, job):
                new_jobs_inserted += 1
    except Exception as e:
        _log(f"[stealth] DB insert error: {e}", "ERROR")
        errors.append(str(e))

    duration = round(time.time() - start_time, 2)
    err_str = "; ".join(errors) if errors else ""
    try:
        log_scraper_run(conn, "stealth_scraper", len(TARGETS), new_jobs_inserted, duration, err_str)
    finally:
        conn.close()

    _log(
        f">>> Stealth Scraper Complete. {new_jobs_inserted} new jobs from {len(us_filtered)} candidates. ({duration}s)"
    )
    return new_jobs_inserted


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_stealth_scraper())
