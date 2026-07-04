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
  - Gem             (job-boards.gem.com)
"""

import hashlib
import html
import os
import re
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from scripts.utils.http_client import (
    HAS_CURL_CFFI,
    NOT_MODIFIED,
    RateLimiter,
    consume_last_failure,
    fetch_with_retry,
    record_request_failure,
)
from scripts.utils.ats_slug_aliases import get_ats_slug_aliases
from scripts.utils.logger import _log
from scripts.utils.target_diagnostics import classify_failure
from scripts.utils.salary_parser import extract_experience, extract_salary, parse_salary_range

_LAST_TARGET_METADATA: ContextVar[dict[str, object] | None] = ContextVar("jobclaw_last_target_metadata", default=None)


def record_target_metadata(**metadata: object) -> dict[str, object]:
    """Store platform-specific metadata discovered while scraping a target."""
    _LAST_TARGET_METADATA.set(metadata)
    return metadata


def consume_target_metadata() -> dict[str, object] | None:
    """Read and clear metadata discovered by the last adapter call in this task."""
    metadata = _LAST_TARGET_METADATA.get()
    _LAST_TARGET_METADATA.set(None)
    return metadata


# Cap the response body we will parse to avoid memory exhaustion from a hostile or
# misbehaving endpoint returning an enormous payload. Generous default (25 MB) — real
# ATS boards are well under this even for very large employers.
MAX_RESPONSE_BYTES = int(os.getenv("JOBCLAW_MAX_RESPONSE_BYTES", str(25 * 1024 * 1024)))


def _declared_too_large(resp) -> bool:
    """True if the response's declared Content-Length exceeds the parse cap."""
    headers = getattr(resp, "headers", None) or {}
    try:
        raw = headers.get("Content-Length") or headers.get("content-length")
        return raw is not None and int(raw) > MAX_RESPONSE_BYTES
    except (ValueError, TypeError):
        return False


async def _parse_json(resp) -> Any:
    """Parse JSON from either a curl_cffi or aiohttp response."""
    if resp is NOT_MODIFIED:
        return {}  # 304 Not Modified — no new data
    if _declared_too_large(resp):
        raise ValueError(f"response exceeds max size ({MAX_RESPONSE_BYTES} bytes)")
    if HAS_CURL_CFFI and hasattr(resp, "status_code"):
        # curl_cffi responses have .json() as a sync method
        return resp.json()
    # aiohttp responses have .json() as an async method
    return await resp.json()


def _record_parse_failure(ats: str, slug: str, message: str) -> None:
    record_request_failure(**classify_failure(error=message, ats=ats, slug=slug))


@dataclass
class NormalizedJob:
    """Common job format across all ATS platforms."""

    title: str
    company: str
    location: str
    url: str
    date_posted: str  # ISO string or relative ("3 hours ago")
    source_ats: str  # greenhouse, lever, ashby, etc.
    job_id: str  # Unique ID (from ATS or generated hash)
    first_seen: str = ""  # When we first ingested it
    keywords_matched: list[str] = field(default_factory=list)
    description: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    experience_years: int | None = None
    remote_ok: str | None = None  # 'remote' | 'hybrid' | 'onsite'
    job_type: str | None = None  # 'full_time' | 'contract' | 'internship' | 'part_time'
    seniority_level: str | None = None  # 'intern' | 'entry' | 'mid' | 'senior' | 'staff' | 'principal' | 'director'
    visa_sponsorship: int | None = None  # 1=yes, 0=no, None=unknown
    tech_stack: list | None = None  # ["Python", "React", "AWS"]

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def dedup_key(self) -> str:
        """Unique key for dedup: hash of title + company + location."""
        raw = f"{self.title}|{self.company}|{self.location}".lower().strip()
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── Pre-compiled enrichment patterns ────────────────────────────────

_REMOTE_PATTERNS = [
    (re.compile(r"\bfully[\s-]remote\b", re.I), "remote"),
    (re.compile(r"\bremote[\s-]first\b", re.I), "remote"),
    (re.compile(r"\bwork from home\b|\bwfh\b", re.I), "remote"),
    (re.compile(r"\b100%\s*remote\b", re.I), "remote"),
    (re.compile(r"\bhybrid\b", re.I), "hybrid"),
    (re.compile(r"\bonsite\b|\bon[\s-]site\b|\bin[\s-]office\b", re.I), "onsite"),
]

