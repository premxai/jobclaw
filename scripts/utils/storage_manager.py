"""
Storage Manager for AI Job Agent.

Manages persistent storage of job listings with:
  - Duplicate detection (by job_id or url)
  - New job detection (diff between runs)
  - Persistent state in data/google_jobs.json
  - Change history tracking
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
JOBS_FILE = DATA_DIR / "google_jobs.json"
RAW_FILE = DATA_DIR / "google_jobs_raw.json"


def _atomic_write(path: Path, content: str) -> None:
    """Atomic file write: temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=path.stem
    )
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        if path.exists():
            path.unlink()
        os.rename(tmp_path, str(path))
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def load_stored_jobs() -> dict[str, Any]:
    """Load the current jobs database.

    Returns:
        Dict with keys: 'jobs' (list), 'last_updated', 'total_count',
        'run_history' (list of change summaries).
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not JOBS_FILE.exists():
        return {
            "jobs": [],
            "last_updated": None,
            "total_count": 0,
            "run_history": [],
        }
    try:
        return json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "jobs": [],
            "last_updated": None,
            "total_count": 0,
            "run_history": [],
        }


def load_raw_results() -> list[dict[str, Any]]:
    """Load raw agent output from data/google_jobs_raw.json.

    Returns:
        List of job dicts from latest scrape, or empty list.
    """
    if not RAW_FILE.exists():
        return []
    try:
        data = json.loads(RAW_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _get_job_key(job: dict[str, Any]) -> str:
    """Generate a unique key for a job listing."""
    return job.get("job_id") or job.get("url") or f"{job.get('title', '')}|{job.get('location', '')}"


def detect_duplicates(
    new_jobs: list[dict[str, Any]],
    existing_jobs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate new jobs from duplicates.

    Args:
        new_jobs: Jobs from latest scrape.
        existing_jobs: Jobs already in storage.

    Returns:
        Tuple of (unique_new_jobs, duplicate_jobs).
    """
    existing_keys = {_get_job_key(j) for j in existing_jobs}
    unique = []
    dupes = []

    for job in new_jobs:
        key = _get_job_key(job)
        if key in existing_keys:
            dupes.append(job)
        else:
            unique.append(job)

    return unique, dupes


def detect_changes(
    new_jobs: list[dict[str, Any]],
    existing_jobs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare runs to detect changes.

    Returns:
        Dict with: 'new_count', 'duplicate_count', 'removed_count',
        'new_jobs', 'removed_jobs'.
    """
    new_keys = {_get_job_key(j) for j in new_jobs}
    existing_keys = {_get_job_key(j) for j in existing_jobs}

    added_keys = new_keys - existing_keys
    removed_keys = existing_keys - new_keys

    added = [j for j in new_jobs if _get_job_key(j) in added_keys]
    removed = [j for j in existing_jobs if _get_job_key(j) in removed_keys]

    return {
        "new_count": len(added),
        "duplicate_count": len(new_keys & existing_keys),
        "removed_count": len(removed),
        "new_jobs": added,
        "removed_jobs": removed,
    }


def store_jobs(new_jobs: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge new jobs into persistent storage.

    Detects duplicates, appends only new jobs, tracks run history.

    Args:
        new_jobs: List of job dicts from latest scrape.

    Returns:
        Change summary dict.
    """
    db = load_stored_jobs()
    existing = db.get("jobs", [])

    changes = detect_changes(new_jobs, existing)
    unique_new, _ = detect_duplicates(new_jobs, existing)

    # Add timestamp to new jobs
    ts = datetime.now(timezone.utc).isoformat()
    for job in unique_new:
        job["first_seen"] = ts

    # Merge: existing + new unique
    merged = existing + unique_new

    # Build run history entry
    run_entry = {
        "timestamp": ts,
        "scraped_count": len(new_jobs),
        "new_count": changes["new_count"],
        "duplicate_count": changes["duplicate_count"],
        "removed_count": changes["removed_count"],
        "total_after": len(merged),
    }

    run_history = db.get("run_history", [])
    run_history.append(run_entry)

    # Keep last 100 history entries
    if len(run_history) > 100:
        run_history = run_history[-100:]

    # Save
    updated_db = {
        "jobs": merged,
        "last_updated": ts,
        "total_count": len(merged),
        "run_history": run_history,
    }
    _atomic_write(JOBS_FILE, json.dumps(updated_db, indent=2))

    return changes
