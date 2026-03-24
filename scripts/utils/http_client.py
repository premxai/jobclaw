"""
Hardened async HTTP client with TLS fingerprint impersonation.

v2: Migrated from aiohttp to curl_cffi for Cloudflare/WAF bypass.

Features:
  - TLS fingerprint impersonation (Chrome 131) via curl_cffi
  - User-Agent rotation from a pool of 50+ real browser fingerprints
  - Per-host rate limiting with configurable RPS + jitter
  - Exponential backoff on 429/503 with retry budget
  - Transparent logging of non-200 responses
  - Header randomization (Accept-Language, sec-ch-ua, etc.)
  - Proxy support (HTTP/SOCKS5)

Usage:
    from scripts.utils.http_client import create_session, RateLimiter

    limiter = RateLimiter()
    async with create_session(limiter) as session:
        resp = await session.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs")
"""

import asyncio
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any

from scripts.utils.logger import _log
from scripts.utils.response_cache import ResponseCache

# Try curl_cffi first (TLS impersonation), fall back to aiohttp
try:
    from curl_cffi.requests import AsyncSession as CffiAsyncSession

    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

import aiohttp

# ═══════════════════════════════════════════════════════════════════════
# TLS IMPERSONATION — which browser to pretend to be
# ═══════════════════════════════════════════════════════════════════════

# curl_cffi impersonation targets — rotates between these.
# Using older, universally supported versions to avoid ImpersonateError
_IMPERSONATE_TARGETS = [
    "chrome110",
    "chrome116",
    "chrome120",
    "edge99",
    "safari15_3",
]


def _random_impersonate() -> str:
    return random.choice(_IMPERSONATE_TARGETS)


# ═══════════════════════════════════════════════════════════════════════
# USER-AGENT ROTATION POOL — real browser fingerprints (Chrome/Firefox/Safari)
# ═══════════════════════════════════════════════════════════════════════

_UA_POOL = [
    # Chrome 120-131 on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:131.0) Gecko/20100101 Firefox/131.0",
    # Safari
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

_ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.9,es;q=0.8",
    "en-US,en;q=0.9,fr;q=0.8",
    "en-GB,en;q=0.9,en-US;q=0.8",
    "en,en-US;q=0.9",
]


def random_headers() -> dict[str, str]:
    """Generate realistic browser-like headers with per-request randomization."""
    ua = random.choice(_UA_POOL)
    return {
        "User-Agent": ua,
        "Accept": "application/json, text/html, */*; q=0.01",
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
    }


# ═══════════════════════════════════════════════════════════════════════
# PER-HOST RATE LIMITER — token bucket with jitter
# ═══════════════════════════════════════════════════════════════════════

# Default RPS limits per ATS domain — tuned for maximum stealth (24/7 reliability)
# Conservative limits to avoid bans during continuous scraping
PLATFORM_RATE_LIMITS: dict[str, float] = {
    # Public board APIs — lowered for stealth
    "boards-api.greenhouse.io": 1.5,  # 2,542 companies — be conservative
    "api.lever.co": 1.0,  # Strict rate limiting
    "api.ashbyhq.com": 1.0,  # Smaller platform
    "api.smartrecruiters.com": 1.0,  # Enterprise platform
    # Workday / Workable — aggressive WAFs, go very slow
    "myworkdayjobs.com": 0.5,  # 1 req / 2s — Workday WAF is harsh
    "apply.workable.com": 0.15,  # ~1 req / 6.6s — Workable 429s very hard, go slow
    # Others — conservative
    "ats.rippling.com": 0.5,  # Stability issues at higher rates
    "bamboohr.com": 0.5,  # Small platform, be nice
    # Enterprise endpoints
    "jobs.apple.com": 1.5,
    "www.amazon.jobs": 1.5,
    "apply.careers.microsoft.com": 2.0,
    "nvidia.eightfold.ai": 2.0,
    "api.lifeattiktok.com": 2.0,
    "www.uber.com": 1.0,
}

_DEFAULT_RPS = 1.5