_SENIORITY_MAP = [
    (re.compile(r"\bintern\b|\binternship\b", re.I), "intern"),
    (re.compile(r"\bjunior\b|\bjr\.?\b|\bentry[\s-]level\b|\bnew\s+grad\b", re.I), "entry"),
    (re.compile(r"\bprincipal\b", re.I), "principal"),
    (re.compile(r"\bstaff\b", re.I), "staff"),
    (re.compile(r"\bdirector\b", re.I), "director"),
    (re.compile(r"\bsenior\b|\bsr\.?\b|\blead\b", re.I), "senior"),
]

_JOB_TYPE_PATTERNS = [
    (re.compile(r"\binternship\b|\bintern\b", re.I), "internship"),
    (re.compile(r"\bcontract\b|\bcontractor\b|\bcontract[\s-]to[\s-]hire\b", re.I), "contract"),
    (re.compile(r"\bpart[\s-]time\b", re.I), "part_time"),
    (re.compile(r"\bfull[\s-]time\b", re.I), "full_time"),
]

_NO_SPONSORSHIP = re.compile(
    r"(not\s+able|unable|will\s+not|cannot|do\s+not|does\s+not|won\'t|cannot)\s+"
    r"(to\s+)?(provide|offer|sponsor|support)",
    re.I,
)
_SPONSORSHIP_YES = re.compile(
    r"(visa\s+(sponsorship|support|assistance|available)|"
    r"sponsor\s+(h[\s-]?1[\s-]?b|work\s+visa|visa)|"
    r"we\s+(do\s+)?sponsor|h[\s-]?1[\s-]?b\s+transfer|"
    r"candidates\s+who\s+(require|need)\s+(visa|sponsorship))",
    re.I,
)

# Top-60 tech vocabulary for exact-word matching
_TECH_VOCAB = {
    # Languages
    "Python",
    "TypeScript",
    "JavaScript",
    "Go",
    "Rust",
    "Java",
    "Scala",
    "C++",
    "C#",
    "Ruby",
    "Swift",
    "Kotlin",
    "R",
    "MATLAB",
    "Julia",
    # ML / AI
    "PyTorch",
    "TensorFlow",
    "JAX",
    "Keras",
    "LangChain",
    "LlamaIndex",
    "scikit-learn",
    "XGBoost",
    "Spark",
    "Hadoop",
    "MLflow",
    "Ray",
    "Triton",
    "Databricks",
    "Hugging Face",
    # Cloud / DevOps
    "AWS",
    "GCP",
    "Azure",
    "Kubernetes",
    "Docker",
    "Terraform",
    "Airflow",
    # Databases
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "Redis",
    "Elasticsearch",
    "Snowflake",
    "BigQuery",
    "Redshift",
    "DynamoDB",
    "Cassandra",
    "Pinecone",
    "Weaviate",
    # Frameworks / Other
    "React",
    "Next.js",
    "FastAPI",
    "Django",
    "Flask",
    "Spring",
    "Rails",
    "GraphQL",
    "dbt",
    "Kafka",
    "Flink",
}
# Build case-insensitive lookup: lowercase → canonical form
_TECH_LOWER = {t.lower(): t for t in _TECH_VOCAB}
# Pre-compiled word-boundary pattern for each term
_TECH_PATTERNS = [(re.compile(r"\b" + re.escape(t) + r"\b", re.I), canonical) for t, canonical in _TECH_LOWER.items()]


def _extract_enrichments(job: NormalizedJob) -> NormalizedJob:
    """
    Extract remote_ok, job_type, seniority_level, visa_sponsorship, and
    tech_stack from the job title + description. Called from _enrich_job().
    """
    title = job.title or ""
    desc = job.description or ""
    location = job.location or ""
    combined = f"{title} {desc}"

    # ── Remote status ──────────────────────────────────────────────
    # Check location string first (most reliable), then description
    if not job.remote_ok:
        loc_lower = location.lower()
        if "remote" in loc_lower:
            job.remote_ok = "hybrid" if "hybrid" in loc_lower else "remote"
        else:
            for pattern, value in _REMOTE_PATTERNS:
                if pattern.search(combined):
                    job.remote_ok = value
                    break

    # ── Job type ───────────────────────────────────────────────────
    if not job.job_type:
        for pattern, value in _JOB_TYPE_PATTERNS:
            if pattern.search(combined):
                job.job_type = value
                break
        if not job.job_type:
            job.job_type = "full_time"  # default assumption

    # ── Seniority level ────────────────────────────────────────────
    if not job.seniority_level:
        for pattern, value in _SENIORITY_MAP:
            if pattern.search(title):  # title only — more reliable
                job.seniority_level = value
                break
        if not job.seniority_level:
            job.seniority_level = "mid"  # default when not specified

    # ── Visa sponsorship ───────────────────────────────────────────
    if job.visa_sponsorship is None and desc:
        if _NO_SPONSORSHIP.search(desc):
            job.visa_sponsorship = 0
        elif _SPONSORSHIP_YES.search(desc):
            job.visa_sponsorship = 1

    # ── Tech stack ─────────────────────────────────────────────────
    if not job.tech_stack and desc:
        found = []
        seen = set()
        for pattern, canonical in _TECH_PATTERNS:
            if canonical not in seen and pattern.search(desc):
                found.append(canonical)
                seen.add(canonical)
        job.tech_stack = found if found else None

    return job


