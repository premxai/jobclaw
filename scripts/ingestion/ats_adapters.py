"""
ATS Platform Adapters.

Each adapter knows how to call a specific ATS platform's public job board API
and normalize the response into a common NormalizedJob format.

Supported platforms:
  - Greenhouse      (boards-api.greenhouse.io)
  - Lever           (api.lever.co)
  - Ashby           (api.ashbyhq.com)
  - SmartRecruiters (api.smartrecruiters.com)
  - BambooHR        ({slug}.bamboohr.com)
  - Workday         ({tenant}.wd{shard}.myworkdayjobs.com)
"""

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
import aiohttp


@dataclass
class NormalizedJob:
    """Common job format across all ATS platforms."""
    title: str
    company: str
    location: str
    url: str
    date_posted: str            # ISO string or relative ("3 hours ago")
    source_ats: str             # greenhouse, lever, ashby, etc.
    job_id: str                 # Unique ID (from ATS or generated hash)
    first_seen: str = ""        # When we first ingested it
    keywords_matched: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def dedup_key(self) -> str:
        """Unique key for dedup: hash of title + company + location."""
        raw = f"{self.title}|{self.company}|{self.location}".lower().strip()
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _is_within_24h(timestamp: Optional[int | float]) -> bool:
    """Check if a Unix timestamp (ms or s) is within last 24 hours."""
    if not timestamp:
        return True  # If no date, include it (let filter decide)
    # Handle milliseconds
    if timestamp > 1e12:
        timestamp = timestamp / 1000
    try:
        posted = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        return posted >= cutoff
    except (ValueError, OSError):
        return True


# ═══════════════════════════════════════════════════════════════════════
# GREENHOUSE ADAPTER
# ═══════════════════════════════════════════════════════════════════════

class GreenhouseAdapter:
    """Greenhouse Boards API: boards-api.greenhouse.io/v1/boards/{slug}/jobs"""

    BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"

    @staticmethod
    async def fetch(session: aiohttp.ClientSession, slug: str, company: str) -> list[NormalizedJob]:
        url = GreenhouseAdapter.BASE_URL.format(slug=slug)
        params = {"content": "true"}
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

            jobs = []
            for j in data.get("jobs", []):
                updated_at = j.get("updated_at") or j.get("created_at", "")
                # Greenhouse returns ISO dates
                location = j.get("location", {}).get("name", "Unknown")

                jobs.append(NormalizedJob(
                    title=j.get("title", ""),
                    company=company,
                    location=location,
                    url=f"https://boards.greenhouse.io/{slug}/jobs/{j.get('id', '')}",
                    date_posted=updated_at,
                    source_ats="greenhouse",
                    job_id=str(j.get("id", "")),
                ))
            return jobs
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════════════
# LEVER ADAPTER
# ═══════════════════════════════════════════════════════════════════════

class LeverAdapter:
    """Lever Postings API: api.lever.co/v0/postings/{slug}"""

    BASE_URL = "https://api.lever.co/v0/postings/{slug}"

    @staticmethod
    async def fetch(session: aiohttp.ClientSession, slug: str, company: str) -> list[NormalizedJob]:
        url = LeverAdapter.BASE_URL.format(slug=slug)
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

            if not isinstance(data, list):
                return []

            jobs = []
            for j in data:
                created_at = j.get("createdAt", 0)

                # Lever uses ms timestamps
                if not _is_within_24h(created_at):
                    continue

                location = j.get("categories", {}).get("location", "Unknown")
                if isinstance(location, list):
                    location = ", ".join(location) if location else "Unknown"

                jobs.append(NormalizedJob(
                    title=j.get("text", ""),
                    company=company,
                    location=location,
                    url=j.get("hostedUrl", ""),
                    date_posted=datetime.fromtimestamp(
                        created_at / 1000, tz=timezone.utc
                    ).isoformat() if created_at else "",
                    source_ats="lever",
                    job_id=j.get("id", ""),
                ))
            return jobs
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════════════
# ASHBY ADAPTER
# ═══════════════════════════════════════════════════════════════════════

class AshbyAdapter:
    """Ashby Job Board API: api.ashbyhq.com/posting-api/job-board/{slug}"""

    BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"

    @staticmethod
    async def fetch(session: aiohttp.ClientSession, slug: str, company: str) -> list[NormalizedJob]:
        url = AshbyAdapter.BASE_URL.format(slug=slug)
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

            jobs = []
            for j in data.get("jobs", []):
                location = j.get("location", "Unknown")
                if isinstance(location, dict):
                    location = location.get("name", "Unknown")
                published = j.get("publishedAt", "")

                jobs.append(NormalizedJob(
                    title=j.get("title", ""),
                    company=company,
                    location=location,
                    url=j.get("jobUrl", j.get("applyUrl", "")),
                    date_posted=published,
                    source_ats="ashby",
                    job_id=j.get("id", ""),
                ))
            return jobs
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════════════
# SMARTRECRUITERS ADAPTER
# ═══════════════════════════════════════════════════════════════════════