@dataclass
class _HostBucket:
    """Token bucket for a single host with adaptive 429 backoff."""

    rps: float
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _base_rps: float = 0.0  # original RPS before any 429 reductions
    _consecutive_429s: int = 0
    _cooldown_until: float = 0.0  # monotonic timestamp — global pause on 429 storms

    def __post_init__(self):
        if self._base_rps == 0.0:
            self._base_rps = self.rps

    def record_429(self):
        """Called when the host returns 429. Halves RPS and sets a cooldown."""
        self._consecutive_429s += 1
        # Halve RPS down to floor of 0.05 (1 req / 20s)
        self.rps = max(0.05, self.rps * 0.5)
        # Global cooldown: all workers for this host must wait
        cooldown_secs = min(10.0 * self._consecutive_429s, 60.0)
        self._cooldown_until = time.monotonic() + cooldown_secs

    def record_success(self):
        """Called on successful request. Gradually restores RPS."""
        self._consecutive_429s = 0
        # Restore towards base RPS by 20% per success
        if self.rps < self._base_rps:
            self.rps = min(self._base_rps, self.rps * 1.2)

    async def acquire(self):
        """Wait until a token is available, then consume one."""
        async with self.lock:
            # Respect global cooldown from 429 storms
            now = time.monotonic()
            if now < self._cooldown_until:
                await asyncio.sleep(self._cooldown_until - now)

            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.rps, self.tokens + elapsed * self.rps)
            self.last_refill = now

            if self.tokens < 1.0:
                wait_time = (1.0 - self.tokens) / self.rps
                # Add human-like jitter (0.5s - 1.5s base)
                jitter = random.uniform(0.5, 1.5)
                await asyncio.sleep(wait_time + jitter)
                self.tokens = 0.0
            else:
                # Even if we have tokens, add a tiny bit of jitter for stealth
                await asyncio.sleep(random.uniform(0.1, 0.3))
                self.tokens -= 1.0


class RateLimiter:
    """Per-host rate limiter using token buckets."""

    def __init__(self, overrides: dict[str, float] | None = None):
        self._buckets: dict[str, _HostBucket] = {}
        self._rates = {**PLATFORM_RATE_LIMITS}
        if overrides:
            self._rates.update(overrides)

    def _host_key(self, url: str) -> str:
        """Extract the rate-limit key from a URL. Groups subdomains for Workday."""
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.hostname or ""
        if "myworkdayjobs.com" in host:
            return "myworkdayjobs.com"
        if "bamboohr.com" in host:
            return "bamboohr.com"
        return host

    def _get_bucket(self, url: str) -> _HostBucket:
        key = self._host_key(url)
        if key not in self._buckets:
            rps = self._rates.get(key, _DEFAULT_RPS)
            self._buckets[key] = _HostBucket(rps=rps)
        return self._buckets[key]

    async def acquire(self, url: str):
        """Wait for permission to hit this URL's host."""
        bucket = self._get_bucket(url)
        await bucket.acquire()

    def record_429(self, url: str):
        """Signal that the host returned 429. Triggers adaptive slowdown."""
        bucket = self._get_bucket(url)
        bucket.record_429()

    def record_success(self, url: str):
        """Signal that a request succeeded. Gradually restores rate."""
        bucket = self._get_bucket(url)
        bucket.record_success()


# ═══════════════════════════════════════════════════════════════════════
# RETRY ENGINE — exponential backoff on 429/503/502
# ═══════════════════════════════════════════════════════════════════════

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
PERMANENT_ERROR_CODES = {404, 410, 422}  # company gone / endpoint removed — skip immediately
MAX_RETRIES = 3
BASE_BACKOFF = 1.5  # seconds

# ── Proxy rotation pool ──────────────────────────────────────────────────────
# Set PROXY_URLS (comma-separated) or PROXY_URL (single) in the environment.
# Requests round-robin across all provided proxies. No-op when empty.
_PROXY_POOL = [u.strip() for u in os.getenv("PROXY_URLS", os.getenv("PROXY_URL", "")).split(",") if u.strip()]
_proxy_idx = 0


def _next_proxy() -> str | None:
    """Return the next proxy from the rotation pool (round-robin). None if no proxies configured."""
    global _proxy_idx
    if not _PROXY_POOL:
        return None
    proxy = _PROXY_POOL[_proxy_idx % len(_PROXY_POOL)]
    _proxy_idx += 1
    return proxy


# Sentinel returned by fetch_with_retry() on HTTP 304 Not Modified
class _NotModified:
    """Sentinel for 304 Not Modified — data hasn't changed since last fetch."""

    def __bool__(self):
        return True  # Truthy so `if resp:` works

    def __repr__(self):
        return "NOT_MODIFIED"


NOT_MODIFIED = _NotModified()

# Optional response cache for ETag conditional requests.
# Set to a ResponseCache instance to enable If-None-Match header injection.
_response_cache: ResponseCache | None = None


