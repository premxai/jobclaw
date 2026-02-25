# Apple Jobs API Client
# Provides a direct integration with Apple's internal career site API.
# Handles CSRF token negotiation and subsequent REST search payloads.
import sys
from pathlib import Path

# Path fixing so we can import internal modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import aiohttp
from typing import List, Optional
import os
import time
import asyncio
import logging
from datetime import datetime, timezone

from scripts.ingestion.ats_adapters import NormalizedJob
from scripts.database.db_utils import get_connection, insert_job, log_scraper_run
from scripts.ingestion.us_filter import is_us_location
from scripts.ingestion.role_filter import is_target_role
from scripts.ingestion.parallel_ingestor import is_within_window
from scripts.utils.logger import _log

class AppleJobsAPI:
    BASE_URL = "https://jobs.apple.com"
    API_BASE = f"{BASE_URL}/api/v1"

    def __init__(self, locale: str = "en-us"):
        self.locale = locale
        self._csrf_token: Optional[str] = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Origin': self.BASE_URL,
            'Referer': f'{self.BASE_URL}/{locale}/search',
            'Content-Type': 'application/json',
            'browserlocale': locale,
            'locale': locale.replace('-', '_').upper(),
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
        }

    async def _ensure_csrf_token(self, session: aiohttp.ClientSession):
        if not self._csrf_token:
            async with session.get(f"{self.API_BASE}/CSRFToken", headers=self.headers) as response:
                if response.status == 200:
                    self._csrf_token = response.headers.get('x-apple-csrf-token')
                    if self._csrf_token:
                        self.headers['x-apple-csrf-token'] = self._csrf_token

    async def fetch_jobs(self, session: aiohttp.ClientSession, page: int = 1) -> List[NormalizedJob]:
        await self._ensure_csrf_token(session)

        # Apple's payload requires search filters, pagination starts from 1
        payload = {
            "query": "",
            "filters": {
                # Filtering to US regions for accuracy
                "postLocation": ["postLocation-USA"]
            },
            "page": page,
            "locale": self.locale,
            "sort": "postingDate", # newest first
            "format": {
                "longDate": "MMMM D, YYYY",
                "mediumDate": "MMM D, YYYY"
            }
        }

        normalized = []
        try:
            async with session.post(f"{self.API_BASE}/search", json=payload, headers=self.headers) as response:
                if response.status != 200:
                    logger.error(f"Apple API error: {response.status}")
                    return []
                
                data = await response.json()
                results = data.get('res', {}).get('searchResults', [])
                
                for job in results:
                    title = job.get('postingTitle', '')
                    company = "Apple"
                    
                    locations = job.get('locations', [])
                    loc_name = locations[0].get('name', 'United States') if locations else 'United States'
                    
                    pos_id = job.get('positionId', '')
                    transformed_title = job.get('transformedPostingTitle', '')
                    url = f"https://jobs.apple.com/en-us/details/{pos_id}/{transformed_title}"
                    
                    normalized.append(NormalizedJob(
                        title=title,
                        company=company,
                        location=loc_name,
                        url=url,
                        date_posted=job.get('postingDate', ''),
                        source_ats='apple',
                        job_id=str(job.get('id', pos_id))
                    ))
        except Exception as e:
            _log(f"Error fetching Apple Page {page}: {e}", "ERROR")
            
        return normalized

class AmazonJobsAPI:
    API_URL = "https://www.amazon.jobs/api/jobs/search"
    HEADERS = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "User-Agent": "Mozilla/5.0",
    }

    async def fetch_jobs(self, session: aiohttp.ClientSession, page: int = 1) -> List[NormalizedJob]:
        size = 25
        start_offset = (page - 1) * size

        payload = {
            "searchType": "JOB_SEARCH",
            "start": start_offset,
            "size": size,
            "sort_by": "Recent",
        }
        
        normalized = []
        try:
            async with session.post(self.API_URL, json=payload, headers=self.HEADERS) as response:
                if response.status != 200:
                    logger.error(f"Amazon API error: {response.status}")
                    return []
                
                data = await response.json()
                hits = data.get('searchHits', [])
                
                for hit in hits:
                    fields = hit.get('fields', {})
                    def first(arr): return arr[0] if isinstance(arr, list) and arr else None
                    
                    title = first(fields.get("title")) or ""
                    location = first(fields.get("location")) or "United States"
                    date_posted = first(fields.get("createdDate")) or ""
                    job_id = hit.get("id", "")
                    url = f"https://www.amazon.jobs/en/jobs/{job_id}"
                    
                    if title and job_id:
                        normalized.append(NormalizedJob(
                            title=title,
                            company="Amazon",
                            location=location,
                            url=url,
                            date_posted=date_posted,
                            source_ats="amazon",
                            job_id=str(job_id)
                        ))
        except Exception as e:
            _log(f"Error fetching Amazon Page {page}: {e}", "ERROR")
            
        return normalized

