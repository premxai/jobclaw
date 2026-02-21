"""
GitHub Job Repo Parsers.

Fetches and parses job listings from GitHub repositories that track
new grad, internship, and AI/ML positions. Each repo uses a different
format — some have listings.json, others use markdown tables.

Supported repos:
  - SimplifyJobs/New-Grad-Positions (JSON backend)
  - SimplifyJobs/Summer2026-Internships (JSON backend)
  - speedyapply/2026-AI-College-Jobs (markdown table)
  - jobright-ai repos (markdown table)
  - zapplyjobs repos (markdown table)
"""

import re
from datetime import datetime, timezone, timedelta
from typing import Optional
import aiohttp

from scripts.ingestion.ats_adapters import NormalizedJob


# ═══════════════════════════════════════════════════════════════════════
# SIMPLIFY JOBS (JSON backend)
# ═══════════════════════════════════════════════════════════════════════

class SimplifyJobsParser:
    """Parses listings.json from SimplifyJobs repos (New-Grad + Internships).

    The JSON contains a list of objects with fields:
    - company_name, title, locations[], url, date_posted, is_visible, etc.
    """

    REPOS = [
        {
            "owner": "SimplifyJobs",
            "repo": "New-Grad-Positions",
            "branch": "dev",
            "label": "new-grad",
        },
        {
            "owner": "SimplifyJobs",
            "repo": "Summer2026-Internships",
            "branch": "dev",
            "label": "internship",
        },
    ]

    @staticmethod
    async def fetch(session: aiohttp.ClientSession) -> list[NormalizedJob]:
        all_jobs = []

        for repo_info in SimplifyJobsParser.REPOS:
            url = (
                f"https://raw.githubusercontent.com/{repo_info['owner']}/"
                f"{repo_info['repo']}/{repo_info['branch']}/"
                f".github/scripts/listings.json"
            )
            try:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)

                if not isinstance(data, list):
                    continue

                for j in data:
                    # Skip inactive/hidden listings
                    if not j.get("is_visible", True):
                        continue
                    if j.get("active") is False:
                        continue

                    # Parse locations
                    locations = j.get("locations", [])
                    if isinstance(locations, list):
                        location = ", ".join(str(loc) for loc in locations[:3]) if locations else "Unknown"
                    else:
                        location = str(locations) if locations else "Unknown"

                    # Parse date
                    date_posted = j.get("date_posted", "")
                    if isinstance(date_posted, (int, float)):
                        try:
                            date_posted = datetime.fromtimestamp(
                                date_posted / 1000 if date_posted > 1e12 else date_posted,
                                tz=timezone.utc
                            ).isoformat()
                        except (ValueError, OSError):
                            date_posted = ""

                    company = j.get("company_name", "Unknown")
                    title = j.get("title", "")
                    job_url = j.get("url", "")

                    # Build simplify.jobs URL if no direct URL
                    if not job_url and j.get("id"):
                        job_url = f"https://simplify.jobs/p/{j['id']}"

                    all_jobs.append(NormalizedJob(
                        title=title,
                        company=company,
                        location=location,
                        url=job_url,
                        date_posted=date_posted,
                        source_ats=f"github-{repo_info['label']}",
                        job_id=str(j.get("id", f"{company}-{title}")),
                    ))

            except Exception:
                continue

        return all_jobs


# ═══════════════════════════════════════════════════════════════════════
# MARKDOWN TABLE REPOS
# ═══════════════════════════════════════════════════════════════════════

class MarkdownTableParser:
    """Parses markdown table format from various repos.

    Handles formats like:
    | Company | Role | Location | Link | Date |
    |---|---|---|---|---|
    | Google | SWE | NYC | [Apply](url) | Feb 2026 |
    """

    REPOS = [
        {
            "owner": "speedyapply",
            "repo": "2026-AI-College-Jobs",
            "branch": "main",
            "file": "README.md",
            "label": "ai-newgrad",
        },
        {
            "owner": "zapplyjobs",
            "repo": "New-Grad-Software-Engineering-Jobs-2026",
            "branch": "main",
            "file": "README.md",
            "label": "swe-newgrad",
        },
    ]

    @staticmethod
    async def fetch(session: aiohttp.ClientSession) -> list[NormalizedJob]:
        all_jobs = []

        for repo_info in MarkdownTableParser.REPOS:
            url = (
                f"https://raw.githubusercontent.com/{repo_info['owner']}/"
                f"{repo_info['repo']}/{repo_info['branch']}/{repo_info['file']}"
            )
            try:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        continue
                    text = await resp.text()

                # Parse markdown tables
                jobs = _parse_markdown_table(text, repo_info["label"])
                all_jobs.extend(jobs)

            except Exception:
                continue

        return all_jobs


