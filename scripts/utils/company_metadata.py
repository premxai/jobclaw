"""
Company Metadata Store — tracks per-company scrape history for skip-unchanged optimization.

This module enables the "skip unchanged companies" optimization:
1. Track when each company was last scraped
2. Store a hash of job IDs to detect changes without full comparison
3. Skip companies that were recently scraped AND haven't changed

Reduces scrape volume from ~12k to ~2-3k per cycle.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ATS platforms with different update frequencies
SCRAPE_INTERVALS = {
    # Fast-moving: 1 hour
    "greenhouse": 3600,
    "lever": 3600,
    # Medium: 2 hours
    "ashby": 7200,
    "workable": 7200,
    "rippling": 7200,
    "gem": 7200,
    # Slow (enterprise): 4 hours
    "workday": 14400,
    "smartrecruiters": 14400,
    # Rare: 6 hours
    "bamboohr": 21600,
}

DEFAULT_INTERVAL = 3600  # 1 hour


class CompanyMetadata:
    """
    File-backed metadata store for company scrape history.
    
    Schema:
    {
        "companies": {
            "greenhouse:stripe": {
                "last_scraped": "2026-03-05T10:30:00Z",
                "last_job_count": 564,
                "last_job_hash": "a1b2c3d4e5f6",
                "consecutive_empty": 0
            }
        }
    }
    """
    
    def __init__(self, path: Path = None):
        self.path = path or Path(__file__).parent.parent.parent / "state" / "company_metadata.json"
        self._data = self._load()
        self._stats = {"checked": 0, "skipped": 0, "scraped": 0}
    
    def _load(self) -> dict:
        """Load metadata from disk."""
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("companies", {})
            except (json.JSONDecodeError, KeyError):
                return {}
        return {}
    
    def save(self) -> None:
        """Persist metadata to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({
                "_comment": "Per-company scrape metadata for skip-unchanged optimization",
                "_schema_version": 1,
                "companies": self._data
            }, f, indent=2)
    
    def _key(self, ats: str, slug: str) -> str:
        """Generate unique key for a company."""
        return f"{ats}:{slug}"
    
    def should_scrape(self, ats: str, slug: str) -> tuple[bool, str]:
        """
        Determine if a company should be scraped.
        
        Returns:
            (should_scrape: bool, reason: str)
        """
        self._stats["checked"] += 1
        key = self._key(ats, slug)
        meta = self._data.get(key)
        
        # Never scraped → must scrape
        if not meta:
            return True, "never_scraped"
        
        # Parse last scraped time
        try:
            last_scraped = datetime.fromisoformat(meta["last_scraped"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            return True, "invalid_timestamp"
        
        # Get scrape interval for this platform
        interval = SCRAPE_INTERVALS.get(ats.lower(), DEFAULT_INTERVAL)
        
        # Check if enough time has passed
        now = datetime.now(timezone.utc)
        elapsed = (now - last_scraped).total_seconds()
        
        if elapsed >= interval:
            return True, f"interval_expired ({int(elapsed)}s >= {interval}s)"
        
        # Check consecutive empty runs — re-scrape after 5 consecutive empties
        if meta.get("consecutive_empty", 0) >= 5:
            # Been empty 5 times — try again less frequently
            if elapsed >= interval * 3:  # 3x normal interval
                return True, "consecutive_empty_retry"
            self._stats["skipped"] += 1
            return False, f"consecutive_empty_skip ({meta['consecutive_empty']} empties)"
        
        # Recently scraped and had jobs → skip
        self._stats["skipped"] += 1
        return False, f"recently_scraped ({int(interval - elapsed)}s remaining)"
    
    def update_after_scrape(
        self,
        ats: str,
        slug: str,
        job_count: int,
        job_ids: list[str] = None,
    ) -> bool:
        """
        Update metadata after a successful scrape.
        
        Returns:
            True if jobs changed since last scrape, False if unchanged.
        """
        self._stats["scraped"] += 1
        key = self._key(ats, slug)
        now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        # Compute job hash
        new_hash = ""
        if job_ids:
            sorted_ids = sorted(str(jid) for jid in job_ids)
            new_hash = hashlib.md5("|".join(sorted_ids).encode()).hexdigest()[:12]
        
        old_meta = self._data.get(key, {})
        old_hash = old_meta.get("last_job_hash", "")
        changed = new_hash != old_hash
        
        # Update consecutive empty count
        consecutive_empty = old_meta.get("consecutive_empty", 0)
        if job_count == 0:
            consecutive_empty += 1
        else:
            consecutive_empty = 0
        
        self._data[key] = {
            "last_scraped": now_str,
            "last_job_count": job_count,
            "last_job_hash": new_hash,
            "consecutive_empty": consecutive_empty,
        }
        
        return changed
    
    def get_stats(self) -> dict:
        """Get skip statistics for logging."""
        return {
            "checked": self._stats["checked"],
            "skipped": self._stats["skipped"],
            "scraped": self._stats["scraped"],
            "skip_rate": (
                f"{100 * self._stats['skipped'] / self._stats['checked']:.1f}%"
                if self._stats["checked"] > 0 else "0%"
            ),
        }
    
    def clear_stats(self) -> None:
        """Reset statistics for a new run."""
        self._stats = {"checked": 0, "skipped": 0, "scraped": 0}