def _enrich_job(job: NormalizedJob) -> NormalizedJob:
    """Extract salary, experience, and classification signals from the job description."""
    if not job.description:
        # Still extract seniority from title even without description
        _extract_enrichments(job)
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

    _extract_enrichments(job)
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
        rate_limiter: RateLimiter | None = None,
    ) -> list[NormalizedJob]:
        url = GreenhouseAdapter.BASE_URL.format(slug=slug)
        resp = await fetch_with_retry(
            session,
            "GET",
            url,
            rate_limiter=rate_limiter,
            log_tag=f"greenhouse/{slug}",
            params={"content": "true"},
        )
        if resp is NOT_MODIFIED:
            return []  # No changes since last scrape — skip processing
        if not resp:
            return []

        try:
            data = await _parse_json(resp)
        except Exception as e:
            _log(f"[greenhouse/{slug}] JSON decode error: {e}", "WARN")
            _record_parse_failure("greenhouse", slug, f"JSON decode error: {e}")
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
        rate_limiter: RateLimiter | None = None,
    ) -> list[NormalizedJob]:
        url = LeverAdapter.BASE_URL.format(slug=slug)
        resp = await fetch_with_retry(
            session,
            "GET",
            url,
            rate_limiter=rate_limiter,
            log_tag=f"lever/{slug}",
        )
        if resp is NOT_MODIFIED:
            return []  # No changes since last scrape — skip processing
        if not resp:
            return []

        try:
            data = await _parse_json(resp)
        except Exception as e:
            _log(f"[lever/{slug}] JSON decode error: {e}", "WARN")
            _record_parse_failure("lever", slug, f"JSON decode error: {e}")
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
                date_posted=datetime.fromtimestamp(created_at / 1000, tz=timezone.utc).isoformat()
                if created_at
                else "",
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
        rate_limiter: RateLimiter | None = None,
    ) -> list[NormalizedJob]:
        url = AshbyAdapter.BASE_URL.format(slug=slug)
        resp = await fetch_with_retry(
            session,
            "GET",
            url,
            rate_limiter=rate_limiter,
            log_tag=f"ashby/{slug}",
        )
        if resp is NOT_MODIFIED:
            return []  # No changes since last scrape — skip processing
        if not resp:
            return []

        try:
            data = await _parse_json(resp)
        except Exception as e:
            _log(f"[ashby/{slug}] JSON decode error: {e}", "WARN")
            _record_parse_failure("ashby", slug, f"JSON decode error: {e}")
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
        rate_limiter: RateLimiter | None = None,
    ) -> list[NormalizedJob]:
        url = SmartRecruitersAdapter.BASE_URL.format(slug=slug)
        all_jobs = []
        offset = 0
        limit = 100
        max_pages = 50  # safety cap (≤5,000 jobs/company); guards against a server that ignores offset

        for _page in range(max_pages):
            resp = await fetch_with_retry(
                session,
                "GET",
                url,
                rate_limiter=rate_limiter,
                log_tag=f"smartrecruiters/{slug}",
                params={"limit": limit, "offset": offset},
            )
            if not resp:
                break

            try:
                data = await _parse_json(resp)
            except Exception as e:
                _log(f"[smartrecruiters/{slug}] Pagination error at offset {offset}: {e}", "WARN")
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
        else:
            _log(f"[smartrecruiters/{slug}] Hit pagination cap ({max_pages} pages); stopping early.", "WARN")

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
        rate_limiter: RateLimiter | None = None,
    ) -> list[NormalizedJob]:
        url = BambooHRAdapter.BASE_URL.format(slug=slug)
        resp = await fetch_with_retry(
            session,
            "GET",
            url,
            rate_limiter=rate_limiter,
            log_tag=f"bamboohr/{slug}",
            headers={"Accept": "application/json"},
        )
        if not resp:
            return []

        # Inactive companies redirect to BambooHR homepage (HTML).
        # Detect non-JSON content-type to avoid parse errors.
        ct = ""
        if hasattr(resp, "headers"):
            ct = (resp.headers.get("content-type") or "") if hasattr(resp.headers, "get") else ""
        if ct and "json" not in ct and "javascript" not in ct:
            _log(f"[bamboohr/{slug}] HTML response — company likely migrated off BambooHR (ct={ct})", "WARN")
            _record_parse_failure("bamboohr", slug, f"HTML response content-type={ct}")
            return []

        try:
            data = await _parse_json(resp)
        except Exception as e:
            _log(f"[bamboohr/{slug}] JSON decode error: {e}", "WARN")
            _record_parse_failure("bamboohr", slug, f"JSON decode error: {e}")
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

    # Common Workday site names to probe when the URL-derived site returns 422
    _COMMON_SITES = ("External", "Jobs", "Careers", "careers", "external")

    @staticmethod
    async def _try_cxs(session, base_url, tenant, site, payload, rate_limiter):
        """Attempt a single CXS API call. Returns (response_data, api_url) or (None, url)."""
        api_url = f"{base_url}/wday/cxs/{tenant}/{site}/jobs"
        resp = await fetch_with_retry(
            session,
            "POST",
            api_url,
            rate_limiter=rate_limiter,
            log_tag=f"workday/{tenant}",
            json=payload,
            max_retries=0,  # Don't retry probes
        )
        if resp:
            status = resp.status_code if hasattr(resp, "status_code") else resp.status
            if status == 200:
                try:
                    data = await _parse_json(resp)
                    return data, api_url
                except Exception:
                    pass
        return None, api_url

    @staticmethod
    async def fetch(
        session,
        slug: str,
        company: str,
        rate_limiter: RateLimiter | None = None,
    ) -> list[NormalizedJob]:
        parts = slug.split(":")
        if len(parts) != 3:
            _log(f"[workday/{slug}] Invalid slug format (expected tenant:shard:site)", "WARN")
            _record_parse_failure("workday", slug, "Invalid slug format")
            return []
        tenant, shard, site = parts

        base_url = f"https://{tenant}.wd{shard}.myworkdayjobs.com"

        payload = {
            "appliedFacets": {},
            "limit": 20,
            "offset": 0,
            "searchText": "",
        }

        # First try the site from the slug
        data, api_url = await WorkdayAdapter._try_cxs(
            session,
            base_url,
            tenant,
            site,
            payload,
            rate_limiter,
        )

        # If that failed, probe common Workday site names regardless of the
        # input shape. Many boards publish locale-looking or stale site slugs.
        if data is None:
            for probe_site in WorkdayAdapter._COMMON_SITES:
                if probe_site.lower() == site.lower():
                    continue
                data, api_url = await WorkdayAdapter._try_cxs(
                    session,
                    base_url,
                    tenant,
                    probe_site,
                    payload,
                    rate_limiter,
                )
                if data is not None:
                    _log(f"[workday/{tenant}] Probed site '{probe_site}' succeeded")
                    site = probe_site
                    break
            if data is None:
                _record_parse_failure("workday", slug, "Workday site probe failed")
                return []

        if data is None:
            _record_parse_failure("workday", slug, "Workday CXS discovery failed")
            return []
        record_target_metadata(workday_site=site)

        all_jobs = []

        # Process first page (already fetched)
        job_postings = data.get("jobPostings", [])
        total = data.get("total", 0)
        all_jobs.extend(WorkdayAdapter._parse_postings(job_postings, company, base_url, site))

        # Fetch remaining pages
        offset = 20
        max_pages = 200  # 4,000 jobs max (was 50/1,000 — too low for Boeing, Amazon, etc.)
        while offset < min(total, max_pages * 20) and job_postings:
            payload["offset"] = offset
            resp = await fetch_with_retry(
                session,
                "POST",
                api_url,
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

            all_jobs.extend(WorkdayAdapter._parse_postings(job_postings, company, base_url, site))

            total = data.get("total", 0)
            offset += 20
            if offset >= total:
                break

        if offset >= max_pages * 20 and total > max_pages * 20:
            _log(f"[workday/{tenant}] Hit {max_pages}-page cap ({max_pages * 20} jobs) — {total} total exist", "WARN")

        return all_jobs

    @staticmethod
    def _parse_postings(job_postings, company, base_url, site):
        """Parse a page of Workday job postings into NormalizedJob objects."""
        jobs = []
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
            jobs.append(job)
        return jobs


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
        rate_limiter: RateLimiter | None = None,
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
                session,
                "POST",
                url,
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
                _record_parse_failure("workable", slug, f"JSON decode error: {e}")
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
        rate_limiter: RateLimiter | None = None,
    ) -> list[NormalizedJob]:
        url = RipplingAdapter.BASE_URL.format(slug=slug)
        resp = await fetch_with_retry(
            session,
            "GET",
            url,
            rate_limiter=rate_limiter,
            log_tag=f"rippling/{slug}",
        )
        if not resp:
            return []

        try:
            data = await _parse_json(resp)
        except Exception as e:
            _log(f"[rippling/{slug}] JSON decode error: {e}", "WARN")
            _record_parse_failure("rippling", slug, f"JSON decode error: {e}")
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
# GEM ATS ADAPTER
# ═══════════════════════════════════════════════════════════════════════