class MicrosoftJobsAPI:
    SEARCH_ENDPOINT = "https://apply.careers.microsoft.com/api/pcsx/search"
    HEADERS = {"accept": "application/json, text/plain, */*", "user-agent": "Mozilla/5.0"}
    PAGE_SIZE = 20

    async def fetch_jobs(self, session: aiohttp.ClientSession, page: int = 1) -> List[NormalizedJob]:
        start = (page - 1) * self.PAGE_SIZE
        params = {
            "domain": "microsoft.com",
            "start": str(start),
            "sort_by": "timestamp"
        }
        
        normalized = []
        try:
            async with session.get(self.SEARCH_ENDPOINT, params=params, headers=self.HEADERS) as response:
                if response.status != 200:
                    logger.error(f"Microsoft API error: {response.status}")
                    return []
                
                data = await response.json()
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
                    
                    if title and job_id:
                        normalized.append(NormalizedJob(
                            title=title,
                            company="Microsoft",
                            location=location,
                            url=url,
                            date_posted=date_posted,
                            source_ats="microsoft",
                            job_id=str(job_id)
                        ))
        except Exception as e:
            _log(f"Error fetching Microsoft Page {page}: {e}", "ERROR")
            
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

async def run_enterprise_scraper():
    log("=== Commencing Phase 9: Enterprise Architecture Scrape ===")
    start_t = time.time()
    all_jobs = []

    async with aiohttp.ClientSession() as session:
        apple_api = AppleJobsAPI()
        amazon_api = AmazonJobsAPI()
        microsoft_api = MicrosoftJobsAPI()
        google_api = GoogleJobsAPI()
        meta_api = MetaJobsAPI()
        
        log("Fetching active job positions from Apple, Amazon, Microsoft, Google, and Meta...")
        
        # Google & Meta fetch all pages deeply via Playwright interceptors.
        google_task = asyncio.create_task(google_api.fetch_all_jobs(max_pages=5))
        meta_task = asyncio.create_task(meta_api.fetch_all_jobs())
        
        for p in range(1, 6):
            results = await asyncio.gather(
                apple_api.fetch_jobs(session, page=p),
                amazon_api.fetch_jobs(session, page=p),
                microsoft_api.fetch_jobs(session, page=p)
            )
            for res in results:
                all_jobs.extend(res)
            
            await asyncio.sleep(1.0) # respect rate limits

        # Wait for Headless Browser Tasks
        google_jobs = await google_task
        meta_jobs = await meta_task
        
        all_jobs.extend(google_jobs)
        all_jobs.extend(meta_jobs)

    log(f"Fetched {len(all_jobs)} total raw jobs from Enterprise endpoints.")

    if not all_jobs:
        log("No jobs found across endpoints. Exiting properly.")
        return

    # Pipeline Processing
    valid_roles = [j for j in all_jobs if is_target_role(j.title)]
    log(f"Role filter: {len(valid_roles)}/{len(all_jobs)} matched target tech roles.")

    us_jobs = [j for j in valid_roles if is_us_location(j.location)]
    log(f"US filter: {len(us_jobs)}/{len(valid_roles)} in United States.")
    
    # Optional 24hr filter behavior
    now = time.localtime()
    is_midnight = now.tm_hour == 0

    if not is_midnight:
        final_jobs = [j for j in us_jobs if is_within_window(j.date_posted)]
        log(f"24hr filter (Incremental Sweep): {len(final_jobs)}/{len(us_jobs)} within 24h window.")
    else:
        final_jobs = us_jobs
        log("Midnight 24hr sweep active. Skipping recent filter to catch backlog.")

    new_jobs_inserted = 0
    conn = get_connection()
    try:
        for job in final_jobs:
            if insert_job(conn, job.__dict__):
                new_jobs_inserted += 1

        log_scraper_run(
            conn=conn,
            script_name="scrape_enterprise",
            companies_fetched=1,  # Number of custom enterprise scrapers that succeeded
            new_jobs=new_jobs_inserted,
            duration=round(time.time() - start_t, 2)
        )
    finally:
        conn.close()

    total_time = round(time.time() - start_t, 2)
    log(f">>> Enterprise Scraper Complete. Found {new_jobs_inserted} brand new jobs out of {len(final_jobs)} candidates. (Took {total_time}s)")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run_enterprise_scraper())
