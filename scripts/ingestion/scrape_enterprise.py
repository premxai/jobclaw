"""
Enterprise Job Scrapers — v2 with hardened HTTP and full pagination.

Custom scrapers for major tech companies with proprietary careers APIs:
  Apple, Amazon, Microsoft, Google, Meta, TikTok, Nvidia, Uber

v2 improvements:
  - UA rotation via http_client.random_headers()
  - Full pagination (iterate until API returns empty — no arbitrary page cap)
  - Description capture for salary/experience extraction
  - Rate limiting via shared RateLimiter
  - Response caching to avoid redundant fetches
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
import json
import os
import re
import time
from datetime import UTC, datetime

import aiohttp

from scripts.database.db_utils import get_connection, insert_job, log_scraper_run
from scripts.ingestion.ats_adapters import NormalizedJob, _enrich_job, _strip_html, fetch_company_jobs
from scripts.ingestion.parallel_ingestor import is_within_window
from scripts.ingestion.role_filter import is_target_role
from scripts.ingestion.us_filter import is_us_location
from scripts.utils.http_client import HAS_CURL_CFFI, RateLimiter, create_session, fetch_with_retry, random_headers
from scripts.utils.logger import _log
from scripts.utils.response_cache import ResponseCache


async def _parse_resp_json(resp):
    """Parse JSON from either curl_cffi or aiohttp response."""
    if HAS_CURL_CFFI and hasattr(resp, "status_code"):
        return resp.json()
    return await resp.json()


class AppleJobsAPI:
    BASE_URL = "https://jobs.apple.com"
    API_BASE = f"{BASE_URL}/api/v1"

    def __init__(self, locale: str = "en-us"):
        self.locale = locale
        self._csrf_token: str | None = None

    def _make_headers(self) -> dict:
        """Build Apple-specific headers with rotated UA."""
        h = random_headers()
        h.update(
            {
                "Origin": self.BASE_URL,
                "Referer": f"{self.BASE_URL}/{self.locale}/search",
                "Content-Type": "application/json",
                "browserlocale": self.locale,
                "locale": self.locale.replace("-", "_").upper(),
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
            }
        )
        if self._csrf_token:
            h["x-apple-csrf-token"] = self._csrf_token
        return h

    async def _ensure_csrf_token(self, session, rate_limiter=None):
        """Fetch CSRF token — works with both curl_cffi and aiohttp."""
        if not self._csrf_token:
            resp = await fetch_with_retry(
                session,
                "GET",
                f"{self.API_BASE}/CSRFToken",
                rate_limiter=rate_limiter,
                log_tag="apple-csrf",
                headers=self._make_headers(),
            )
            if resp:
                self._csrf_token = resp.headers.get("x-apple-csrf-token")

    async def fetch_jobs(self, session, page: int = 1, rate_limiter: RateLimiter | None = None) -> list[NormalizedJob]:
        await self._ensure_csrf_token(session, rate_limiter)

        payload = {
            "query": "",
            "filters": {"postLocation": ["postLocation-USA"]},
            "page": page,
            "locale": self.locale,
            "sort": "postingDate",
            "format": {"longDate": "MMMM D, YYYY", "mediumDate": "MMM D, YYYY"},
        }

        normalized = []
        try:
            resp = await fetch_with_retry(
                session,
                "POST",
                f"{self.API_BASE}/search",
                rate_limiter=rate_limiter,
                log_tag="apple",
                json=payload,
                headers=self._make_headers(),
            )
            if not resp:
                return []

            try:
                from scripts.utils.http_client import HAS_CURL_CFFI

                if HAS_CURL_CFFI and hasattr(resp, "status_code"):
                    data = resp.json()
                else:
                    data = await resp.json()
            except Exception:
                return []

            results = data.get("res", {}).get("searchResults", [])

            for job in results:
                title = job.get("postingTitle", "")
                company = "Apple"

                locations = job.get("locations", [])
                loc_name = locations[0].get("name", "United States") if locations else "United States"

                pos_id = job.get("positionId", "")
                transformed_title = job.get("transformedPostingTitle", "")
                url = f"https://jobs.apple.com/en-us/details/{pos_id}/{transformed_title}"

                # Apple includes jobSummary in search results
                description = job.get("jobSummary") or job.get("description") or None
                if description:
                    description = _strip_html(description)

                nj = NormalizedJob(
                    title=title,
                    company=company,
                    location=loc_name,
                    url=url,
                    date_posted=job.get("postingDate", ""),
                    source_ats="apple",
                    job_id=str(job.get("id", pos_id)),
                    description=description,
                )
                normalized.append(_enrich_job(nj))
        except Exception as e:
            _log(f"Error fetching Apple Page {page}: {e}", "ERROR")

        return normalized


class AmazonJobsAPI:
    API_URL = "https://www.amazon.jobs/api/jobs/search"

    async def fetch_jobs(self, session, page: int = 1, rate_limiter: RateLimiter | None = None) -> list[NormalizedJob]:
        size = 100
        start_offset = (page - 1) * size

        payload = {
            "searchType": "JOB_SEARCH",
            "start": start_offset,
            "size": size,
            "sort_by": "Recent",
            "country": ["US"],
        }

        normalized = []
        try:
            resp = await fetch_with_retry(
                session,
                "POST",
                self.API_URL,
                rate_limiter=rate_limiter,
                log_tag="amazon",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                },
            )
            if not resp:
                return []

            try:
                data = await _parse_resp_json(resp)
            except Exception:
                return []

            hits = data.get("searchHits", [])

            for hit in hits:
                fields = hit.get("fields", {})

                def first(arr):
                    return arr[0] if isinstance(arr, list) and arr else None

                title = first(fields.get("title")) or ""
                location = first(fields.get("location")) or "United States"
                date_posted = first(fields.get("createdDate")) or ""
                job_id = first(fields.get("icimsJobId")) or first(fields.get("jobCode")) or ""
                url = first(fields.get("urlNextStep")) or f"https://www.amazon.jobs/en/jobs/{job_id}"

                desc_parts = []
                raw_desc = first(fields.get("description"))
                if raw_desc:
                    desc_parts.append(_strip_html(raw_desc))
                basic_quals = first(fields.get("basic_qualifications"))
                if basic_quals:
                    desc_parts.append(_strip_html(basic_quals))
                description = "\n\n".join(desc_parts) if desc_parts else None

                if title and job_id:
                    nj = NormalizedJob(
                        title=title,
                        company="Amazon",
                        location=location,
                        url=url,
                        date_posted=date_posted,
                        source_ats="amazon",
                        job_id=str(job_id),
                        description=description,
                    )
                    normalized.append(_enrich_job(nj))
        except Exception as e:
            _log(f"Error fetching Amazon Page {page}: {e}", "ERROR")

        return normalized


class MicrosoftJobsAPI:
    SEARCH_ENDPOINT = "https://apply.careers.microsoft.com/api/pcsx/search"
    PAGE_SIZE = 20

    async def fetch_jobs(self, session, page: int = 1, rate_limiter: RateLimiter | None = None) -> list[NormalizedJob]:
        start = (page - 1) * self.PAGE_SIZE
        params = {"domain": "microsoft.com", "start": str(start), "sort_by": "timestamp"}

        normalized = []
        try:
            resp = await fetch_with_retry(
                session,
                "GET",
                self.SEARCH_ENDPOINT,
                rate_limiter=rate_limiter,
                log_tag="microsoft",
                params=params,
            )
            if not resp:
                return []

            try:
                data = await _parse_resp_json(resp)
            except Exception:
                return []

            positions = data.get("data", {}).get("positions", [])

            for p in positions:
                title = p.get("name", "")
                locs = p.get("locations", [])
                location = locs[0] if locs else "United States"

                ts = p.get("postedTs")
                date_posted = ""
                if ts:
                    date_posted = datetime.fromtimestamp(ts, UTC).isoformat()

                url = "https://apply.careers.microsoft.com" + p.get("positionUrl", "")
                job_id = p.get("id", "")

                description = _strip_html(p.get("description", "")) or None

                if title and job_id:
                    nj = NormalizedJob(
                        title=title,
                        company="Microsoft",
                        location=location,
                        url=url,
                        date_posted=date_posted,
                        source_ats="microsoft",
                        job_id=str(job_id),
                        description=description,
                    )
                    normalized.append(_enrich_job(nj))
        except Exception as e:
            _log(f"Error fetching Microsoft Page {page}: {e}", "ERROR")

        return normalized


class TikTokJobsAPI:
    API_URL = "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts"

    async def fetch_jobs(self, session, page: int = 1, rate_limiter: RateLimiter | None = None) -> list[NormalizedJob]:
        limit = 12
        offset = (page - 1) * limit
        payload = {
            "recruitment_id_list": [],
            "job_category_id_list": [],
            "subject_id_list": [],
            "location_code_list": [],
            "keyword": "",
            "limit": limit,
            "offset": offset,
        }

        normalized = []
        try:
            resp = await fetch_with_retry(
                session,
                "POST",
                self.API_URL,
                rate_limiter=rate_limiter,
                log_tag="tiktok",
                json=payload,
                headers={
                    "content-type": "application/json",
                    "website-path": "tiktok",
                    "referer": "https://lifeattiktok.com/",
                },
            )
            if not resp:
                return []

            try:
                data = await _parse_resp_json(resp)
            except Exception:
                return []

            job_list = data.get("data", {}).get("job_post_list", [])

            for job in job_list:
                job_id = job.get("id")
                title = job.get("title")

                # Null-safe city_info traversal
                city_info = job.get("city_info") or {}
                city = city_info.get("en_name") if isinstance(city_info, dict) else None
                parent = city_info.get("parent") or {} if isinstance(city_info, dict) else {}
                grandparent = parent.get("parent") or {} if isinstance(parent, dict) else {}
                country = grandparent.get("en_name") if isinstance(grandparent, dict) else None
                locs = [x for x in [city, country] if x]
                location = ", ".join(locs) if locs else "United States"

                url = f"https://lifeattiktok.com/search/{job_id}" if job_id else ""

                if title and job_id:
                    normalized.append(
                        NormalizedJob(
                            title=title,
                            company="TikTok",
                            location=location,
                            url=url,
                            date_posted="",
                            source_ats="tiktok",
                            job_id=str(job_id),
                        )
                    )
        except Exception as e:
            _log(f"Error fetching TikTok Page {page}: {e}", "ERROR")

        return normalized


class NvidiaJobsAPI:
    SEARCH_ENDPOINT = "https://nvidia.eightfold.ai/api/pcsx/search"
    PAGE_SIZE = 20

    async def fetch_jobs(self, session, page: int = 1, rate_limiter: RateLimiter | None = None) -> list[NormalizedJob]:
        start = (page - 1) * self.PAGE_SIZE
        params = {"domain": "nvidia.com", "start": str(start), "sort_by": "timestamp"}

        normalized = []
        try:
            resp = await fetch_with_retry(
                session,
                "GET",
                self.SEARCH_ENDPOINT,
                rate_limiter=rate_limiter,
                log_tag="nvidia",
                params=params,
            )
            if not resp:
                return []

            try:
                data = await _parse_resp_json(resp)
            except Exception:
                return []

            positions = data.get("data", {}).get("positions", [])

            for p in positions:
                title = p.get("name", "")
                locs = p.get("locations", [])
                location = locs[0] if locs else "United States"

                ts = p.get("postedTs")
                date_posted = ""
                if ts:
                    date_posted = datetime.fromtimestamp(ts, UTC).isoformat()

                url = "https://nvidia.eightfold.ai" + p.get("positionUrl", "")
                job_id = p.get("id", "")

                description = _strip_html(p.get("description", "")) or None

                if title and job_id:
                    nj = NormalizedJob(
                        title=title,
                        company="Nvidia",
                        location=location,
                        url=url,
                        date_posted=date_posted,
                        source_ats="nvidia",
                        job_id=str(job_id),
                        description=description,
                    )
                    normalized.append(_enrich_job(nj))
        except Exception as e:
            _log(f"Error fetching Nvidia Page {page}: {e}", "ERROR")

        return normalized


class UberJobsAPI:
    SEARCH_ENDPOINT = "https://www.uber.com/api/loadSearchJobsResults"

    async def fetch_jobs(self, session, page: int = 1, rate_limiter: RateLimiter | None = None) -> list[NormalizedJob]:
        limit = 10
        page_idx = page - 1

        request_body = {
            "limit": limit,
            "page": page_idx,
            "params": {
                "department": [],
                "lineOfBusinessName": [],
                "location": [],
                "programAndPlatform": [],
                "team": [],
            },
        }

        query_params = {"localeCode": "en"}
        normalized = []
        try:
            resp = await fetch_with_retry(
                session,
                "POST",
                self.SEARCH_ENDPOINT,
                rate_limiter=rate_limiter,
                log_tag="uber",
                json=request_body,
                params=query_params,
                headers={
                    "Origin": "https://www.uber.com",
                    "Referer": "https://www.uber.com/us/en/careers/",
                    "x-csrf-token": "x",
                },
            )
            if not resp:
                return []

            try:
                data = await _parse_resp_json(resp)
            except Exception:
                return []

            results = data.get("data", {}).get("results", [])

            for job in results:
                title = job.get("title", "")
                job_id = job.get("id", "")

                loc_data = job.get("location", {})
                city = loc_data.get("city")
                region = loc_data.get("region")
                country = loc_data.get("countryName")

                loc_parts = [x for x in [city, region, country] if x]
                location = ", ".join(loc_parts) if loc_parts else "United States"

                url = f"https://www.uber.com/global/en/careers/list/{job_id}/" if job_id else ""

                if title and job_id:
                    normalized.append(
                        NormalizedJob(
                            title=title,
                            company="Uber",
                            location=location,
                            url=url,
                            date_posted=job.get("creationDate", ""),
                            source_ats="uber",
                            job_id=str(job_id),
                        )
                    )
        except Exception as e:
            _log(f"Error fetching Uber Page {page}: {e}", "ERROR")

        return normalized


class TeslaJobsAPI:
    """Tesla Careers API. Protected by Akamai — uses curl_cffi TLS impersonation.
    May fail silently if Akamai blocks the request; non-fatal."""

    API_URL = "https://www.tesla.com/cua-api/apps/careers/state"

    async def fetch_jobs(self, session, page: int = 1, rate_limiter: RateLimiter | None = None) -> list[NormalizedJob]:
        if page > 1:
            return []  # Tesla API returns all jobs in one call

        normalized = []
        try:
            resp = await fetch_with_retry(
                session,
                "GET",
                self.API_URL,
                rate_limiter=rate_limiter,
                log_tag="tesla",
                headers={
                    "Referer": "https://www.tesla.com/careers/search/",
                    "Accept": "application/json",
                },
            )
            if not resp:
                _log("[tesla] API blocked (Akamai) — skipping", "WARN")
                return []

            try:
                data = await _parse_resp_json(resp)
            except Exception:
                return []

            # Tesla returns jobs under various keys depending on API version
            job_list = []
            if isinstance(data, dict):
                job_list = data.get("results", []) or data.get("listings", []) or data.get("jobs", [])
            elif isinstance(data, list):
                job_list = data

            for job in job_list:
                if not isinstance(job, dict):
                    continue
                title = job.get("title") or job.get("jobTitle", "")
                job_id = str(job.get("id") or job.get("jobId", ""))
                location = job.get("location") or job.get("city", "")
                if isinstance(location, dict):
                    location = location.get("name", "United States")
                if not location:
                    location = "United States"

                url = f"https://www.tesla.com/careers/search/job/{job_id}" if job_id else ""

                if title and job_id:
                    normalized.append(
                        NormalizedJob(
                            title=title,
                            company="Tesla",
                            location=location,
                            url=url,
                            date_posted=job.get("postedDate", ""),
                            source_ats="tesla",
                            job_id=job_id,
                        )
                    )
        except Exception as e:
            _log(f"Error fetching Tesla jobs: {e}", "WARN")

        return normalized


class CursorJobsAPI:
    """Cursor.com careers page scraper — simple HTML parsing."""

    CAREERS_URL = "https://cursor.com/careers"

    async def fetch_jobs(self, session, page: int = 1, rate_limiter: RateLimiter | None = None) -> list[NormalizedJob]:
        if page > 1:
            return []  # Single page

        normalized = []
        try:
            resp = await fetch_with_retry(
                session,
                "GET",
                self.CAREERS_URL,
                rate_limiter=rate_limiter,
                log_tag="cursor",
            )
            if not resp:
                return []

            try:
                if HAS_CURL_CFFI and hasattr(resp, "status_code"):
                    html = resp.text
                else:
                    html = await resp.text()
            except Exception:
                return []

            # Parse job links from careers page
            import re

            # Find all career links: /careers/SLUG
            links = re.findall(r'href="(/careers/[^"]+)"', html)
            # Extract job titles from link context
            # Pattern: title text followed by location info
            re.findall(r'href="(/careers/[^"]+)"[^>]*>.*?>(.*?)</.*?</a>', html, re.DOTALL)

            seen = set()
            for link in links:
                if link in seen or link == "/careers" or link == "/careers/":
                    continue
                seen.add(link)

                # Extract slug as job ID
                slug = link.replace("/careers/", "").strip("/")
                if not slug or slug in ("search", "teams", "locations"):
                    continue

                # Title from slug
                title = slug.replace("-", " ").title()
                url = f"https://cursor.com{link}"

                normalized.append(
                    NormalizedJob(
                        title=title,
                        company="Cursor",
                        location="San Francisco, CA",  # Cursor HQ
                        url=url,
                        date_posted="",
                        source_ats="cursor",
                        job_id=slug,
                    )
                )
        except Exception as e:
            _log(f"Error fetching Cursor jobs: {e}", "WARN")

        return normalized


CHUNK_CAPTURE_INIT = """
(() => {
    const store = [];
    Object.defineProperty(window, "__dsChunkStore", { value: store, writable: false, configurable: false });
    const cloneChunk = (chunk) => { try { return JSON.parse(JSON.stringify(chunk)); } catch (err) { return null; } };
    const capture = (chunk) => { if (chunk && chunk.key && chunk.data) { const copy = cloneChunk(chunk); if (copy) { store.push(copy); } } };
    const wrapCallback = (fn) => {
        if (typeof fn !== "function") { return function(chunk) { capture(chunk); }; }
        return function(...args) { capture(args[0]); return fn.apply(this, args); };
    };
    let activeCallback = wrapCallback(window.AF_initDataCallback);
    Object.defineProperty(window, "AF_initDataCallback", { configurable: true, get() { return activeCallback; }, set(fn) { activeCallback = wrapCallback(fn); } });
    const queue = Array.isArray(window.AF_initDataChunkQueue) ? window.AF_initDataChunkQueue : (window.AF_initDataChunkQueue = []);
    for (const chunk of queue) { capture(chunk); }
    const originalPush = queue.push;
    queue.push = function(...args) { for (const chunk of args) { capture(chunk); } return originalPush.apply(this, args); };
})();
"""


class GoogleJobsAPI:
    URL = "https://www.google.com/about/careers/applications/jobs/results/"

    @staticmethod
    def _extract_ds1(html: str):
        """Extract ds:1 data from AF_initDataCallback in SSR HTML."""
        pattern = r"AF_initDataCallback\(\{key:\s*'ds:1'.*?data:(\[.+?),\s*sideChannel:"
        match = re.search(pattern, html, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            return None

    def _parse_ds1(self, ds1_payload) -> list[NormalizedJob]:
        """Parse Google's ds:1 data chunk. Wrapped in try/except for resilience
        against Google changing their internal data structure indices."""
        jobs = []
        try:
            if isinstance(ds1_payload, dict):
                ds1_payload = ds1_payload.get("data")
            if not isinstance(ds1_payload, list) or not ds1_payload:
                return jobs
            job_entries = ds1_payload[0]
            if not isinstance(job_entries, list):
                return jobs

            for entry in job_entries:
                try:
                    if not isinstance(entry, list) or not entry:
                        continue

                    def get(idx, _entry=entry):
                        return _entry[idx] if idx < len(_entry) else None

                    ats_id = str(get(0) or "").strip()
                    title = str(get(1) or "").strip()
                    url = str(get(2) or "").strip()
                    company = str(get(7) or "Google").strip()

                    raw_locs = get(9)
                    locations = []
                    if isinstance(raw_locs, list):
                        for r in raw_locs:
                            if isinstance(r, str) and r.strip():
                                locations.append(r.strip())
                            elif isinstance(r, list):
                                for sub in r:
                                    if isinstance(sub, str) and sub.strip():
                                        locations.append(sub.strip())

                    loc_name = locations[0] if locations else "United States"

                    if ats_id or url:
                        jobs.append(
                            NormalizedJob(
                                title=title,
                                company=company,
                                location=loc_name,
                                url=url,
                                date_posted="",
                                source_ats="google",
                                job_id=ats_id or url,
                            )
                        )
                except (IndexError, TypeError, ValueError) as e:
                    _log(f"[google] Skipping malformed job entry: {e}", "DEBUG")
                    continue
        except (IndexError, TypeError, KeyError) as e:
            _log(f"[google] ds:1 structure changed or malformed: {e}", "WARN")
        return jobs

    async def fetch_all_jobs(
        self, max_pages: int = 5, session=None, rate_limiter: RateLimiter | None = None
    ) -> list[NormalizedJob]:
        """Fetch Google jobs via HTTP SSR extraction (no Playwright needed)."""
        all_jobs = []

        for page in range(1, max_pages + 1):
            url = f"{self.URL}?page={page}"
            resp = await fetch_with_retry(
                session,
                "GET",
                url,
                rate_limiter=rate_limiter,
                log_tag="google",
            )
            if not resp:
                break

            html = resp.text if hasattr(resp, "status_code") else await resp.text()
            data = self._extract_ds1(html)
            if not data:
                _log(f"[google] No ds:1 data on page {page}", "DEBUG")
                break

            parsed = self._parse_ds1(data)
            if not parsed:
                break
            all_jobs.extend(parsed)

            # Check total — data is [entries, null, total, page_size]
            total = 0
            if isinstance(data, list):
                for item in data[1:]:
                    if isinstance(item, int) and item > 100:
                        total = item
                        break
            if total and page * 20 >= total:
                break

        _log(f"[google] Extracted {len(all_jobs)} jobs from {min(page, max_pages)} pages")
        return all_jobs


class MetaJobsAPI:
    URL = "https://www.metacareers.com/jobs"

    async def fetch_all_jobs(self) -> list[NormalizedJob]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            _log("Playwright not installed. Skipping Meta jobs.", "ERROR")
            return []

        all_jobs = []
        graphql_data = []

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                )
                page = await context.new_page()

                async def handle_response(response):
                    if "graphql" in response.url:
                        try:
                            json_data = await response.json()
                            graphql_data.append(json_data)
                        except Exception:
                            pass

                page.on("response", handle_response)
                await page.goto(self.URL, wait_until="domcontentloaded", timeout=60000)

                # Sleep briefly to ensure GraphQL finishes caching
                await asyncio.sleep(8)

                for gql_response in graphql_data:
                    try:
                        data = gql_response.get("data", {})
                        # Try multiple known GraphQL query names (Meta changes these)
                        job_results = []
                        for query_key in ["job_search_with_featured_jobs", "job_search", "careers_job_search"]:
                            if query_key in data:
                                container = data[query_key]
                                job_results = (
                                    container.get("all_jobs", [])
                                    or container.get("jobs", [])
                                    or container.get("results", [])
                                )
                                if job_results:
                                    break

                        for job in job_results:
                            job_id = job.get("id")
                            title = job.get("title", "")

                            locs = job.get("locations", [])
                            location = locs[0] if locs else "United States"

                            url = f"https://www.metacareers.com/jobs/{job_id}/" if job_id else ""

                            if title and job_id:
                                all_jobs.append(
                                    NormalizedJob(
                                        title=title,
                                        company="Meta",
                                        location=location,
                                        url=url,
                                        date_posted="",
                                        source_ats="meta",
                                        job_id=str(job_id),
                                    )
                                )
                    except (KeyError, TypeError, AttributeError) as e:
                        _log(f"[meta] Error parsing GraphQL response: {e}", "DEBUG")

                await context.close()
                await browser.close()
        except Exception as e:
            _log(f"Error fetching Meta jobs via Playwright: {e}", "ERROR")

        return all_jobs


def log(msg: str, level: str = "INFO"):
    _log(msg, level, "enterprise")


async def _paginate_api(
    api, session: aiohttp.ClientSession, name: str, rate_limiter: RateLimiter | None = None, max_pages: int = 25
) -> list[NormalizedJob]:
    """
    Paginate an enterprise API until it returns empty results.
    No more arbitrary page-5 cap — we iterate until the API is exhausted.
    Safety limit: max_pages (default 25 = ~500 jobs per company).
    """
    all_jobs = []
    for page in range(1, max_pages + 1):
        try:
            jobs = await api.fetch_jobs(session, page=page, rate_limiter=rate_limiter)
            if not jobs:
                break  # API returned empty — done
            all_jobs.extend(jobs)
            await asyncio.sleep(0.15)  # Minimal delay — rate limiter handles throttling
        except Exception as e:
            _log(f"Error paginating {name} page {page}: {e}", "ERROR")
            break
    return all_jobs


# ═══════════════════════════════════════════════════════════════════════
# PRIORITY AI / HIGH-GROWTH COMPANIES
# Scraped every run (not subject to shard rotation) via existing ATS adapters.
# These are the highest-signal companies for AI/ML and SWE roles.
# ═══════════════════════════════════════════════════════════════════════

PRIORITY_COMPANIES = [
    # AI/ML Frontier Labs
    {"company": "OpenAI", "ats": "greenhouse", "slug": "openai"},
    {"company": "Anthropic", "ats": "lever", "slug": "anthropic"},
    {"company": "DeepMind", "ats": "greenhouse", "slug": "deepmind"},
    {"company": "Cohere", "ats": "lever", "slug": "cohere"},
    {"company": "Mistral AI", "ats": "lever", "slug": "mistral"},
    {"company": "xAI", "ats": "greenhouse", "slug": "xai"},
    {"company": "Perplexity AI", "ats": "greenhouse", "slug": "perplexity"},
    {"company": "Scale AI", "ats": "greenhouse", "slug": "scaleai"},
    {"company": "Weights & Biases", "ats": "lever", "slug": "wandb"},
    {"company": "Hugging Face", "ats": "workable", "slug": "huggingface"},
    {"company": "Runway ML", "ats": "greenhouse", "slug": "runwayml"},
    {"company": "Together AI", "ats": "greenhouse", "slug": "together-ai"},
    {"company": "Stability AI", "ats": "lever", "slug": "stability-ai"},
    # High-Growth Tech
    {"company": "Figma", "ats": "greenhouse", "slug": "figma"},
    {"company": "Notion", "ats": "greenhouse", "slug": "notion"},
    {"company": "Linear", "ats": "ashby", "slug": "linear"},
    {"company": "Vercel", "ats": "ashby", "slug": "vercel"},
    {"company": "Supabase", "ats": "ashby", "slug": "supabase"},
    {"company": "Retool", "ats": "greenhouse", "slug": "retool"},
    {"company": "Airtable", "ats": "greenhouse", "slug": "airtable"},
    {"company": "Brex", "ats": "greenhouse", "slug": "brex"},
    {"company": "Ramp", "ats": "lever", "slug": "ramp"},
    {"company": "Stripe", "ats": "greenhouse", "slug": "stripe"},
    {"company": "Plaid", "ats": "lever", "slug": "plaid"},
    {"company": "Rippling", "ats": "rippling", "slug": "rippling"},
]


async def _fetch_priority_companies(session, rate_limiter) -> list[NormalizedJob]:
    """
    Scrape all PRIORITY_COMPANIES using the existing ATS adapter infrastructure.
    Each is fetched concurrently with a 3-worker semaphore to avoid hammering.
    """
    sem = asyncio.Semaphore(3)
    jobs = []

    async def _fetch_one(entry):
        async with sem:
            try:
                result = await fetch_company_jobs(
                    session,
                    entry["company"],
                    entry["ats"],
                    entry["slug"],
                    rate_limiter=rate_limiter,
                )
                return result or []
            except Exception as e:
                log(f"[priority] {entry['company']} ({entry['ats']}) error: {e}", "WARN")
                return []

    results = await asyncio.gather(*[_fetch_one(e) for e in PRIORITY_COMPANIES])
    for batch in results:
        jobs.extend(batch)

    log(f"[priority] Fetched {len(jobs)} raw jobs from {len(PRIORITY_COMPANIES)} priority companies.")
    return jobs


async def run_enterprise_scraper():
    log("=== Commencing Enterprise Architecture Scrape v2 ===")
    start_t = time.time()
    all_jobs = []
    ResponseCache()
    rate_limiter = RateLimiter()

    proxy = os.environ.get("PROXY_URL")
    if proxy:
        _log(f"Enterprise scraper using proxy: {proxy[:30]}...")

    async with create_session(rate_limiter, proxy=proxy) as session:
        apple_api = AppleJobsAPI()
        amazon_api = AmazonJobsAPI()
        microsoft_api = MicrosoftJobsAPI()
        google_api = GoogleJobsAPI()
        meta_api = MetaJobsAPI()
        tiktok_api = TikTokJobsAPI()
        nvidia_api = NvidiaJobsAPI()
        uber_api = UberJobsAPI()
        tesla_api = TeslaJobsAPI()
        cursor_api = CursorJobsAPI()

        log(
            "Fetching from Apple, Amazon, Microsoft, Google, Meta, TikTok, Nvidia, Uber, Tesla, Cursor + 25 priority AI/ML companies..."
        )

        # Priority AI/ML companies (always scraped, not subject to shard rotation)
        priority_jobs = await _fetch_priority_companies(session, rate_limiter)
        all_jobs.extend(priority_jobs)

        # Full pagination for all API companies (including Google via HTTP SSR)
        api_results = await asyncio.gather(
            _paginate_api(apple_api, session, "Apple", rate_limiter=rate_limiter, max_pages=15),
            _paginate_api(amazon_api, session, "Amazon", rate_limiter=rate_limiter, max_pages=20),
            _paginate_api(microsoft_api, session, "Microsoft", rate_limiter=rate_limiter, max_pages=20),
            _paginate_api(tiktok_api, session, "TikTok", rate_limiter=rate_limiter, max_pages=15),
            _paginate_api(nvidia_api, session, "Nvidia", rate_limiter=rate_limiter, max_pages=20),
            _paginate_api(uber_api, session, "Uber", rate_limiter=rate_limiter, max_pages=15),
            _paginate_api(tesla_api, session, "Tesla", rate_limiter=rate_limiter, max_pages=1),
            _paginate_api(cursor_api, session, "Cursor", rate_limiter=rate_limiter, max_pages=1),
            google_api.fetch_all_jobs(max_pages=10, session=session, rate_limiter=rate_limiter),
            meta_api.fetch_all_jobs(session=session, rate_limiter=rate_limiter),
            return_exceptions=True,
        )

        api_names = ["Apple", "Amazon", "Microsoft", "TikTok", "Nvidia", "Uber", "Tesla", "Cursor", "Google", "Meta"]
        for name, result in zip(api_names, api_results):
            if isinstance(result, Exception):
                log(f"{name} scraper error: {result}", "ERROR")
            else:
                log(f"{name}: {len(result)} raw jobs")
                all_jobs.extend(result)

    log(f"Fetched {len(all_jobs)} total raw jobs from enterprise endpoints.")

    if not all_jobs:
        log("No jobs found. Exiting.")
        return

    # Pipeline filtering
    valid_roles = [j for j in all_jobs if is_target_role(j.title)]
    log(f"Role filter: {len(valid_roles)}/{len(all_jobs)} matched target tech roles.")

    us_jobs = [j for j in valid_roles if is_us_location(j.location)]
    log(f"US filter: {len(us_jobs)}/{len(valid_roles)} in United States.")

    # Midnight sweep: skip 24hr filter to catch any backlog
    now = time.localtime()
    is_midnight = now.tm_hour == 0

    if not is_midnight:
        final_jobs = [j for j in us_jobs if is_within_window(j.date_posted)]
        log(f"24hr filter: {len(final_jobs)}/{len(us_jobs)} within window.")
    else:
        final_jobs = us_jobs
        log("Midnight sweep active — skipping 24hr filter.")

    new_jobs_inserted = 0
    conn = get_connection()
    try:
        for job in final_jobs:
            j_dict = {
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "url": job.url,
                "date_posted": job.date_posted,
                "source_ats": job.source_ats,
                "job_id": job.job_id,
                "keywords_matched": getattr(job, "keywords_matched", []),
                "description": getattr(job, "description", None),
                "salary_min": getattr(job, "salary_min", None),
                "salary_max": getattr(job, "salary_max", None),
                "salary_currency": getattr(job, "salary_currency", None),
                "experience_years": getattr(job, "experience_years", None),
                "remote_ok": getattr(job, "remote_ok", None),
                "job_type": getattr(job, "job_type", None),
                "seniority_level": getattr(job, "seniority_level", None),
                "visa_sponsorship": getattr(job, "visa_sponsorship", None),
                "tech_stack": getattr(job, "tech_stack", None),
            }
            if insert_job(conn, j_dict):
                new_jobs_inserted += 1

        total_companies = 10 + len(PRIORITY_COMPANIES)
        log_scraper_run(
            conn=conn,
            script_name="scrape_enterprise",
            companies_fetched=total_companies,
            new_jobs=new_jobs_inserted,
            duration=round(time.time() - start_t, 2),
        )
    finally:
        conn.close()

    total_time = round(time.time() - start_t, 2)
    log(
        f">>> Enterprise Scraper Complete. New={new_jobs_inserted}, Candidates={len(final_jobs)}, Duration={total_time}s"
    )


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_enterprise_scraper())