class SmartRecruitersAdapter:
    """SmartRecruiters API: api.smartrecruiters.com/v1/companies/{slug}/postings"""

    BASE_URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"

    @staticmethod
    async def fetch(session: aiohttp.ClientSession, slug: str, company: str) -> list[NormalizedJob]:
        url = SmartRecruitersAdapter.BASE_URL.format(slug=slug)
        params = {"limit": 100}
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

            jobs = []
            for j in data.get("content", []):
                location_obj = j.get("location", {})
                location = location_obj.get("city", "")
                if location_obj.get("region"):
                    location += f", {location_obj['region']}"
                if location_obj.get("country"):
                    location += f", {location_obj['country']}"
                if not location:
                    location = "Unknown"

                released = j.get("releasedDate", "")

                jobs.append(NormalizedJob(
                    title=j.get("name", ""),
                    company=company,
                    location=location.strip(", "),
                    url=f"https://jobs.smartrecruiters.com/{slug}/{j.get('id', '')}",
                    date_posted=released,
                    source_ats="smartrecruiters",
                    job_id=str(j.get("id", "")),
                ))
            return jobs
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════════════
# BAMBOOHR ADAPTER
# ═══════════════════════════════════════════════════════════════════════

class BambooHRAdapter:
    """BambooHR: {slug}.bamboohr.com/careers/list"""

    BASE_URL = "https://{slug}.bamboohr.com/careers/list"

    @staticmethod
    async def fetch(session: aiohttp.ClientSession, slug: str, company: str) -> list[NormalizedJob]:
        url = BambooHRAdapter.BASE_URL.format(slug=slug)
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30),
                                   headers={"Accept": "application/json"}) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

            jobs = []
            for j in data.get("result", []):
                location_parts = []
                if j.get("location", {}).get("city"):
                    location_parts.append(j["location"]["city"])
                if j.get("location", {}).get("state"):
                    location_parts.append(j["location"]["state"])
                location = ", ".join(location_parts) if location_parts else "Unknown"

                jobs.append(NormalizedJob(
                    title=j.get("jobOpeningName", ""),
                    company=company,
                    location=location,
                    url=f"https://{slug}.bamboohr.com/careers/{j.get('id', '')}",
                    date_posted=j.get("datePosted", ""),
                    source_ats="bamboohr",
                    job_id=str(j.get("id", "")),
                ))
            return jobs
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════════════
# WORKDAY ADAPTER
# ═══════════════════════════════════════════════════════════════════════

class WorkdayAdapter:
    """Workday CXS API: {tenant}.wd{shard}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs

    Slug format: "tenant:shard:site"
    Example: "microsoft:5:Microsoft" → microsoft.wd5.myworkdayjobs.com/wday/cxs/microsoft/Microsoft/jobs
    """

    @staticmethod
    async def fetch(session: aiohttp.ClientSession, slug: str, company: str) -> list[NormalizedJob]:
        # Parse slug: "tenant:shard:site"
        parts = slug.split(":")
        if len(parts) != 3:
            return []
        tenant, shard, site = parts

        base_url = f"https://{tenant}.wd{shard}.myworkdayjobs.com"
        api_url = f"{base_url}/wday/cxs/{tenant}/{site}/jobs"

        # Workday uses POST with JSON body for search
        payload = {
            "appliedFacets": {},
            "limit": 20,
            "offset": 0,
            "searchText": "",
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            all_jobs = []
            offset = 0
            max_pages = 10  # Safety limit: 200 jobs max

            while offset < max_pages * 20:
                payload["offset"] = offset
                async with session.post(
                    api_url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        break
                    data = await resp.json()

                job_postings = data.get("jobPostings", [])
                if not job_postings:
                    break

                for j in job_postings:
                    title = j.get("title", "")
                    loc_parts = []
                    if j.get("locationsText"):
                        loc_parts.append(j["locationsText"])
                    location = ", ".join(loc_parts) if loc_parts else "Unknown"

                    posted = j.get("postedOn", "")
                    bullet_fields = j.get("bulletFields", [])
                    if not posted and bullet_fields:
                        # Sometimes date is in bulletFields
                        for bf in bullet_fields:
                            if "posted" in str(bf).lower() or "20" in str(bf):
                                posted = str(bf)
                                break

                    external_path = j.get("externalPath", "")
                    job_url = f"{base_url}/en-US/{site}{external_path}" if external_path else ""

                    all_jobs.append(NormalizedJob(
                        title=title,
                        company=company,
                        location=location,
                        url=job_url,
                        date_posted=posted,
                        source_ats="workday",
                        job_id=external_path or title,
                    ))

                total = data.get("total", 0)
                offset += 20
                if offset >= total:
                    break

            return all_jobs
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════════════
# ADAPTER REGISTRY
# ═══════════════════════════════════════════════════════════════════════

ADAPTERS = {
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "ashby": AshbyAdapter,
    "smartrecruiters": SmartRecruitersAdapter,
    "bamboohr": BambooHRAdapter,
    "workday": WorkdayAdapter,
}


async def fetch_company_jobs(
    session: aiohttp.ClientSession,
    company: str,
    ats: str,
    slug: str,
) -> list[NormalizedJob]:
    """Fetch jobs for a single company using the appropriate adapter."""
    adapter = ADAPTERS.get(ats)
    if not adapter:
        return []
    return await adapter.fetch(session, slug, company)
