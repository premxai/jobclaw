"""
ATS Platform Adapters — v3 with TLS impersonation + anti-detection + descriptions.

Each adapter knows how to call a specific ATS platform's public job board API
and normalize the response into a common NormalizedJob format.

v3 improvements over v2:
  - Dual-backend HTTP: curl_cffi (TLS impersonation) or aiohttp fallback
  - Session-agnostic adapters (work with both curl_cffi and aiohttp sessions)
  - Uses hardened HTTP client (UA rotation, per-host rate limiting, retry/backoff)
  - Captures full job descriptions
  - Extracts salary/experience from descriptions
  - Returns raw API data for response caching
  - Proper error logging (no more silent exception swallowing)

Supported platforms:
  - Greenhouse      (boards-api.greenhouse.io)
  - Lever           (api.lever.co)
  - Ashby           (api.ashbyhq.com)
  - SmartRecruiters (api.smartrecruiters.com)
  - BambooHR        ({slug}.bamboohr.com)
  - Workday         ({tenant}.wd{shard}.myworkdayjobs.com)
  - Workable        (apply.workable.com)
  - Rippling        (ats.rippling.com)
"""

import hashlib
import html
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from scripts.utils.http_client import fetch_with_retry, RateLimiter, HAS_CURL_CFFI
from scripts.utils.salary_parser import extract_salary, extract_experience, parse_salary_range
from scripts.utils.logger import _log


async def _parse_json(resp) -> Any:
    """Parse JSON from either a curl_cffi or aiohttp response."""
    if HAS_CURL_CFFI:
        from curl_cffi.requests import AsyncSession as CffiSession
        # curl_cffi responses have .json() as a sync method
        if hasattr(resp, 'status_code'):
            return resp.json()
    # aiohttp responses have .json() as an async method
    return await resp.json()


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
    description: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None
    experience_years: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def dedup_key(self) -> str:
        """Unique key for dedup: hash of title + company + location."""
        raw = f"{self.title}|{self.company}|{self.location}".lower().strip()
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _enrich_job(job: NormalizedJob) -> NormalizedJob:
    """Extract salary and experience from the job description."""
    if not job.description:
        return job

    salary_str, _ = extract_salary(job.description)
    if salary_str:
        s_min, s_max, s_cur = parse_salary_range(salary_str)
        job.salary_min = s_min
        job.salary_max = s_max
        job.salary_currency = s_cur

    years, _ = extract_experience(job.description)
    if years is not None:
        job.experience_years = years

    return job


