"""
Git-Committed Dedup File — persistent deduplication across ephemeral CI runs.

Stores internal_hash values of jobs already posted to Discord in a JSON file
(`data/posted_hashes.json`) that is committed back to the repo after each run.

This solves the problem of ephemeral SQLite databases on GitHub Actions where
each run starts fresh and can't remember what was already posted.

Usage:
    from scripts.utils.dedup_file import load_posted_hashes, save_posted_hashes, is_already_posted

    hashes = load_posted_hashes()            # Load at start of run
    if is_already_posted(hashes, job_hash):   # Check before posting
        skip...
    hashes.add(new_hash)                     # Track after posting
    save_posted_hashes(hashes)               # Save at end of run
"""

import json
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEDUP_FILE = PROJECT_ROOT / "data" / "posted_hashes.json"

# Keep hashes for 7 days max before pruning (prevents the file from growing forever)
MAX_AGE_DAYS = 7


def load_posted_hashes() -> dict[str, str]:
    """Load the dedup file. Returns {hash: timestamp_iso}."""
    if not DEDUP_FILE.exists():
        return {}
    try:
        with open(DEDUP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Handle both old format (list of hashes) and new format (dict of hash:timestamp)
        if isinstance(data, list):
            now = datetime.now(timezone.utc).isoformat()
            return {h: now for h in data}
        return data
    except (json.JSONDecodeError, IOError):
        return {}


def save_posted_hashes(hashes: dict[str, str]) -> None:
    """Save the dedup file, pruning entries older than MAX_AGE_DAYS."""
    now = datetime.now(timezone.utc)
    pruned = {}
    for h, ts in hashes.items():
        try:
            recorded = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            age_days = (now - recorded).total_seconds() / 86400
            if age_days <= MAX_AGE_DAYS:
                pruned[h] = ts
        except (ValueError, TypeError):
            pruned[h] = ts  # Keep if we can't parse the timestamp

    DEDUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DEDUP_FILE, "w", encoding="utf-8") as f:
        json.dump(pruned, f, indent=None)


def is_already_posted(hashes: dict[str, str], internal_hash: str) -> bool:
    """Check if a job was already posted in a previous run."""
    return internal_hash in hashes


def mark_as_posted(hashes: dict[str, str], internal_hash: str) -> None:
    """Mark a hash as posted with the current timestamp."""
    hashes[internal_hash] = datetime.now(timezone.utc).isoformat()