async def fetch_with_retry(
    session,  # aiohttp.ClientSession OR curl_cffi AsyncSession
    method: str,
    url: str,
    rate_limiter: RateLimiter | None = None,
    max_retries: int = MAX_RETRIES,
    timeout: int = 30,
    log_tag: str = "",
    **kwargs,
):
    """
    Fetch a URL with rate limiting, UA rotation, and exponential backoff.

    Works with BOTH aiohttp.ClientSession and curl_cffi.requests.AsyncSession.
    Returns a response object on success, None on exhausted retries.

    For curl_cffi: response has .status_code, .json(), .text, .headers
    For aiohttp:   response has .status, .json(), .text(), .headers
    """
    is_cffi = HAS_CURL_CFFI and isinstance(session, CffiAsyncSession)

    total_attempts = max_retries + 1
    for attempt in range(total_attempts):
        try:
            # Rate limit
            if rate_limiter:
                await rate_limiter.acquire(url)

            # Merge random headers with any caller-provided headers
            headers = random_headers()
            if "headers" in kwargs:
                headers.update(kwargs.pop("headers"))

            # Send If-None-Match if we have a cached ETag for this URL
            if _response_cache:
                cached_meta = _response_cache.get_http_meta(url)
                if cached_meta and cached_meta.get("etag"):
                    merged_headers = {**headers, "If-None-Match": cached_meta["etag"]}
                else:
                    merged_headers = headers
            else:
                merged_headers = headers

            if is_cffi:
                resp = await _cffi_request(session, method, url, merged_headers, timeout, **kwargs)
                status = resp.status_code
            else:
                resp = await _aiohttp_request(session, method, url, merged_headers, timeout, **kwargs)
                status = resp.status

            # Success
            if status == 200:
                if rate_limiter:
                    rate_limiter.record_success(url)
                # Cache the ETag for future conditional requests
                if _response_cache:
                    resp_etag = resp.headers.get("ETag") or resp.headers.get("etag")
                    if resp_etag:
                        _response_cache.store_http_meta(url, {"etag": resp_etag})
                return resp

            # HTTP 304 Not Modified — data hasn't changed since last fetch
            if status == 304:
                if not is_cffi:
                    await resp.release()
                return NOT_MODIFIED

            # Retryable error
            if status in RETRYABLE_STATUS_CODES:
                # Notify rate limiter about 429 for adaptive slowdown
                if status == 429 and rate_limiter:
                    rate_limiter.record_429(url)

                # Last attempt — don't waste time sleeping
                if attempt >= max_retries:
                    tag = f"[{log_tag}] " if log_tag else ""
                    _log(f"{tag}HTTP {status} on {url} — retries exhausted", "WARN")
                    if not is_cffi:
                        await resp.release()
                    return None

                retry_after = (resp.headers or {}).get("Retry-After")
                if retry_after:
                    try:
                        wait = min(float(retry_after), 120.0)
                    except ValueError:
                        wait = random.uniform(0, min(45.0, BASE_BACKOFF * (2**attempt)))
                else:
                    wait = random.uniform(0, min(45.0, BASE_BACKOFF * (2**attempt)))

                tag = f"[{log_tag}] " if log_tag else ""
                _log(
                    f"{tag}HTTP {status} on {url} — retry {attempt + 1}/{max_retries} in {wait:.1f}s",
                    "WARN",
                )
                if not is_cffi:
                    await resp.release()
                await asyncio.sleep(wait)
                continue

            # Permanent error — company gone or endpoint removed, don't waste retries
            if status in PERMANENT_ERROR_CODES:
                tag = f"[{log_tag}] " if log_tag else ""
                _log(f"{tag}HTTP {status} on {url} — permanent error, skipping", "WARN")
                if not is_cffi:
                    await resp.release()
                return None

            # Non-retryable error (403, etc.)
            tag = f"[{log_tag}] " if log_tag else ""
            _log(f"{tag}HTTP {status} on {url} — not retrying", "WARN")
            if not is_cffi:
                await resp.release()
            return None

        except TimeoutError:
            tag = f"[{log_tag}] " if log_tag else ""
            if attempt < max_retries:
                wait = BASE_BACKOFF * (2**attempt) * random.uniform(0.8, 1.2)
                _log(f"{tag}Timeout on {url} — retry {attempt + 1}/{max_retries} in {wait:.1f}s", "WARN")
                await asyncio.sleep(wait)
            else:
                _log(f"{tag}Timeout on {url} — retries exhausted", "WARN")
                return None

        except Exception as e:
            tag = f"[{log_tag}] " if log_tag else ""
            if attempt < max_retries:
                wait = BASE_BACKOFF * (2**attempt) * random.uniform(0.8, 1.2)
                _log(f"{tag}{type(e).__name__} on {url} — retry {attempt + 1}/{max_retries} in {wait:.1f}s", "WARN")
                await asyncio.sleep(wait)
            else:
                _log(f"{tag}{type(e).__name__} on {url} — retries exhausted: {e}", "WARN")
                return None

    return None


