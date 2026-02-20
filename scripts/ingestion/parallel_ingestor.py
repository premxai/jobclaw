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
import aiohttp

# Fix imports for both standalone and module usage
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ingestion.ats_adapters import fetch_company_jobs, NormalizedJob
from scripts.ingestion.role_filter import matches_target_role
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

def is_within_24h(date_str: str) -> bool:
    """Check if a date string is within the last 24 hours.

    Handles ISO dates, Unix timestamps, and relative dates.
    Returns True if date is unparseable (include rather than exclude).
    """
    if not date_str:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

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

    # Relative dates like "3 hours ago", "today" - include them
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


async def run_cycle() -> dict[str, Any]:
    """Execute one full ingestion cycle.

    1. Load registry
    2. Fetch all companies in parallel
    3. Filter by role keywords
    4. Filter by 24hr time window
    5. Dedup against known jobs
    6. Store results

    Returns:
        Dict with cycle results:
          - new_jobs: list of NormalizedJob dicts
          - total_fetched: int
          - total_filtered: int
          - total_new: int
          - companies_succeeded: int
          - companies_failed: int
          - errors: list of error strings
          - duration_seconds: float
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

    total_fetched = len(all_jobs)
    _log(f"Fetched {total_fetched} jobs from {succeeded} companies ({failed} failed)")

    # 3. Filter by role keywords
    filtered = []
    for job in all_jobs:
        matched = matches_target_role(job.title)
        if matched:
            job.keywords_matched = matched
            filtered.append(job)

    total_filtered = len(filtered)
    _log(f"Role filter: {total_filtered}/{total_fetched} jobs match target keywords")

    # 4. Filter by 24hr time window
    recent = [j for j in filtered if is_within_24h(j.date_posted)]
    _log(f"24hr filter: {len(recent)}/{total_filtered} jobs within window")

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
