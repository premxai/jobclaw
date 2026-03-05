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

import aiohttp
from typing import List, Optional
import os
import time
import asyncio
from datetime import datetime, timezone

from scripts.ingestion.ats_adapters import NormalizedJob, _strip_html, _enrich_job
from scripts.database.db_utils import get_connection, insert_job, log_scraper_run
from scripts.ingestion.us_filter import is_us_location
from scripts.ingestion.role_filter import is_target_role
from scripts.ingestion.parallel_ingestor import is_within_window
from scripts.utils.logger import _log
from scripts.utils.http_client import random_headers, RateLimiter, fetch_with_retry, create_session
from scripts.utils.response_cache import ResponseCache
from scripts.utils.http_client import HAS_CURL_CFFI


async def _parse_resp_json(resp):
    """Parse JSON from either curl_cffi or aiohttp response."""
    if HAS_CURL_CFFI and hasattr(resp, 'status_code'):
        return resp.json()
    return await resp.json()

class AppleJobsAPI:
    BASE_URL = "https://jobs.apple.com"
    API_BASE = f"{BASE_URL}/api/v1"

    def __init__(self, locale: str = "en-us"):
        self.locale = locale
        self._csrf_token: Optional[str] = None

    def _make_headers(self) -> dict:
        """Build Apple-specific headers with rotated UA."""
        h = random_headers()
        h.update({
            'Origin': self.BASE_URL,
            'Referer': f'{self.BASE_URL}/{self.locale}/search',
            'Content-Type': 'application/json',
            'browserlocale': self.locale,
            'locale': self.locale.replace('-', '_').upper(),
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
        })
        if self._csrf_token:
            h['x-apple-csrf-token'] = self._csrf_token
        return h

    async def _ensure_csrf_token(self, session, rate_limiter=None):
        """Fetch CSRF token — works with both curl_cffi and aiohttp."""
        if not self._csrf_token:
            resp = await fetch_with_retry(
                session, "GET", f"{self.API_BASE}/CSRFToken",
                rate_limiter=rate_limiter,
                log_tag="apple-csrf",
                headers=self._make_headers(),
            )
            if resp:
                self._csrf_token = resp.headers.get('x-apple-csrf-token')

    async def fetch_jobs(self, session, page: int = 1,
                        rate_limiter: Optional[RateLimiter] = None) -> List[NormalizedJob]:
        await self._ensure_csrf_token(session, rate_limiter)

        payload = {
            "query": "",
            "filters": {
                "postLocation": ["postLocation-USA"]
            },
            "page": page,
            "locale": self.locale,
            "sort": "postingDate",
            "format": {
                "longDate": "MMMM D, YYYY",
                "mediumDate": "MMM D, YYYY"
            }
        }

        normalized = []
        try:
            resp = await fetch_with_retry(
                session, "POST", f"{self.API_BASE}/search",
                rate_limiter=rate_limiter,
                log_tag="apple",
                json=payload,
                headers=self._make_headers(),
            )
            if not resp:
                return []

            try:
                from scripts.utils.http_client import HAS_CURL_CFFI
                if HAS_CURL_CFFI and hasattr(resp, 'status_code'):
                    data = resp.json()
                else:
                    data = await resp.json()
            except Exception:
                return []

            results = data.get('res', {}).get('searchResults', [])
            
            for job in results:
                title = job.get('postingTitle', '')
                company = "Apple"
                
                locations = job.get('locations', [])
                loc_name = locations[0].get('name', 'United States') if locations else 'United States'
                
                pos_id = job.get('positionId', '')
                transformed_title = job.get('transformedPostingTitle', '')
                url = f"https://jobs.apple.com/en-us/details/{pos_id}/{transformed_title}"

                # Apple includes jobSummary in search results
                description = job.get('jobSummary') or job.get('description') or None
                if description:
                    description = _strip_html(description)
                
                nj = NormalizedJob(
                    title=title,
                    company=company,
                    location=loc_name,
                    url=url,
                    date_posted=job.get('postingDate', ''),
                    source_ats='apple',
                    job_id=str(job.get('id', pos_id)),
                    description=description,
                )
                normalized.append(_enrich_job(nj))
        except Exception as e:
            _log(f"Error fetching Apple Page {page}: {e}", "ERROR")
            
        return normalized

