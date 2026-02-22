"""
Parallel ATS Job Ingestor.

Fetches jobs from all companies in the registry concurrently using asyncio + aiohttp.
Applies role filtering, deduplication, and 24hr time filtering.

Usage:
    # As a library
    from scripts.ingestion.parallel_ingestor import run_cycle
    results = asyncio.run(run_cycle())

    # Standalone test
    python scripts/ingestion/parallel_ingestor.py
"""

import asyncio
import json
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import sys
import re
import aiohttp

# Fix imports for both standalone and module usage
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ingestion.ats_adapters import fetch_company_jobs, NormalizedJob
from scripts.ingestion.role_filter import matches_target_role
from scripts.ingestion.us_filter import is_us_location
from scripts.ingestion.job_board_adapters import fetch_all_job_boards
from scripts.ingestion.github_parser import fetch_all_github_repos
from scripts.ingestion.aggregator_adapters import fetch_all_aggregators
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
REGISTRY_FILE = CONFIG_DIR / "company_registry.json"
JOBS_DB_FILE = DATA_DIR / "jobs.json"

# ── Tuning ────────────────────────────────────────────────────────────
MAX_CONCURRENT = 25        # Max parallel HTTP requests
REQUEST_TIMEOUT = 30       # Seconds per request
MAX_RETRIES = 2            # Retry failed fetches
RETRY_DELAY = 2            # Seconds between retries


def _log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"{ts} | {level} | [ingestor] {msg}"
    print(entry)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOGS_DIR / "system.log", "a", encoding="utf-8") as f:
        f.write(entry + "\n")


# ═══════════════════════════════════════════════════════════════════════
# REGISTRY
# ═══════════════════════════════════════════════════════════════════════

def load_registry() -> list[dict[str, str]]:
    """Load company registry from config/company_registry.json."""
    if not REGISTRY_FILE.exists():
        _log("No company_registry.json found!", "ERROR")
        return []
    try:
        data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return data.get("companies", [])
    except (json.JSONDecodeError, OSError) as e:
        _log(f"Failed to load registry: {e}", "ERROR")
        return []


# ═══════════════════════════════════════════════════════════════════════
# DEDUP ENGINE
# ═══════════════════════════════════════════════════════════════════════

def load_known_jobs() -> dict[str, Any]:
    """Load the jobs database with known job IDs."""
    if not JOBS_DB_FILE.exists():
        return {"jobs": {}, "last_updated": None, "run_history": []}
    try:
        return json.loads(JOBS_DB_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"jobs": {}, "last_updated": None, "run_history": []}


