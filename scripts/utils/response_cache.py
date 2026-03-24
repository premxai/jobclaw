"""
JSON Response Cache with TTL + ETag/Last-Modified Delta Tracking.

Caches raw API responses to disk so repeated scraper runs within the TTL
skip redundant HTTP calls. Supports HTTP conditional headers (ETag,
Last-Modified) for 304 Not Modified responses.

Features:
  - Per-company JSON file caching keyed by "{ats}_{slug}.json"
  - HTTP metadata storage (.meta files) for ETag/Last-Modified headers
  - Configurable TTL per platform (default 1h)
  - Atomic writes (write to .tmp, then os.replace)
  - Cache statistics for monitoring (hits/misses/expired/not_modified)

Usage:
    from scripts.utils.response_cache import ResponseCache

    cache = ResponseCache()
    data = cache.get("greenhouse", "acme")
    if data is not None:
        # Use cached data
    else:
        # Fetch with conditional headers
        meta = cache.get_http_meta("greenhouse", "acme")
        data = await fetch_with_conditional(url, etag=meta.get('etag'), last_modified=meta.get('last_modified'))
        cache.put("greenhouse", "acme", data, http_headers=response.headers)
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from scripts.utils.logger import _log

PROJECT_ROOT = Path(__file__).parent.parent.parent

# Use TEMP directory for cache to avoid OneDrive file-locking conflicts.
# OneDrive syncs files in the workspace and locks .tmp/.json during sync,
# which causes atomic rename failures (WinError 5 / WinError 32).
_temp = os.environ.get("TEMP", os.environ.get("TMP", ""))
if _temp:
    CACHE_DIR = Path(_temp) / "jobclaw_cache"
else:
    CACHE_DIR = PROJECT_ROOT / "data" / "cache"

# ── TTL per platform (in seconds) ────────────────────────────────────
# These are tuned based on how often each platform's job listings change.
# Fast-moving boards get shorter TTLs; enterprise pages get longer.
PLATFORM_TTL: dict[str, int] = {
    "greenhouse": 1 * 3600,  # 1 hour — catch jobs fast
    "lever": 1 * 3600,  # 1 hour
    "ashby": 1 * 3600,  # 1 hour
    "workable": 2 * 3600,  # 2 hours — WAF, slightly longer
    "workday": 2 * 3600,  # 2 hours — WAF
    "smartrecruiters": 1 * 3600,  # 1 hour
    "bamboohr": 2 * 3600,  # 2 hours
    "rippling": 1 * 3600,  # 1 hour
    # Enterprise
    "apple": 30 * 60,  # 30 min (fast-moving, high value)
    "amazon": 30 * 60,  # 30 min
    "microsoft": 1 * 3600,  # 1 hour
    "google": 1 * 3600,  # 1 hour
    "meta": 1 * 3600,  # 1 hour
    "tiktok": 1 * 3600,  # 1 hour
    "nvidia": 1 * 3600,  # 1 hour
    "uber": 1 * 3600,  # 1 hour
}

DEFAULT_TTL = 1 * 3600  # 1 hour


class CacheStats:
    """Track cache hit/miss/expired/not_modified stats per run."""

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.expired = 0
        self.writes = 0
        self.not_modified = 0  # HTTP 304 responses

    def __repr__(self):
        total = self.hits + self.misses + self.expired
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return (
            f"CacheStats(hits={self.hits}, misses={self.misses}, expired={self.expired}, "
            f"not_modified={self.not_modified}, writes={self.writes}, hit_rate={hit_rate:.1f}%)"
        )


class ResponseCache:
    """Disk-backed JSON response cache with per-platform TTLs."""

    def __init__(self, cache_dir: Path | None = None, ttl_overrides: dict[str, int] | None = None):
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

    def get(self, platform: str, slug: str) -> Any | None:
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

    def put(self, platform: str, slug: str, data: Any, http_headers: dict = None) -> None:
        """
        Write response data to cache with atomic write.
        Optionally stores HTTP metadata (ETag, Last-Modified) for conditional requests.

        Args:
            platform: ATS platform name
            slug: Company slug
            data: JSON-serializable response data
            http_headers: Optional response headers dict (stores ETag & Last-Modified)
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
            tmp_path.unlink(missing_ok=True)

        # Store HTTP metadata for conditional requests (ETag / Last-Modified)
        if http_headers:
            self._save_http_meta(platform, slug, http_headers)

    def _meta_path(self, platform: str, slug: str) -> Path:
        """Path for HTTP metadata file (ETag, Last-Modified)."""
        platform_dir = self.cache_dir / platform
        platform_dir.mkdir(parents=True, exist_ok=True)
        return platform_dir / f"{self._cache_key(platform, slug)}.meta"

    def _save_http_meta(self, platform: str, slug: str, headers: dict) -> None:
        """Extract and save ETag + Last-Modified from response headers."""
        meta = {}
        # Support both dict and CaseInsensitiveDict headers
        for key in headers:
            lk = key.lower() if isinstance(key, str) else str(key).lower()
            if lk == "etag":
                meta["etag"] = headers[key]
            elif lk == "last-modified":
                meta["last_modified"] = headers[key]

        if not meta:
            return

        path = self._meta_path(platform, slug)
        try:
            path.write_text(json.dumps(meta), encoding="utf-8")
        except OSError:
            pass  # Non-fatal — conditional requests just won't work

    def get_http_meta(self, url: str) -> dict:
        """
        Get stored HTTP metadata (ETag, Last-Modified) for a URL (for conditional requests).

        Keyed by URL — used by fetch_with_retry() to send If-None-Match headers.

        Returns:
            Dict with 'etag' and/or 'last_modified' keys, or empty dict.
        """
        slug = hashlib.md5(url.encode()).hexdigest()
        path = self._meta_path("_url_", slug)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def store_http_meta(self, url: str, meta: dict) -> None:
        """
        Store HTTP metadata (ETag, Last-Modified) keyed by URL.

        Used by fetch_with_retry() to persist ETags from 200 responses for
        future If-None-Match conditional requests.

        Args:
            url: The request URL used as the cache key.
            meta: Dict with 'etag' and/or 'last_modified' values.
        """
        slug = hashlib.md5(url.encode()).hexdigest()
        path = self._meta_path("_url_", slug)
        try:
            path.write_text(json.dumps(meta), encoding="utf-8")
        except OSError:
            pass  # Non-fatal — conditional requests just won't work

    def record_not_modified(self) -> None:
        """Record a 304 Not Modified response."""
        self.stats.not_modified += 1

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