class GemAdapter:
    """Gem Job Board API: job-boards.gem.com/{slug}/jobs"""

    BASE_URL = "https://job-boards.gem.com/{slug}/jobs"

    @staticmethod
    async def fetch(
        session,
        slug: str,
        company: str,
        rate_limiter: RateLimiter | None = None,
    ) -> list[NormalizedJob]:
        url = GemAdapter.BASE_URL.format(slug=slug)
        resp = await fetch_with_retry(
            session,
            "GET",
            url,
            rate_limiter=rate_limiter,
            log_tag=f"gem/{slug}",
        )
        if not resp:
            return []

        try:
            data = await _parse_json(resp)
        except Exception as e:
            _log(f"[gem/{slug}] JSON decode error: {e}", "WARN")
            _record_parse_failure("gem", slug, f"JSON decode error: {e}")
            return []

        if not isinstance(data, dict):
            return []

        raw_jobs = data.get("jobs", data.get("data", []))
        if not isinstance(raw_jobs, list):
            return []

        jobs = []
        for j in raw_jobs:
            if not isinstance(j, dict):
                continue

            location = j.get("location", "") or j.get("city", "") or "Unknown"
            if isinstance(location, dict):
                parts = [location.get("city", ""), location.get("state", ""), location.get("country", "")]
                location = ", ".join(p for p in parts if p) or "Unknown"

            job_id = str(j.get("id", "") or j.get("req_id", ""))
            apply_url = j.get("apply_url") or j.get("url") or f"https://job-boards.gem.com/{slug}/jobs/{job_id}"

            description = _strip_html(j.get("description", "") or j.get("content", "")) or None

            job = NormalizedJob(
                title=j.get("title", "") or j.get("name", ""),
                company=company,
                location=location,
                url=apply_url,
                date_posted=j.get("created_at", "") or j.get("posted_at", ""),
                source_ats="gem",
                job_id=job_id,
                description=description,
            )
            jobs.append(_enrich_job(job))

        return jobs