def save_jobs_db(db: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DB_FILE.write_text(json.dumps(db, indent=2, default=str), encoding="utf-8")


def dedup_jobs(
    new_jobs: list[NormalizedJob],
    known_keys: set[str],
) -> list[NormalizedJob]:
    """Remove jobs whose dedup_key is already known."""
    seen = set()
    unique = []
    for job in new_jobs:
        key = job.dedup_key
        if key not in known_keys and key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


# ═══════════════════════════════════════════════════════════════════════
# 24HR TIME FILTER
# ═══════════════════════════════════════════════════════════════════════

def is_within_window(date_str: str, window_hours: int = 24) -> bool:
    """Check if a date string is within the specified time window.

    Args:
        date_str: Date string (ISO, Unix timestamp, or relative).
        window_hours: Number of hours to look back (default 24).

    Returns True if date is unparseable (include rather than exclude).
    """
    if not date_str:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    # Try ISO format
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(date_str, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed >= cutoff
        except ValueError:
            continue

    # Try unix timestamp
    try:
        ts = float(date_str)
        if ts > 1e12:
            ts = ts / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc) >= cutoff
    except (ValueError, OSError):
        pass

    # Basic relative date parsing (e.g., "30+ Days Ago", "3 days ago")
    date_str_lower = date_str.lower()
    
    # Anything with month/year is definitely out of the 24h window
    if "month" in date_str_lower or "year" in date_str_lower:
        return window_hours >= 720  # True only if window >= 30 days

    # Extract days (handles "3 days", "30+ days", etc)
    match = re.search(r'(\d+)\+?\s*day', date_str_lower)
    if match:
        days = int(match.group(1))
        return (days * 24) <= window_hours

    # Relative dates like "3 hours ago" or unparseable ones - include them
    return True


# ═══════════════════════════════════════════════════════════════════════
# PARALLEL WORKER
# ═══════════════════════════════════════════════════════════════════════

async def _fetch_with_retry(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    company: dict[str, str],
) -> tuple[str, list[NormalizedJob], str | None]:
    """Fetch jobs for one company with retry and semaphore.

    Returns: (company_name, jobs, error_msg_or_None)
    """
    name = company["company"]
    ats = company["ats"]
    slug = company["slug"]

    async with semaphore:
        for attempt in range(MAX_RETRIES + 1):
            try:
                jobs = await fetch_company_jobs(session, name, ats, slug)
                return (name, jobs, None)
            except Exception as e:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    return (name, [], str(e))

    return (name, [], "Max retries exceeded")


async def run_cycle(window_hours: int = 24) -> dict[str, Any]:
    """Execute one full ingestion cycle.

    1. Load registry
    2. Fetch all companies in parallel
    3. Filter by role keywords
    4. Filter by US location
    5. Filter by time window
    6. Dedup against known jobs
    7. Store results

    Args:
        window_hours: How far back to look (24 for midnight sweep, 1 for regular).

    Returns:
        Dict with cycle results.
    """
    start = datetime.now()
    _log("========== INGESTION CYCLE START ==========")

    # 1. Load registry
    registry = load_registry()
    if not registry:
        _log("Empty registry — nothing to ingest.", "WARN")
        return {"new_jobs": [], "total_fetched": 0, "total_filtered": 0,
                "total_new": 0, "companies_succeeded": 0, "companies_failed": 0,
                "errors": ["Empty registry"], "duration_seconds": 0}

    _log(f"Registry loaded: {len(registry)} companies")

    # 2. Parallel fetch
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, limit_per_host=5)

    all_jobs: list[NormalizedJob] = []
    errors: list[str] = []
    succeeded = 0
    failed = 0

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            _fetch_with_retry(session, semaphore, company)
            for company in registry
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))
                failed += 1
                continue

            name, jobs, error = result
            if error:
                errors.append(f"{name}: {error}")
                failed += 1
            else:
                succeeded += 1
                all_jobs.extend(jobs)

        # 2b. Fetch from job board APIs
        board_jobs, board_errors = await fetch_all_job_boards(session)
        all_jobs.extend(board_jobs)
        errors.extend(board_errors)
        if board_jobs:
            _log(f"Job boards: {len(board_jobs)} additional jobs from APIs/RSS")

        # 2c. Fetch from GitHub repos (temporarily disabled)
        # gh_jobs, gh_errors = await fetch_all_github_repos(session)
        # all_jobs.extend(gh_jobs)
        # errors.extend(gh_errors)
        # if gh_jobs:
        #     _log(f"GitHub repos: {len(gh_jobs)} additional jobs from repos")

        # 2d. Fetch from aggregator sites
        agg_jobs, agg_errors = await fetch_all_aggregators(session)
        all_jobs.extend(agg_jobs)
        errors.extend(agg_errors)
        if agg_jobs:
            _log(f"Aggregators: {len(agg_jobs)} additional jobs from sites")

    total_fetched = len(all_jobs)
    _log(f"Fetched {total_fetched} jobs from {succeeded} companies + job boards ({failed} failed)")

    # 3. Filter by role keywords
    filtered = []
    for job in all_jobs:
        matched = matches_target_role(job.title)
        if matched:
            job.keywords_matched = matched
            filtered.append(job)

    total_filtered = len(filtered)
    _log(f"Role filter: {total_filtered}/{total_fetched} jobs match target keywords")

    # 4. Filter by US location
    us_jobs = [j for j in filtered if is_us_location(j.location)]
    _log(f"US filter: {len(us_jobs)}/{total_filtered} jobs in United States")

    # 5. Filter by time window
    recent = [j for j in us_jobs if is_within_window(j.date_posted, window_hours)]
    _log(f"{window_hours}hr filter: {len(recent)}/{len(us_jobs)} jobs within window")

    # 5. Dedup
    db = load_known_jobs()
    known_keys = set(db.get("jobs", {}).keys())
    new_jobs = dedup_jobs(recent, known_keys)
    total_new = len(new_jobs)
    _log(f"Dedup: {total_new} new jobs (skipped {len(recent) - total_new} duplicates)")

    # 6. Store
    ts = datetime.now(timezone.utc).isoformat()
    for job in new_jobs:
        job.first_seen = ts
        db["jobs"][job.dedup_key] = job.to_dict()

    # Trim run history to last 200 entries
    run_entry = {
        "timestamp": ts,
        "fetched": total_fetched,
        "filtered": total_filtered,
        "new": total_new,
        "succeeded": succeeded,
        "failed": failed,
        "duration_s": round((datetime.now() - start).total_seconds(), 1),
    }
    history = db.get("run_history", [])
    history.append(run_entry)
    if len(history) > 200:
        history = history[-200:]
    db["run_history"] = history
    db["last_updated"] = ts

    save_jobs_db(db)

    elapsed = round((datetime.now() - start).total_seconds(), 1)
    _log(f"Cycle complete in {elapsed}s — {total_new} new jobs stored")
    _log("========== INGESTION CYCLE COMPLETE ==========")

    return {
        "new_jobs": [j.to_dict() for j in new_jobs],
        "total_fetched": total_fetched,
        "total_filtered": total_filtered,
        "total_new": total_new,
        "companies_succeeded": succeeded,
        "companies_failed": failed,
        "errors": errors[:20],  # Cap error list
        "duration_seconds": elapsed,
    }


# ═══════════════════════════════════════════════════════════════════════
# STANDALONE TEST
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    # Fix imports when running standalone
    sys.path.insert(0, str(PROJECT_ROOT))
    result = asyncio.run(run_cycle())
    print(f"\n{'='*50}")
    print(f"Companies succeeded: {result['companies_succeeded']}")
    print(f"Companies failed:    {result['companies_failed']}")
    print(f"Total fetched:       {result['total_fetched']}")
    print(f"After role filter:   {result['total_filtered']}")
    print(f"New (deduped):       {result['total_new']}")
    print(f"Duration:            {result['duration_seconds']}s")
    if result["errors"]:
        print(f"\nErrors ({len(result['errors'])}):")
        for e in result["errors"][:10]:
            print(f"  - {e}")
