"""
Retry Queue — file-backed queue for failed scrape attempts.

Failed companies are queued for retry with exponential backoff:
  Retry 1: 1 hour later
  Retry 2: 6 hours later
  Retry 3: 24 hours later
  Retry 4+: Drop (mark as problematic)

This ensures transient failures (429s, timeouts) don't cause permanent data loss.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Retry schedule (in seconds)
RETRY_DELAYS = [
    3600,  # 1 hour
    21600,  # 6 hours
    86400,  # 24 hours
]
MAX_RETRIES = len(RETRY_DELAYS)


class RetryQueue:
    """
    File-backed retry queue for failed company scrapes.

    Schema:
    {
        "queue": [
            {
                "company": "acme",
                "ats": "workday",
                "slug": "acme:5:external",
                "error": "429 Too Many Requests",
                "failed_at": "2026-03-05T10:00:00Z",
                "retry_count": 1,
                "next_retry": "2026-03-05T11:00:00Z"
            }
        ]
    }
    """

    def __init__(self, path: Path = None):
        self.path = path or Path(__file__).parent.parent.parent / "state" / "retry_queue.json"
        self._queue = self._load()
        self._stats = {"added": 0, "retried": 0, "dropped": 0, "success": 0}

    def _load(self) -> list:
        """Load queue from disk."""
        if self.path.exists():
            try:
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("queue", [])
            except (json.JSONDecodeError, KeyError):
                return []
        return []

    def save(self) -> None:
        """Persist queue to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(
                {"_comment": "Failed companies pending retry", "_schema_version": 1, "queue": self._queue}, f, indent=2
            )

    def _key(self, ats: str, slug: str) -> str:
        """Generate unique key for a company."""
        return f"{ats}:{slug}"

    def add_failure(self, company: str, ats: str, slug: str, error: str) -> None:
        """
        Add a failed company to the retry queue.

        If already in queue, increment retry count and reschedule.
        If max retries exceeded, drop from queue.
        """
        key = self._key(ats, slug)
        now = datetime.now(UTC)
        now_str = now.isoformat().replace("+00:00", "Z")

        # Check if already in queue
        existing = None
        for i, item in enumerate(self._queue):
            if self._key(item["ats"], item["slug"]) == key:
                existing = (i, item)
                break

        if existing:
            idx, item = existing
            retry_count = item.get("retry_count", 0) + 1

            if retry_count >= MAX_RETRIES:
                # Drop from queue — too many failures
                self._queue.pop(idx)
                self._stats["dropped"] += 1
                return

            # Update with new retry schedule
            delay = RETRY_DELAYS[retry_count]
            next_retry = (now + timedelta(seconds=delay)).isoformat().replace("+00:00", "Z")

            self._queue[idx] = {
                "company": company,
                "ats": ats,
                "slug": slug,
                "error": error,
                "failed_at": now_str,
                "retry_count": retry_count,
                "next_retry": next_retry,
            }
        else:
            # New failure — add to queue
            delay = RETRY_DELAYS[0]
            next_retry = (now + timedelta(seconds=delay)).isoformat().replace("+00:00", "Z")

            self._queue.append(
                {
                    "company": company,
                    "ats": ats,
                    "slug": slug,
                    "error": error,
                    "failed_at": now_str,
                    "retry_count": 0,
                    "next_retry": next_retry,
                }
            )
            self._stats["added"] += 1

    def get_ready_retries(self) -> list[dict]:
        """
        Get companies that are ready for retry.

        Returns list of company dicts with ats, slug, company fields.
        Does NOT remove from queue — call mark_success() after successful retry.
        """
        now = datetime.now(UTC)
        ready = []

        for item in self._queue:
            try:
                next_retry = datetime.fromisoformat(item["next_retry"].replace("Z", "+00:00"))
                if now >= next_retry:
                    ready.append(
                        {
                            "company": item["company"],
                            "ats": item["ats"],
                            "slug": item["slug"],
                        }
                    )
                    self._stats["retried"] += 1
            except (KeyError, ValueError):
                continue

        return ready

    def mark_success(self, ats: str, slug: str) -> None:
        """Remove a company from retry queue after successful scrape."""
        key = self._key(ats, slug)
        self._queue = [item for item in self._queue if self._key(item["ats"], item["slug"]) != key]
        self._stats["success"] += 1

    def get_stats(self) -> dict:
        """Get retry queue statistics."""
        return {
            "queue_size": len(self._queue),
            "added": self._stats["added"],
            "retried": self._stats["retried"],
            "dropped": self._stats["dropped"],
            "success": self._stats["success"],
        }

    def clear_stats(self) -> None:
        """Reset statistics for a new run."""
        self._stats = {"added": 0, "retried": 0, "dropped": 0, "success": 0}

    def get_queue_summary(self) -> str:
        """Get human-readable summary of queue contents."""
        if not self._queue:
            return "Retry queue empty"

        by_ats = {}
        for item in self._queue:
            ats = item.get("ats", "unknown")
            by_ats[ats] = by_ats.get(ats, 0) + 1

        parts = [f"{ats}={count}" for ats, count in sorted(by_ats.items())]
        return f"Retry queue: {len(self._queue)} companies ({', '.join(parts)})"