# ═══════════════════════════════════════════════════════════════════════
# ORACLE RECRUITING CLOUD (ORC / Fusion) ADAPTER
# ═══════════════════════════════════════════════════════════════════════


class OracleAdapter:
    """Oracle Recruiting Cloud (Fusion) public career-site REST API.

    Endpoint: https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
    Slug format: "host:siteNumber"  e.g. "eeho.fa.us2.oraclecloud.com:CX_1"
    `siteNumber` defaults to CX_1 (Oracle's default career site) when omitted.

    Covers the large non-Workday enterprise segment (Oracle/PeopleSoft shops).
    Same paginated-JSON shape as Workday: a first page carries TotalJobsCount,
    then offset paging until drained.
    """

    PAGE_SIZE = 25
    MAX_PAGES = 80  # 2,000-req safety cap per tenant

    @staticmethod
    def _build_url(host: str, site: str, limit: int, offset: int) -> str:
        # ORC finder uses raw ';' and ',' sub-delims; curl_cffi sends the URL
        # verbatim (production path) and yarl preserves these in the query.
        finder = f"findReqs;siteNumber={site},limit={limit},offset={offset},sortBy=POSTING_DATES_DESC"
        expand = "requisitionList.secondaryLocations,flexFieldsFacet.values"
        return (
            f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
            f"?onlyData=true&expand={expand}&finder={finder}"
        )

    @staticmethod
    async def fetch(
        session,
        slug: str,
        company: str,
        rate_limiter: RateLimiter | None = None,
    ) -> list[NormalizedJob]:
        parts = slug.split(":")
        host = parts[0].strip().strip("/")
        site = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "CX_1"
        if not host:
            _log(f"[oracle/{slug}] Invalid slug (expected host:siteNumber)", "WARN")
            _record_parse_failure("oracle", slug, "Invalid slug (missing host)")
            return []

        record_target_metadata(oracle_site=site)

        all_jobs: list[NormalizedJob] = []
        offset = 0
        for _ in range(OracleAdapter.MAX_PAGES):
            url = OracleAdapter._build_url(host, site, OracleAdapter.PAGE_SIZE, offset)
            resp = await fetch_with_retry(
                session,
                "GET",
                url,
                rate_limiter=rate_limiter,
                log_tag=f"oracle/{host}",
                headers={"Accept": "application/json"},
            )
            if not resp:
                break

            try:
                data = await _parse_json(resp)
            except Exception as e:
                _log(f"[oracle/{host}] JSON decode error: {e}", "WARN")
                _record_parse_failure("oracle", slug, f"JSON decode error: {e}")
                break

            items = data.get("items") or []
            if not items:
                break
            block = items[0] or {}
            reqs = block.get("requisitionList") or []
            if not reqs:
                break

            all_jobs.extend(OracleAdapter._parse_reqs(reqs, company, host, site))

            total = block.get("TotalJobsCount") or 0
            offset += OracleAdapter.PAGE_SIZE
            if offset >= total:
                break

        return all_jobs

    @staticmethod
    def _parse_reqs(reqs, company, host, site):
        """Parse a page of ORC requisitions into NormalizedJob objects."""
        jobs = []
        for r in reqs:
            title = (r.get("Title") or "").strip()
            job_id = str(r.get("Id") or "").strip()
            if not title or not job_id:
                continue

            location = (r.get("PrimaryLocation") or "").strip()
            secondary = r.get("secondaryLocations") or []
            if secondary:
                extra = [s.get("Name", "").strip() for s in secondary if isinstance(s, dict) and s.get("Name")]
                extra = [e for e in extra if e]
                if extra:
                    location = ", ".join([location, *extra]) if location else ", ".join(extra)
            location = location or "Unknown"

            job = NormalizedJob(
                title=title,
                company=company,
                location=location,
                url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{job_id}",
                date_posted=(r.get("PostedDate") or "").strip(),
                source_ats="oracle",
                job_id=job_id,
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
    "gem": GemAdapter,
    "oracle": OracleAdapter,
}