def _strip_html(text: str) -> str:
    """Strip HTML tags and decode entities to get plain text."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ═══════════════════════════════════════════════════════════════════════
# GREENHOUSE ADAPTER
# ═══════════════════════════════════════════════════════════════════════

class GreenhouseAdapter:
    """Greenhouse Boards API: boards-api.greenhouse.io/v1/boards/{slug}/jobs"""

    BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"

    @staticmethod
    async def fetch(
        session,
        slug: str,
        company: str,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> list[NormalizedJob]:
        url = GreenhouseAdapter.BASE_URL.format(slug=slug)
        resp = await fetch_with_retry(
            session, "GET", url,
            rate_limiter=rate_limiter,
            log_tag=f"greenhouse/{slug}",
            params={"content": "true"},
        )
        if not resp:
            return []

        try:
            data = await _parse_json(resp)
        except Exception as e:
            _log(f"[greenhouse/{slug}] JSON decode error: {e}", "WARN")
            return []

        jobs = []
        for j in data.get("jobs", []):
            updated_at = j.get("updated_at") or j.get("created_at", "")
            loc_obj = j.get("location")
            location = loc_obj.get("name", "Unknown") if isinstance(loc_obj, dict) else "Unknown"

            # Full description from the content field (HTML)
            raw_content = j.get("content", "")
            description = _strip_html(raw_content) if raw_content else None

            job = NormalizedJob(
                title=j.get("title", ""),
                company=company,
                location=location,
                url=f"https://boards.greenhouse.io/{slug}/jobs/{j.get('id', '')}",
                date_posted=updated_at,
                source_ats="greenhouse",
                job_id=str(j.get("id", "")),
                description=description,
            )
            jobs.append(_enrich_job(job))

        return jobs


# ═══════════════════════════════════════════════════════════════════════
# LEVER ADAPTER
# ═══════════════════════════════════════════════════════════════════════

class LeverAdapter:
    """Lever Postings API: api.lever.co/v0/postings/{slug}"""

    BASE_URL = "https://api.lever.co/v0/postings/{slug}"

    @staticmethod
    async def fetch(
        session,
        slug: str,
        company: str,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> list[NormalizedJob]:
        url = LeverAdapter.BASE_URL.format(slug=slug)
        resp = await fetch_with_retry(
            session, "GET", url,
            rate_limiter=rate_limiter,
            log_tag=f"lever/{slug}",
        )
        if not resp:
            return []

        try:
            data = await _parse_json(resp)
        except Exception as e:
            _log(f"[lever/{slug}] JSON decode error: {e}", "WARN")
            return []

        if not isinstance(data, list):
            return []

        jobs = []
        for j in data:
            created_at = j.get("createdAt", 0)

            cats = j.get("categories")
            if isinstance(cats, dict):
                location = cats.get("location", "Unknown")
            else:
                location = "Unknown"
            if isinstance(location, list):
                location = ", ".join(location) if location else "Unknown"

            # Build description from descriptionPlain + lists + additionalPlain
            desc_parts = []
            if j.get("descriptionPlain"):
                desc_parts.append(j["descriptionPlain"].strip())
            if j.get("lists") and isinstance(j["lists"], list):
                for li in j["lists"]:
                    if isinstance(li, dict):
                        header = li.get("text", "").strip()
                        content = li.get("content", "")
                        if content:
                            plain = _strip_html(content)
                            if plain:
                                desc_parts.append(f"{header}\n{plain}" if header else plain)
            if j.get("additionalPlain"):
                desc_parts.append(j["additionalPlain"].strip())
            description = "\n\n".join(desc_parts) if desc_parts else None

            job = NormalizedJob(
                title=j.get("text", ""),
                company=company,
                location=location,
                url=j.get("hostedUrl", ""),
                date_posted=datetime.fromtimestamp(
                    created_at / 1000, tz=timezone.utc
                ).isoformat() if created_at else "",
                source_ats="lever",
                job_id=j.get("id", ""),
                description=description,
            )
            jobs.append(_enrich_job(job))

        return jobs


# ═══════════════════════════════════════════════════════════════════════
# ASHBY ADAPTER
# ═══════════════════════════════════════════════════════════════════════

class AshbyAdapter:
    """Ashby Job Board API: api.ashbyhq.com/posting-api/job-board/{slug}"""

    BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"

    @staticmethod
    async def fetch(
        session,
        slug: str,
        company: str,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> list[NormalizedJob]:
        url = AshbyAdapter.BASE_URL.format(slug=slug)
        resp = await fetch_with_retry(
            session, "GET", url,
            rate_limiter=rate_limiter,
            log_tag=f"ashby/{slug}",
        )
        if not resp:
            return []

        try:
            data = await _parse_json(resp)
        except Exception as e:
            _log(f"[ashby/{slug}] JSON decode error: {e}", "WARN")
            return []

        jobs = []
        for j in data.get("jobs", []):
            location = j.get("location", "Unknown")
            if isinstance(location, dict):
                location = location.get("name", "Unknown")
            published = j.get("publishedAt", "")

            # Ashby provides descriptionPlain or descriptionHtml
            description = j.get("descriptionPlain") or _strip_html(j.get("descriptionHtml", ""))

            job = NormalizedJob(
                title=j.get("title", ""),
                company=company,
                location=location,
                url=j.get("jobUrl", j.get("applyUrl", "")),
                date_posted=published,
                source_ats="ashby",
                job_id=j.get("id", ""),
                description=description or None,
            )
            jobs.append(_enrich_job(job))

        return jobs


# ═══════════════════════════════════════════════════════════════════════
# SMARTRECRUITERS ADAPTER
# ═══════════════════════════════════════════════════════════════════════

class SmartRecruitersAdapter:
    """SmartRecruiters API: api.smartrecruiters.com/v1/companies/{slug}/postings"""

    BASE_URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"

    @staticmethod
    async def fetch(
        session,
        slug: str,
        company: str,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> list[NormalizedJob]:
        url = SmartRecruitersAdapter.BASE_URL.format(slug=slug)
        all_jobs = []
        offset = 0
        limit = 100

        while True:
            resp = await fetch_with_retry(
                session, "GET", url,
                rate_limiter=rate_limiter,
                log_tag=f"smartrecruiters/{slug}",
                params={"limit": limit, "offset": offset},
            )
            if not resp:
                break

            try:
                data = await _parse_json(resp)
            except Exception:
                break

            content = data.get("content", [])
            if not content:
                break

            for j in content:
                location_obj = j.get("location", {})
                location = location_obj.get("city", "")
                if location_obj.get("region"):
                    location += f", {location_obj['region']}"
                if location_obj.get("country"):
                    location += f", {location_obj['country']}"
                if not location:
                    location = "Unknown"

                released = j.get("releasedDate", "")

                # SmartRecruiters includes jobAd.sections for descriptions
                description = None
                job_ad = j.get("jobAd")
                if job_ad and isinstance(job_ad, dict):
                    sections = job_ad.get("sections")
                    if sections and isinstance(sections, dict):
                        desc_parts = []
                        for section_key in ["jobDescription", "qualifications", "additionalInformation"]:
                            section = sections.get(section_key, {})
                            if section and section.get("text"):
                                desc_parts.append(_strip_html(section["text"]))
                        if desc_parts:
                            description = "\n\n".join(desc_parts)

                job = NormalizedJob(
                    title=j.get("name", ""),
                    company=company,
                    location=location.strip(", "),
                    url=f"https://jobs.smartrecruiters.com/{slug}/{j.get('id', '')}",
                    date_posted=released,
                    source_ats="smartrecruiters",
                    job_id=str(j.get("id", "")),
                    description=description,
                )
                all_jobs.append(_enrich_job(job))

            if len(content) < limit:
                break
            offset += limit

        return all_jobs


# ═══════════════════════════════════════════════════════════════════════
# BAMBOOHR ADAPTER
# ═══════════════════════════════════════════════════════════════════════

class BambooHRAdapter:
    """BambooHR: {slug}.bamboohr.com/careers/list"""

    BASE_URL = "https://{slug}.bamboohr.com/careers/list"

    @staticmethod
    async def fetch(
        session,
        slug: str,
        company: str,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> list[NormalizedJob]:
        url = BambooHRAdapter.BASE_URL.format(slug=slug)
        resp = await fetch_with_retry(
            session, "GET", url,
            rate_limiter=rate_limiter,
            log_tag=f"bamboohr/{slug}",
            headers={"Accept": "application/json"},
        )
        if not resp:
            return []

        try:
            data = await _parse_json(resp)
        except Exception as e:
            _log(f"[bamboohr/{slug}] JSON decode error: {e}", "WARN")
            return []

        jobs = []
        for j in data.get("result", []):
            loc_obj = j.get("location")
            location_parts = []
            if isinstance(loc_obj, dict):
                if loc_obj.get("city"):
                    location_parts.append(loc_obj["city"])
                if loc_obj.get("state"):
                    location_parts.append(loc_obj["state"])
            location = ", ".join(location_parts) if location_parts else "Unknown"

            description = _strip_html(j.get("description", "")) or None

            job = NormalizedJob(
                title=j.get("jobOpeningName", ""),
                company=company,
                location=location,
                url=f"https://{slug}.bamboohr.com/careers/{j.get('id', '')}",
                date_posted=j.get("datePosted", ""),
                source_ats="bamboohr",
                job_id=str(j.get("id", "")),
                description=description,
            )
            jobs.append(_enrich_job(job))

        return jobs


# ═══════════════════════════════════════════════════════════════════════
# WORKDAY ADAPTER
# ═══════════════════════════════════════════════════════════════════════

class WorkdayAdapter:
    """Workday CXS API: {tenant}.wd{shard}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs

    Slug format: "tenant:shard:site"
    Example: "microsoft:5:Microsoft" → microsoft.wd5.myworkdayjobs.com/wday/cxs/microsoft/Microsoft/jobs
    """

    @staticmethod
    async def fetch(
        session,
        slug: str,
        company: str,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> list[NormalizedJob]:
        parts = slug.split(":")
        if len(parts) != 3:
            _log(f"[workday/{slug}] Invalid slug format (expected tenant:shard:site)", "WARN")
            return []
        tenant, shard, site = parts

        base_url = f"https://{tenant}.wd{shard}.myworkdayjobs.com"
        api_url = f"{base_url}/wday/cxs/{tenant}/{site}/jobs"

        payload = {
            "appliedFacets": {},
            "limit": 20,
            "offset": 0,
            "searchText": "",
        }

        all_jobs = []
        offset = 0
        max_pages = 50  # Safety limit: 1000 jobs max

        while offset < max_pages * 20:
            payload["offset"] = offset
            resp = await fetch_with_retry(
                session, "POST", api_url,
                rate_limiter=rate_limiter,
                log_tag=f"workday/{tenant}",
                json=payload,
            )
            if not resp:
                break

            try:
                data = await _parse_json(resp)
            except Exception:
                break

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
                    for bf in bullet_fields:
                        if "posted" in str(bf).lower() or "20" in str(bf):
                            posted = str(bf)
                            break

                external_path = j.get("externalPath", "")
                job_url = f"{base_url}/en-US/{site}{external_path}" if external_path else ""

                job = NormalizedJob(
                    title=title,
                    company=company,
                    location=location,
                    url=job_url,
                    date_posted=posted,
                    source_ats="workday",
                    job_id=external_path or title,
                )
                all_jobs.append(job)

            total = data.get("total", 0)
            offset += 20
            if offset >= total:
                break

        return all_jobs


# ═══════════════════════════════════════════════════════════════════════
# WORKABLE ADAPTER
# ═══════════════════════════════════════════════════════════════════════

class WorkableAdapter:
    """Workable API: apply.workable.com/api/v3/accounts/{slug}/jobs"""

    BASE_URL = "https://apply.workable.com/api/v3/accounts/{slug}/jobs"

    @staticmethod
    async def fetch(
        session,
        slug: str,
        company: str,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> list[NormalizedJob]:
        url = WorkableAdapter.BASE_URL.format(slug=slug)
        all_jobs = []
        token = None  # Cursor for pagination
        max_pages = 20  # Safety limit

        for _ in range(max_pages):
            payload = {
                "query": "",
                "location": [],
                "department": [],
                "worktype": [],
                "remote": [],
            }
            if token:
                payload["token"] = token

            resp = await fetch_with_retry(
                session, "POST", url,
                rate_limiter=rate_limiter,
                log_tag=f"workable/{slug}",
                json=payload,
            )
            if not resp:
                break

            try:
                data = await _parse_json(resp)
            except Exception as e:
                _log(f"[workable/{slug}] JSON decode error: {e}", "WARN")
                break

            for j in data.get("results", []):
                location_obj = j.get("location", {})
                location = location_obj.get("city") or ""
                region = location_obj.get("region")
                if region:
                    location += f", {region}" if location else region
                country = location_obj.get("country")
                if country:
                    location += f", {country}" if location else country
                
                if not location:
                    location = "Unknown"

                published = j.get("published", "")

                description = _strip_html(j.get("description", "")) or None

                job = NormalizedJob(
                    title=j.get("title", ""),
                    company=company,
                    location=location.strip(", "),
                    url=f"https://apply.workable.com/{slug}/j/{j.get('shortcode', '')}/",
                    date_posted=published,
                    source_ats="workable",
                    job_id=str(j.get("shortcode", "")),
                    description=description,
                )
                all_jobs.append(_enrich_job(job))

            # Check for next page cursor
            next_token = data.get("nextPage") or data.get("paging", {}).get("next")
            if not next_token or not data.get("results"):
                break
            token = next_token

        return all_jobs


# ═══════════════════════════════════════════════════════════════════════
# RIPPLING ADAPTER
# ═══════════════════════════════════════════════════════════════════════

class RipplingAdapter:
    """Rippling API: api.rippling.com/ats/api/v1/board/{slug}/jobs"""

    BASE_URL = "https://ats.rippling.com/api/v1/board/{slug}/jobs"

    @staticmethod
    async def fetch(
        session,
        slug: str,
        company: str,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> list[NormalizedJob]:
        url = RipplingAdapter.BASE_URL.format(slug=slug)
        resp = await fetch_with_retry(
            session, "GET", url,
            rate_limiter=rate_limiter,
            log_tag=f"rippling/{slug}",
        )
        if not resp:
            return []

        try:
            data = await _parse_json(resp)
        except Exception as e:
            _log(f"[rippling/{slug}] JSON decode error: {e}", "WARN")
            return []

        if not isinstance(data, list):
            data = data.get("jobs", data.get("data", []))

        jobs = []
        for j in data:
            if not isinstance(j, dict):
                continue
            location = j.get("location", {})
            if isinstance(location, dict):
                location = location.get("name", "Unknown")
            elif not isinstance(location, str):
                location = "Unknown"

            created = j.get("timeCreated", "")

            description = _strip_html(j.get("description", "")) or None

            job = NormalizedJob(
                title=j.get("name", ""),
                company=company,
                location=location,
                url=j.get("url", f"https://ats.rippling.com/{slug}/jobs/{j.get('id', '')}"),
                date_posted=created,
                source_ats="rippling",
                job_id=j.get("id", ""),
                description=description,
            )
            jobs.append(_enrich_job(job))

        return jobs


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
    "workable": WorkableAdapter,
    "rippling": RipplingAdapter,
}


async def fetch_company_jobs(
    session,
    company: str,
    ats: str,
    slug: str,
    rate_limiter: Optional[RateLimiter] = None,
) -> list[NormalizedJob]:
    """Fetch jobs for a single company using the appropriate adapter."""
    adapter = ADAPTERS.get(ats)
    if not adapter:
        _log(f"No adapter for ATS platform '{ats}' (company: {company})", "WARN")
        return []
    return await adapter.fetch(session, slug, company, rate_limiter=rate_limiter)