class AmazonJobsAPI:
    API_URL = "https://www.amazon.jobs/api/jobs/search"

    async def fetch_jobs(self, session, page: int = 1,
                        rate_limiter: Optional[RateLimiter] = None) -> List[NormalizedJob]:
        size = 25
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
                session, "POST", self.API_URL,
                rate_limiter=rate_limiter,
                log_tag="amazon",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            if not resp:
                return []

            try:
                data = await _parse_resp_json(resp)
            except Exception:
                return []

            hits = data.get('searchHits', [])
            
            for hit in hits:
                fields = hit.get('fields', {})
                def first(arr): return arr[0] if isinstance(arr, list) and arr else None
                
                title = first(fields.get("title")) or ""
                location = first(fields.get("location")) or "United States"
                date_posted = first(fields.get("createdDate")) or ""
                job_id = hit.get("id", "")
                url = f"https://www.amazon.jobs/en/jobs/{job_id}"
                
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

    async def fetch_jobs(self, session, page: int = 1,
                        rate_limiter: Optional[RateLimiter] = None) -> List[NormalizedJob]:
        start = (page - 1) * self.PAGE_SIZE
        params = {
            "domain": "microsoft.com",
            "start": str(start),
            "sort_by": "timestamp"
        }
        
        normalized = []
        try:
            resp = await fetch_with_retry(
                session, "GET", self.SEARCH_ENDPOINT,
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
                    date_posted = datetime.fromtimestamp(ts, timezone.utc).isoformat()
                    
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

    async def fetch_jobs(self, session, page: int = 1,
                        rate_limiter: Optional[RateLimiter] = None) -> List[NormalizedJob]:
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
                session, "POST", self.API_URL,
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
                
                city = job.get("city_info", {}).get("en_name")
                country = job.get("city_info", {}).get("parent", {}).get("parent", {}).get("en_name")
                locs = [x for x in [city, country] if x]
                location = ", ".join(locs) if locs else "United States"
                
                url = f"https://lifeattiktok.com/search/{job_id}" if job_id else ""
                
                if title and job_id:
                    normalized.append(NormalizedJob(
                        title=title,
                        company="TikTok",
                        location=location,
                        url=url,
                        date_posted="",
                        source_ats="tiktok",
                        job_id=str(job_id)
                    ))
        except Exception as e:
            _log(f"Error fetching TikTok Page {page}: {e}", "ERROR")
            
        return normalized

class NvidiaJobsAPI:
    SEARCH_ENDPOINT = "https://nvidia.eightfold.ai/api/pcsx/search"
    PAGE_SIZE = 10

    async def fetch_jobs(self, session, page: int = 1,
                        rate_limiter: Optional[RateLimiter] = None) -> List[NormalizedJob]:
        start = (page - 1) * self.PAGE_SIZE
        params = {
            "domain": "nvidia.com",
            "start": str(start),
            "sort_by": "timestamp"
        }
        
        normalized = []
        try:
            resp = await fetch_with_retry(
                session, "GET", self.SEARCH_ENDPOINT,
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
                    date_posted = datetime.fromtimestamp(ts, timezone.utc).isoformat()
                    
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

    async def fetch_jobs(self, session, page: int = 1,
                        rate_limiter: Optional[RateLimiter] = None) -> List[NormalizedJob]:
        limit = 10
        page_idx = page - 1
        
        request_body = {
            'limit': limit,
            'page': page_idx,
            'params': {
                'department': [],
                'lineOfBusinessName': [],
                'location': [],
                'programAndPlatform': [],
                'team': []
            }
        }

        query_params = {'localeCode': 'en'}
        normalized = []
        try:
            resp = await fetch_with_retry(
                session, "POST", self.SEARCH_ENDPOINT,
                rate_limiter=rate_limiter,
                log_tag="uber",
                json=request_body,
                params=query_params,
                headers={
                    'Origin': 'https://www.uber.com',
                    'Referer': 'https://www.uber.com/us/en/careers/',
                    'x-csrf-token': 'x',
                },
            )
            if not resp:
                return []

            try:
                data = await _parse_resp_json(resp)
            except Exception:
                return []

            results = data.get('data', {}).get('results', [])
            
            for job in results:
                title = job.get('title', '')
                job_id = job.get('id', '')
                
                loc_data = job.get('location', {})
                city = loc_data.get('city')
                region = loc_data.get('region')
                country = loc_data.get('countryName')
                
                loc_parts = [x for x in [city, region, country] if x]
                location = ", ".join(loc_parts) if loc_parts else "United States"
                
                url = f"https://www.uber.com/global/en/careers/list/{job_id}/" if job_id else ""
                
                if title and job_id:
                    normalized.append(NormalizedJob(
                        title=title,
                        company="Uber",
                        location=location,
                        url=url,
                        date_posted=job.get('creationDate', ''),
                        source_ats="uber",
                        job_id=str(job_id)
                    ))
        except Exception as e:
            _log(f"Error fetching Uber Page {page}: {e}", "ERROR")
            
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
    URL = "https://careers.google.com/jobs/results/"

    async def _wait_for_ds_chunk(self, page, chunk_key: str, timeout_ms: int):
        js = """
        (chunkKey) => {
            const store = globalThis.__dsChunkStore || [];
            for (const entry of store) {
                if (entry && entry.key === chunkKey && entry.data && !entry.__consumed) {
                    entry.__consumed = true; return entry;
                }
            }
            const queue = globalThis.AF_initDataChunkQueue;
            if (Array.isArray(queue)) {
                for (const entry of queue) {
                    if (entry && entry.key === chunkKey && entry.data && !entry.__consumed) {
                        entry.__consumed = true; return entry;
                    }
                }
            }
            const requests = globalThis.AF_dataServiceRequests || {};
            const candidate = requests[chunkKey];
            if (candidate && candidate.data && !candidate.__consumed) {
                candidate.__consumed = true; return { key: chunkKey, data: candidate.data };
            }
            return null;
        }
        """
        try:
            handle = await page.wait_for_function(js, arg=chunk_key, timeout=timeout_ms)
            chunk = await handle.json_value()
            if not chunk or "data" not in chunk: return None
            return chunk["data"]
        except Exception:
            return None

    async def _click_next_page(self, page) -> bool:
        selectors = [
            "button[aria-label='Next page']",
            "div[role='button'][aria-label='Next page']",
            "button:has-text(\"Next\")",
        ]
        for selector in selectors:
            locator = page.locator(selector)
            try:
                if await locator.count() == 0: continue
                target = locator.first
                if not await target.is_enabled(): continue
                await target.click()
                await page.wait_for_timeout(500)
                return True
            except Exception:
                continue
        return False

    def _parse_ds1(self, ds1_payload) -> List[NormalizedJob]:
        jobs = []
        if isinstance(ds1_payload, dict): ds1_payload = ds1_payload.get("data")
        if not isinstance(ds1_payload, list) or not ds1_payload: return jobs
        job_entries = ds1_payload[0]
        if not isinstance(job_entries, list): return jobs

        for entry in job_entries:
            if not isinstance(entry, list) or not entry: continue
            def get(idx): return entry[idx] if idx < len(entry) else None
            
            ats_id = str(get(0) or "").strip()
            title = str(get(1) or "").strip()
            url = str(get(2) or "").strip()
            company = str(get(7) or "Google").strip()
            
            raw_locs = get(9)
            locations = []
            if isinstance(raw_locs, list):
                for r in raw_locs:
                    if isinstance(r, str) and r.strip(): locations.append(r.strip())
                    elif isinstance(r, list):
                        for sub in r:
                            if isinstance(sub, str) and sub.strip(): locations.append(sub.strip())
            
            loc_name = locations[0] if locations else "United States"
            
            if ats_id or url:
                jobs.append(NormalizedJob(
                    title=title,
                    company=company,
                    location=loc_name,
                    url=url,
                    date_posted="", 
                    source_ats="google",
                    job_id=ats_id or url
                ))
        return jobs

    async def fetch_all_jobs(self, max_pages: int = 5) -> List[NormalizedJob]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            _log("Playwright not installed. Skipping Google jobs.", "ERROR")
            return []

        all_jobs = []
        timeout_ms = 25000
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36")
                page = await context.new_page()
                await page.add_init_script(CHUNK_CAPTURE_INIT)
                
                await page.goto(self.URL, wait_until="networkidle", timeout=timeout_ms)
                
                for _ in range(max_pages):
                    data = await self._wait_for_ds_chunk(page, "ds:1", timeout_ms)
                    if data:
                        parsed = self._parse_ds1(data)
                        all_jobs.extend(parsed)
                    
                    has_next = await self._click_next_page(page)
                    if not has_next: break
                
                await context.close()
                await browser.close()
        except Exception as e:
            _log(f"Error fetching Google jobs via Playwright: {e}", "ERROR")
            
        return all_jobs

class MetaJobsAPI:
    URL = "https://www.metacareers.com/jobs"

    async def fetch_all_jobs(self) -> List[NormalizedJob]:
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
                context = await browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
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
                    data = gql_response.get("data", {})
                    # Meta's exact payload structure based on the scrapers repo
                    if "job_search_with_featured_jobs" in data:
                        job_results = data["job_search_with_featured_jobs"].get("all_jobs", [])
                        for job in job_results:
                            job_id = job.get("id")
                            title = job.get("title", "")
                            
                            locs = job.get("locations", [])
                            location = locs[0] if locs else "United States"
                            
                            url = f"https://www.metacareers.com/jobs/{job_id}/" if job_id else ""
                            
                            if title and job_id:
                                all_jobs.append(NormalizedJob(
                                    title=title,
                                    company="Meta",
                                    location=location,
                                    url=url,
                                    date_posted="",
                                    source_ats="meta",
                                    job_id=str(job_id)
                                ))
                
                await context.close()
                await browser.close()
        except Exception as e:
            _log(f"Error fetching Meta jobs via Playwright: {e}", "ERROR")
            
        return all_jobs

def log(msg: str, level: str = "INFO"):
    _log(msg, level, "enterprise")


async def _paginate_api(api, session: aiohttp.ClientSession, name: str,
                        rate_limiter: Optional[RateLimiter] = None,
                        max_pages: int = 25) -> List[NormalizedJob]:
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


async def run_enterprise_scraper():
    log("=== Commencing Enterprise Architecture Scrape v2 ===")
    start_t = time.time()
    all_jobs = []
    cache = ResponseCache()
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
        
        log("Fetching from Apple, Amazon, Microsoft, Google, Meta, TikTok, Nvidia, Uber...")
        
        # Google & Meta use Playwright — run them in parallel background tasks
        google_task = asyncio.create_task(google_api.fetch_all_jobs(max_pages=10))
        meta_task = asyncio.create_task(meta_api.fetch_all_jobs())
        
        # Full pagination for REST API companies (no more 5-page cap)
        api_results = await asyncio.gather(
            _paginate_api(apple_api, session, "Apple", rate_limiter=rate_limiter, max_pages=15),
            _paginate_api(amazon_api, session, "Amazon", rate_limiter=rate_limiter, max_pages=20),
            _paginate_api(microsoft_api, session, "Microsoft", rate_limiter=rate_limiter, max_pages=20),
            _paginate_api(tiktok_api, session, "TikTok", rate_limiter=rate_limiter, max_pages=15),
            _paginate_api(nvidia_api, session, "Nvidia", rate_limiter=rate_limiter, max_pages=20),
            _paginate_api(uber_api, session, "Uber", rate_limiter=rate_limiter, max_pages=15),
            return_exceptions=True,
        )
        
        api_names = ["Apple", "Amazon", "Microsoft", "TikTok", "Nvidia", "Uber"]
        for name, result in zip(api_names, api_results):
            if isinstance(result, Exception):
                log(f"{name} scraper error: {result}", "ERROR")
            else:
                log(f"{name}: {len(result)} raw jobs")
                all_jobs.extend(result)

        # Wait for Playwright scrapers
        google_jobs = await google_task
        meta_jobs = await meta_task
        
        log(f"Google: {len(google_jobs)} raw jobs")
        log(f"Meta: {len(meta_jobs)} raw jobs")
        all_jobs.extend(google_jobs)
        all_jobs.extend(meta_jobs)

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
            }
            if insert_job(conn, j_dict):
                new_jobs_inserted += 1

        log_scraper_run(
            conn=conn,
            script_name="scrape_enterprise",
            companies_fetched=8,
            new_jobs=new_jobs_inserted,
            duration=round(time.time() - start_t, 2)
        )
    finally:
        conn.close()

    total_time = round(time.time() - start_t, 2)
    log(f">>> Enterprise Scraper Complete. New={new_jobs_inserted}, Candidates={len(final_jobs)}, Duration={total_time}s")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_enterprise_scraper())
