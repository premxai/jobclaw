"""
Pydantic v2 response models for the JobClaw API.
"""

from pydantic import BaseModel, Field


class JobResponse(BaseModel):
    """A job listing."""

    internal_hash: str
    job_id: str = ""
    title: str
    company: str
    location: str = ""
    url: str = ""
    date_posted: str = ""
    source_ats: str = ""
    first_seen: str | None = None
    status: str = "unposted"
    keywords_matched: list[str] = Field(default_factory=list)
    description: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    experience_years: int | None = None
    is_active: bool = True
    last_seen_at: str | None = None


class JobListResponse(BaseModel):
    """Paginated list of jobs."""

    jobs: list[JobResponse]
    total: int
    page: int
    per_page: int
    has_more: bool


class CompanyResponse(BaseModel):
    """A company with job count."""

    company: str
    source_ats: str
    job_count: int
    latest_job: str | None = None


class StatsOverview(BaseModel):
    """System-wide statistics."""

    total_jobs: int
    active_jobs: int
    inactive_jobs: int
    unposted_jobs: int
    posted_jobs: int
    companies: int
    platforms: dict[str, int]  # ats → count
    jobs_last_24h: int
    jobs_last_7d: int


class ScraperRunResponse(BaseModel):
    """A single scraper run log entry."""

    id: int
    script_name: str
    timestamp: str
    companies_fetched: int
    new_jobs_found: int
    duration_s: float
    errors: str | None = None


class HealthResponse(BaseModel):
    """API health check."""

    status: str = "ok"
    version: str = "4.0.0"
    database: str = "connected"
    total_jobs: int = 0
