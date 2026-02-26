"""
JSON Response Cache with TTL + Cooldown Tracking.

Caches raw API responses to disk so repeated scraper runs within the TTL
skip redundant HTTP calls. Cuts 11,800 company fetches down to only the
ones whose cache has expired.

Features:
  - Per-company JSON file caching keyed by "{ats}_{slug}.json"
  - Configurable TTL per platform (default 4h)
  - Atomic writes (write to .tmp, then os.replace)
  - Cache statistics for monitoring

Usage:
    from scripts.utils.response_cache import ResponseCache

    cache = ResponseCache()
    data = cache.get("greenhouse", "acme")
    if data is not None:
        # Use cached data
    else:
        data = await fetch(...)
        cache.put("greenhouse", "acme", data)
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from scripts.utils.logger import _log

PROJECT_ROOT = Path(__file__).parent.parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "cache"

# ── TTL per platform (in seconds) ────────────────────────────────────
# These are tuned based on how often each platform's job listings change.
# Fast-moving boards get shorter TTLs; enterprise pages get longer.
PLATFORM_TTL: dict[str, int] = {
    "greenhouse": 1 * 3600,       # 1 hour — catch jobs fast
    "lever": 1 * 3600,            # 1 hour
    "ashby": 1 * 3600,            # 1 hour
    "workable": 2 * 3600,         # 2 hours — WAF, slightly longer
    "workday": 2 * 3600,          # 2 hours — WAF
    "smartrecruiters": 1 * 3600,  # 1 hour
    "bamboohr": 2 * 3600,         # 2 hours
    "rippling": 1 * 3600,         # 1 hour
    # Enterprise
    "apple": 30 * 60,             # 30 min (fast-moving, high value)
    "amazon": 30 * 60,            # 30 min
    "microsoft": 1 * 3600,        # 1 hour
    "google": 1 * 3600,           # 1 hour
    "meta": 1 * 3600,             # 1 hour
    "tiktok": 1 * 3600,           # 1 hour
    "nvidia": 1 * 3600,           # 1 hour
    "uber": 1 * 3600,             # 1 hour
}

DEFAULT_TTL = 1 * 3600  # 1 hour


class CacheStats:
    """Track cache hit/miss/expired stats per run."""
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.expired = 0
        self.writes = 0

    def __repr__(self):
        total = self.hits + self.misses + self.expired
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return f"CacheStats(hits={self.hits}, misses={self.misses}, expired={self.expired}, writes={self.writes}, hit_rate={hit_rate:.1f}%)"


class ResponseCache:
    """Disk-backed JSON response cache with per-platform TTLs."""

    def __init__(self, cache_dir: Optional[Path] = None, ttl_overrides: Optional[dict[str, int]] = None):
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttls = {**PLATFORM_TTL}
        if ttl_overrides:
            self.ttls.update(ttl_overrides)
        self.stats = CacheStats()

    def _cache_key(self, platform: str, slug: str) -> str:
        """Generate a safe filename from platform + slug."""
        # Replace colons (Workday slugs use "tenant:shard:site")
        safe_slug = slug.replace(":", "_").replace("/", "_").replace("\\", "_")
        return f"{platform}_{safe_slug}"

    def _cache_path(self, platform: str, slug: str) -> Path:
        """Full file path for a cached response."""
        # Group caches by platform subdirectory
        platform_dir = self.cache_dir / platform
        platform_dir.mkdir(parents=True, exist_ok=True)
        return platform_dir / f"{self._cache_key(platform, slug)}.json"

    def _ttl_for(self, platform: str) -> int:
        return self.ttls.get(platform, DEFAULT_TTL)

    def get(self, platform: str, slug: str) -> Optional[Any]:
        """
        Read cached response if it exists and hasn't expired.

        Returns:
            Parsed JSON data if cache hit, None if miss or expired.
        """
        path = self._cache_path(platform, slug)
        if not path.exists():
            self.stats.misses += 1
            return None

        # Check TTL based on file modification time
        age = time.time() - path.stat().st_mtime
        ttl = self._ttl_for(platform)

        if age > ttl:
            self.stats.expired += 1
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.stats.hits += 1
            return data
        except (json.JSONDecodeError, OSError):
            self.stats.misses += 1
            return None

    def put(self, platform: str, slug: str, data: Any) -> None:
        """
        Write response data to cache with atomic write.

        Args:
            platform: ATS platform name
            slug: Company slug
            data: JSON-serializable response data
        """
        path = self._cache_path(platform, slug)
        tmp_path = path.with_suffix(".tmp")

        try:
            tmp_path.write_text(
                json.dumps(data, separators=(",", ":"), default=str),
                encoding="utf-8",
            )
            os.replace(str(tmp_path), str(path))
            self.stats.writes += 1
        except OSError as e:
            _log(f"Cache write failed for {platform}/{slug}: {e}", "WARN")
            # Clean up temp file if it exists
            tmp_path.unlink(missing_ok=True)

    def is_fresh(self, platform: str, slug: str) -> bool:
        """Check if a cache entry exists and is within TTL, without reading it."""
        path = self._cache_path(platform, slug)
        if not path.exists():
            return False
        age = time.time() - path.stat().st_mtime
        return age <= self._ttl_for(platform)

    def invalidate(self, platform: str, slug: str) -> None:
        """Remove a specific cache entry."""
        path = self._cache_path(platform, slug)
        path.unlink(missing_ok=True)

    def clear_platform(self, platform: str) -> int:
        """Remove all cache entries for a platform. Returns count removed."""
        platform_dir = self.cache_dir / platform
        if not platform_dir.exists():
            return 0
        count = 0
        for f in platform_dir.glob("*.json"):
            f.unlink()
            count += 1
        return count

    def clear_all(self) -> int:
        """Remove all cached data. Returns count removed."""
        count = 0
        for platform_dir in self.cache_dir.iterdir():
            if platform_dir.is_dir():
                for f in platform_dir.glob("*.json"):
                    f.unlink()
                    count += 1
        return count

    def log_stats(self) -> None:
        """Log cache stats summary."""
        _log(f"Cache stats: {self.stats}")