def _parse_markdown_table(markdown: str, label: str) -> list[NormalizedJob]:
    """Extract job listings from markdown tables.

    Tries to identify columns: Company, Role/Title, Location, Link/URL, Date
    """
    jobs = []
    lines = markdown.split("\n")
    header_indices = {}  # column name -> index

    in_table = False
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            in_table = False
            header_indices = {}
            continue

        cells = [c.strip() for c in line.split("|")[1:-1]]  # Remove empty first/last

        # Skip separator lines
        if all(set(c) <= {"-", ":", " "} for c in cells):
            continue

        # Detect header row
        if not in_table:
            for i, cell in enumerate(cells):
                cl = cell.lower()
                if any(k in cl for k in ["company", "employer"]):
                    header_indices["company"] = i
                elif any(k in cl for k in ["role", "title", "position"]):
                    header_indices["title"] = i
                elif any(k in cl for k in ["location", "city"]):
                    header_indices["location"] = i
                elif any(k in cl for k in ["link", "url", "apply", "application"]):
                    header_indices["url"] = i
                elif any(k in cl for k in ["date", "posted", "added"]):
                    header_indices["date"] = i

            if header_indices:
                in_table = True
            continue

        # Parse data row
        if len(cells) < 2:
            continue

        company = cells[header_indices.get("company", 0)] if header_indices.get("company") is not None else ""
        title = cells[header_indices.get("title", 1)] if header_indices.get("title") is not None else ""
        location = cells[header_indices.get("location", 2)] if header_indices.get("location") is not None and len(cells) > header_indices["location"] else "Unknown"
        date = cells[header_indices.get("date", -1)] if header_indices.get("date") is not None and len(cells) > header_indices["date"] else ""

        # Extract URL from markdown link [text](url)
        url_cell = cells[header_indices.get("url", 3)] if header_indices.get("url") is not None and len(cells) > header_indices["url"] else ""
        url_match = re.search(r'\[([^\]]*)\]\(([^)]+)\)', url_cell)
        job_url = url_match.group(2) if url_match else ""

        # Also check for URLs in company/title cells
        if not job_url:
            for cell in cells:
                url_match = re.search(r'\[([^\]]*)\]\(([^)]+)\)', cell)
                if url_match and ("http" in url_match.group(2)):
                    job_url = url_match.group(2)
                    break

        # Clean markdown from company/title
        company = re.sub(r'\[([^\]]*)\]\([^)]+\)', r'\1', company).strip()
        title = re.sub(r'\[([^\]]*)\]\([^)]+\)', r'\1', title).strip()

        if not company and not title:
            continue

        # Skip rows with "closed" or strike-through
        if "~~" in line or "🔒" in line:
            continue

        jobs.append(NormalizedJob(
            title=title or "New Grad Position",
            company=company or "Unknown",
            location=location,
            url=job_url,
            date_posted=date,
            source_ats=f"github-{label}",
            job_id=f"{company}-{title}-{label}",
        ))

    return jobs


# ═══════════════════════════════════════════════════════════════════════
# COMBINED FETCHER
# ═══════════════════════════════════════════════════════════════════════

async def fetch_all_github_repos(session: aiohttp.ClientSession) -> tuple[list[NormalizedJob], list[str]]:
    """Fetch jobs from all GitHub repo sources.

    Returns:
        Tuple of (all_jobs, errors)
    """
    all_jobs = []
    errors = []

    # SimplifyJobs (JSON)
    try:
        jobs = await SimplifyJobsParser.fetch(session)
        all_jobs.extend(jobs)
    except Exception as e:
        errors.append(f"SimplifyJobs: {str(e)}")

    # Markdown table repos
    try:
        jobs = await MarkdownTableParser.fetch(session)
        all_jobs.extend(jobs)
    except Exception as e:
        errors.append(f"MarkdownRepos: {str(e)}")

    return all_jobs, errors