async def _cffi_request(session, method: str, url: str, headers: dict, timeout: int, **kwargs):
    """Execute request via curl_cffi with TLS impersonation."""
    # Rotate impersonation target per request for maximum evasion
    impersonate = _random_impersonate()

    if method.upper() == "GET":
        return await session.get(
            url,
            headers=headers,
            timeout=timeout,
            impersonate=impersonate,
            **kwargs,
        )
    elif method.upper() == "POST":
        return await session.post(
            url,
            headers=headers,
            timeout=timeout,
            impersonate=impersonate,
            **kwargs,
        )
    else:
        return await session.request(
            method,
            url,
            headers=headers,
            timeout=timeout,
            impersonate=impersonate,
            **kwargs,
        )


async def _aiohttp_request(session, method: str, url: str, headers: dict, timeout: int, **kwargs):
    """Execute request via aiohttp (fallback when curl_cffi is not installed)."""
    req_timeout = aiohttp.ClientTimeout(total=timeout)
    proxy_url = getattr(session, "_proxy_url", None)
    proxy_kwarg = {"proxy": proxy_url} if proxy_url else {}

    if method.upper() == "GET":
        return await session.get(url, headers=headers, timeout=req_timeout, **proxy_kwarg, **kwargs)
    elif method.upper() == "POST":
        return await session.post(url, headers=headers, timeout=req_timeout, **proxy_kwarg, **kwargs)
    else:
        return await session.request(method, url, headers=headers, timeout=req_timeout, **proxy_kwarg, **kwargs)


# ═══════════════════════════════════════════════════════════════════════
# UNIFIED RESPONSE WRAPPER — normalizes curl_cffi and aiohttp responses
# ═══════════════════════════════════════════════════════════════════════


class UnifiedResponse:
    """
    Wraps both curl_cffi and aiohttp responses with a consistent API.
    Use this in adapters to avoid caring which backend is in use.
    """

    def __init__(self, resp, is_cffi: bool = False):
        self._resp = resp
        self._is_cffi = is_cffi

    @property
    def status(self) -> int:
        if self._is_cffi:
            return self._resp.status_code
        return self._resp.status

    @property
    def headers(self):
        return self._resp.headers

    async def json(self) -> Any:
        if self._is_cffi:
            return self._resp.json()
        return await self._resp.json()

    async def text(self) -> str:
        if self._is_cffi:
            return self._resp.text
        return await self._resp.text()

    async def release(self):
        if not self._is_cffi:
            await self._resp.release()


# ═══════════════════════════════════════════════════════════════════════
# SESSION FACTORY
# ═══════════════════════════════════════════════════════════════════════


class SessionManager:
    """
    Async context manager that creates the best available HTTP session.
    Prefers curl_cffi (TLS impersonation) and falls back to aiohttp.

    Usage:
        async with create_session(rate_limiter) as session:
            resp = await fetch_with_retry(session, "GET", url, rate_limiter=rate_limiter)
    """

    def __init__(
        self,
        rate_limiter: RateLimiter | None = None,
        max_connections: int = 15,
        max_per_host: int = 10,
        proxy: str | None = None,
    ):
        self.rate_limiter = rate_limiter
        self.max_connections = max_connections
        self.max_per_host = max_per_host
        self.proxy = proxy or _next_proxy()  # rotate across proxy pool if configured
        self._session = None
        self.is_cffi = False

    async def __aenter__(self):
        if HAS_CURL_CFFI:
            _log("[http] Using curl_cffi with TLS impersonation (Chrome/Safari/Edge)")
            self._session = CffiAsyncSession(
                max_clients=self.max_connections,
                proxy=self.proxy,
                verify=True,
            )
            self.is_cffi = True
        else:
            _log("[http] curl_cffi not available, falling back to aiohttp")
            connector = aiohttp.TCPConnector(
                limit=self.max_connections,
                limit_per_host=self.max_per_host,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                headers=random_headers(),
                trust_env=True,
            )
            if self.proxy:
                self._session._proxy_url = self.proxy  # type: ignore[attr-defined]
            self.is_cffi = False

        return self._session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            if self.is_cffi:
                await self._session.close()
            else:
                await self._session.close()


def create_session(
    rate_limiter: RateLimiter | None = None,
    max_connections: int = 15,
    max_per_host: int = 10,
    proxy: str | None = None,
) -> SessionManager:
    """
    Create an async HTTP session context manager.

    Prefers curl_cffi (TLS impersonation, defeats Cloudflare/WAF).
    Falls back to aiohttp if curl_cffi is not installed.

    Usage:
        async with create_session(limiter) as session:
            resp = await fetch_with_retry(session, "GET", url, rate_limiter=limiter)
    """
    return SessionManager(
        rate_limiter=rate_limiter,
        max_connections=max_connections,
        max_per_host=max_per_host,
        proxy=proxy,
    )
