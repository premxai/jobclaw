"""
Pydantic v2 response models for the JobClaw API.
"""

from datetime import datetime
from typing import Optional
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
    first_seen: Optional[str] = None
    status: str = "unposted"
    keywords_matched: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None
    experience_years: Optional[int] = None
    is_active: bool = True
    last_seen_at: Optional[str] = None


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
    latest_job: Optional[str] = None


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
    errors: Optional[str] = None


class HealthResponse(BaseModel):
    """API health check."""
    status: str = "ok"
    version: str = "4.0.0"
    database: str = "connected"
    total_jobs: int = 0
