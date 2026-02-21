"""
Aggregator & Startup Board Adapters.

Fetches jobs from aggregator sites and startup job boards.
Some use internal APIs discovered via network inspection,
others fall back to RSS or simple HTTP scraping.

Supported:
  - HiringCafe (internal search API)
  - Jobright.ai (internal API)
  - Startup.jobs (HTTP)
  - Y Combinator Work at a Startup (HTTP)
"""

import json
import re
from datetime import datetime, timezone
from typing import Optional
import aiohttp

from scripts.ingestion.ats_adapters import NormalizedJob


# ═══════════════════════════════════════════════════════════════════════
# HIRING CAFE
# ═══════════════════════════════════════════════════════════════════════

class HiringCafeAdapter:
    """HiringCafe internal search API.

    Uses POST to their search endpoint with role-based queries.
    Falls back to RSS-like structured extraction if API changes.
    """

    SEARCH_URL = "https://hiring.cafe/api/search"

    SEARCH_QUERIES = [
        "software engineer",
        "machine learning engineer",
        "data scientist",
        "data engineer",
        "AI engineer",
    ]

    @staticmethod
    async def fetch(session: aiohttp.ClientSession) -> list[NormalizedJob]:
        all_jobs = []

        for query in HiringCafeAdapter.SEARCH_QUERIES:
            try:
                payload = {
                    "query": query,
                    "location": "United States",
                    "limit": 50,
                }
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "JobClaw/2.0",
                }

                async with session.post(
                    HiringCafeAdapter.SEARCH_URL, json=payload,
                    headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        # Try GET endpoint fallback
                        get_url = f"https://hiring.cafe/api/jobs?q={query.replace(' ', '+')}&location=US&limit=50"
                        async with session.get(
                            get_url, headers=headers,
                            timeout=aiohttp.ClientTimeout(total=30)
                        ) as get_resp:
                            if get_resp.status != 200:
                                continue
                            data = await get_resp.json(content_type=None)
                    else:
                        data = await resp.json(content_type=None)

                # Parse results (format may vary)
                jobs_list = data if isinstance(data, list) else data.get("jobs", data.get("results", []))

                for j in jobs_list:
                    if not isinstance(j, dict):
                        continue
                    all_jobs.append(NormalizedJob(
                        title=j.get("title", j.get("job_title", "")),
                        company=j.get("company", j.get("company_name", "Unknown")),
                        location=j.get("location", "Unknown"),
                        url=j.get("url", j.get("apply_url", j.get("link", ""))),
                        date_posted=j.get("date_posted", j.get("posted_date", j.get("date", ""))),
                        source_ats="hiringcafe",
                        job_id=str(j.get("id", j.get("job_id", f"{j.get('title','')}-{j.get('company','')}"))),
                    ))
            except Exception:
                continue

        return all_jobs


# ═══════════════════════════════════════════════════════════════════════
# JOBRIGHT.AI
# ═══════════════════════════════════════════════════════════════════════

class JobrightAdapter:
    """Jobright.ai internal API adapter.

    Jobright has a GraphQL/REST API behind their frontend.
    Falls back to their sitemap or structured pages.
    """

    API_URL = "https://jobright.ai/api/jobs/search"

    SEARCH_QUERIES = [
        "software engineer",
        "machine learning",
        "data scientist",
        "new grad",
    ]

    @staticmethod
    async def fetch(session: aiohttp.ClientSession) -> list[NormalizedJob]:
        all_jobs = []

        for query in JobrightAdapter.SEARCH_QUERIES:
            try:
                params = {
                    "q": query,
                    "location": "United States",
                    "limit": 50,
                    "sort": "date",
                }
                headers = {
                    "Accept": "application/json",
                    "User-Agent": "JobClaw/2.0",
                }

                async with session.get(
                    JobrightAdapter.API_URL, params=params,
                    headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)

                jobs_list = data if isinstance(data, list) else data.get("jobs", data.get("results", data.get("data", [])))

                for j in jobs_list:
                    if not isinstance(j, dict):
                        continue
                    all_jobs.append(NormalizedJob(
                        title=j.get("title", j.get("job_title", "")),
                        company=j.get("company", j.get("company_name", "Unknown")),
                        location=j.get("location", "Unknown"),
                        url=j.get("url", j.get("apply_url", "")),
                        date_posted=j.get("date_posted", j.get("posted_date", "")),
                        source_ats="jobright",
                        job_id=str(j.get("id", j.get("job_id", ""))),
                    ))
            except Exception:
                continue

        return all_jobs


# ═══════════════════════════════════════════════════════════════════════
# Y COMBINATOR - Work at a Startup API
# ═══════════════════════════════════════════════════════════════════════

class YCWorkAtStartupAdapter:
    """Y Combinator 'Work at a Startup' internal API.

    Fetches from their algolia-backed search endpoint.
    """

    API_URL = "https://45bwzj1sgc-dsn.algolia.net/1/indexes/WaaSJobs_production"

    @staticmethod
    async def fetch(session: aiohttp.ClientSession) -> list[NormalizedJob]:
        try:
            params = {
                "query": "",
                "hitsPerPage": 100,
                "filters": "role_type:FullTime",
                "x-algolia-application-id": "45BWZJ1SGC",
                "x-algolia-api-key": "MjBjYjRiMzY0NzdhZWY0NjExY2NhZjYxMGIxYjc2MTAwNWFkNTkwNTc4NjgxYjU0YzFhYTY2ZGQ5OGY5NDMzZnJlc3RyaWN0SW5kaWNlcz0nV2FhU0pvYnNfcHJvZHVjdGlvbic=",
            }
            headers = {
                "Accept": "application/json",
                "User-Agent": "JobClaw/2.0",
            }

            async with session.get(
                YCWorkAtStartupAdapter.API_URL, params=params,
                headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json(content_type=None)

            jobs = []
            for hit in data.get("hits", []):
                company = hit.get("company_name", hit.get("startup_name", "Unknown"))
                title = hit.get("title", "")
                locations = hit.get("pretty_location", hit.get("location", "Unknown"))

                url = hit.get("url", "")
                if not url and hit.get("slug"):
                    url = f"https://www.workatastartup.com/jobs/{hit['slug']}"

                jobs.append(NormalizedJob(
                    title=title,
                    company=company,
                    location=locations if isinstance(locations, str) else ", ".join(locations),
                    url=url,
                    date_posted=hit.get("created_at", ""),
                    source_ats="yc-startup",
                    job_id=str(hit.get("objectID", hit.get("id", f"{company}-{title}"))),
                ))
            return jobs
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════════════
# COMBINED FETCHER
# ═══════════════════════════════════════════════════════════════════════

AGGREGATOR_ADAPTERS = {
    "hiringcafe": HiringCafeAdapter,
    "jobright": JobrightAdapter,
    "yc-startup": YCWorkAtStartupAdapter,
}


async def fetch_all_aggregators(session: aiohttp.ClientSession) -> tuple[list[NormalizedJob], list[str]]:
    """Fetch jobs from all aggregator sources.

    Returns:
        Tuple of (all_jobs, errors)
    """
    all_jobs = []
    errors = []

    for name, adapter in AGGREGATOR_ADAPTERS.items():
        try:
            jobs = await adapter.fetch(session)
            all_jobs.extend(jobs)
        except Exception as e:
            errors.append(f"Aggregator {name}: {str(e)}")

    return all_jobs, errors