def get_adapter(ats: str):
    """Return the adapter class for the given ATS platform name, or None."""
    return ADAPTERS.get(ats.lower()) if ats else None


async def fetch_company_jobs(
    session,
    company: str,
    ats: str,
    slug: str,
    rate_limiter: RateLimiter | None = None,
) -> list[NormalizedJob]:
    """Fetch jobs for a single company using the appropriate adapter."""
    adapter = ADAPTERS.get(ats)
    if not adapter:
        _log(f"No adapter for ATS platform '{ats}' (company: {company})", "WARN")
        _record_parse_failure(ats or "unknown", slug, "No adapter available")
        return []
    jobs = await adapter.fetch(session, slug, company, rate_limiter=rate_limiter)
    failure = consume_last_failure()
    if jobs or not failure or failure.get("category") != "bad_target":
        if failure:
            record_request_failure(**failure)
        return jobs

    for alias_ats, alias_slug in get_ats_slug_aliases(company, ats, slug):
        alias_adapter = ADAPTERS.get(alias_ats)
        if not alias_adapter:
            continue
        _log(f"[{ats}/{slug}] Trying repaired slug {alias_ats}/{alias_slug} for {company}", "INFO")
        alias_jobs = await alias_adapter.fetch(session, alias_slug, company, rate_limiter=rate_limiter)
        alias_failure = consume_last_failure()
        if alias_jobs:
            record_target_metadata(resolved_ats=alias_ats, resolved_slug=alias_slug)
            _log(f"[{ats}/{slug}] Repaired via {alias_ats}/{alias_slug}: {len(alias_jobs)} jobs", "INFO")
            return alias_jobs
        if alias_failure:
            failure = alias_failure

    record_request_failure(**failure)
    return []
