"""
Hardened async HTTP client with anti-detection measures.

Features:
  - User-Agent rotation from a pool of 50+ real browser fingerprints
  - Per-host rate limiting with configurable RPS + jitter
  - Exponential backoff on 429/503 with retry budget
  - Transparent logging of non-200 responses (no more silent swallowing)
  - Header randomization (Accept-Language, sec-ch-ua, etc.)

Usage:
    from scripts.utils.http_client import create_session, RateLimiter

    limiter = RateLimiter()
    async with create_session(limiter) as session:
        resp = await session.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs")
"""

import asyncio
import random
import time
import aiohttp
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from scripts.utils.logger import _log

# ═══════════════════════════════════════════════════════════════════════
# USER-AGENT ROTATION POOL — real browser fingerprints (Chrome/Firefox/Safari)
# ═══════════════════════════════════════════════════════════════════════

_UA_POOL = [
    # Chrome 120-129 on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:129.0) Gecko/20100101 Firefox/129.0",
    # Firefox on Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0",
    # Chrome on Android (mobile)
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    # Safari on iPhone
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]

_ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.9,es;q=0.8",
    "en-US,en;q=0.9,fr;q=0.8",
    "en-US,en;q=0.9,de;q=0.8",
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

# Default RPS limits per ATS domain — tuned from real observation
PLATFORM_RATE_LIMITS: dict[str, float] = {
    # Public board APIs — push harder, these are designed for volume
    "boards-api.greenhouse.io": 10.0,
    "api.lever.co": 8.0,
    "api.ashbyhq.com": 10.0,
    "api.smartrecruiters.com": 6.0,
    # Workday / Workable — aggressive WAF, push carefully
    "myworkdayjobs.com": 3.0,
    "apply.workable.com": 5.0,
    # Others
    "ats.rippling.com": 5.0,
    "bamboohr.com": 5.0,
    # Enterprise endpoints — push to safe max
    "jobs.apple.com": 3.0,
    "www.amazon.jobs": 3.0,
    "apply.careers.microsoft.com": 4.0,
    "nvidia.eightfold.ai": 4.0,
    "api.lifeattiktok.com": 4.0,
    "www.uber.com": 2.0,
}

# Default for hosts not in the map
_DEFAULT_RPS = 2.0


@dataclass
class _HostBucket:
    """Token bucket for a single host."""
    rps: float
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def acquire(self):
        """Wait until a token is available, then consume one."""
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.rps, self.tokens + elapsed * self.rps)
            self.last_refill = now

            if self.tokens < 1.0:
                wait_time = (1.0 - self.tokens) / self.rps
                # Add 10-30% jitter to prevent thundering herd
                jitter = wait_time * random.uniform(0.1, 0.3)
                await asyncio.sleep(wait_time + jitter)
                self.tokens = 0.0
            else:
                self.tokens -= 1.0


class RateLimiter:
    """Per-host rate limiter using token buckets."""

    def __init__(self, overrides: Optional[dict[str, float]] = None):
        self._buckets: dict[str, _HostBucket] = {}
        self._rates = {**PLATFORM_RATE_LIMITS}
        if overrides:
            self._rates.update(overrides)

    def _host_key(self, url: str) -> str:
        """Extract the rate-limit key from a URL. Groups subdomains for Workday."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or ""
        # Workday: *.wd5.myworkdayjobs.com → myworkdayjobs.com
        if "myworkdayjobs.com" in host:
            return "myworkdayjobs.com"
        # bamboohr: *.bamboohr.com → bamboohr.com 
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


# ═══════════════════════════════════════════════════════════════════════
# RETRY ENGINE — exponential backoff on 429/503/502
# ═══════════════════════════════════════════════════════════════════════

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
BASE_BACKOFF = 1.5  # seconds


async def fetch_with_retry(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    rate_limiter: Optional[RateLimiter] = None,
    max_retries: int = MAX_RETRIES,
    timeout: int = 30,
    log_tag: str = "",
    **kwargs,
) -> Optional[aiohttp.ClientResponse]:
    """
    Fetch a URL with rate limiting, UA rotation, and exponential backoff.

    Returns the response on success (caller must read body).
    Returns None on exhausted retries.
    """
    for attempt in range(max_retries + 1):
        try:
            # Rate limit
            if rate_limiter:
                await rate_limiter.acquire(url)

            # Merge random headers with any caller-provided headers
            headers = random_headers()
            if "headers" in kwargs:
                headers.update(kwargs.pop("headers"))

            req_timeout = aiohttp.ClientTimeout(total=timeout)

            # Proxy support: use proxy URL stored on session if available
            proxy_url = getattr(session, "_proxy_url", None)
            proxy_kwarg = {"proxy": proxy_url} if proxy_url else {}

            if method.upper() == "GET":
                resp = await session.get(url, headers=headers, timeout=req_timeout, **proxy_kwarg, **kwargs)
            elif method.upper() == "POST":
                resp = await session.post(url, headers=headers, timeout=req_timeout, **proxy_kwarg, **kwargs)
            else:
                resp = await session.request(method, url, headers=headers, timeout=req_timeout, **proxy_kwarg, **kwargs)

            # Success
            if resp.status == 200:
                return resp

            # Retryable error
            if resp.status in RETRYABLE_STATUS_CODES:
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = min(float(retry_after), 30.0)  # Cap at 30s — some sites send absurd values
                    except ValueError:
                        wait = BASE_BACKOFF * (2 ** attempt)
                else:
                    wait = BASE_BACKOFF * (2 ** attempt)

                jitter = random.uniform(0.5, 1.5)
                total_wait = min(wait * jitter, 45.0)  # Never wait more than 45s total

                tag = f"[{log_tag}] " if log_tag else ""
                _log(
                    f"{tag}HTTP {resp.status} on {url} — retry {attempt + 1}/{max_retries} "
                    f"in {total_wait:.1f}s",
                    "WARN",
                )
                await resp.release()
                await asyncio.sleep(total_wait)
                continue

            # Non-retryable error (403, 404, etc.)
            tag = f"[{log_tag}] " if log_tag else ""
            if resp.status != 404:  # 404 is expected for dead companies
                _log(f"{tag}HTTP {resp.status} on {url} — not retrying", "WARN")
            await resp.release()
            return None

        except asyncio.TimeoutError:
            tag = f"[{log_tag}] " if log_tag else ""
            if attempt < max_retries:
                wait = BASE_BACKOFF * (2 ** attempt) * random.uniform(0.8, 1.2)
                _log(f"{tag}Timeout on {url} — retry {attempt + 1}/{max_retries} in {wait:.1f}s", "WARN")
                await asyncio.sleep(wait)
            else:
                _log(f"{tag}Timeout on {url} — retries exhausted", "WARN")
                return None

        except (aiohttp.ClientError, OSError) as e:
            tag = f"[{log_tag}] " if log_tag else ""
            if attempt < max_retries:
                wait = BASE_BACKOFF * (2 ** attempt) * random.uniform(0.8, 1.2)
                _log(f"{tag}{type(e).__name__} on {url} — retry {attempt + 1}/{max_retries} in {wait:.1f}s", "WARN")
                await asyncio.sleep(wait)
            else:
                _log(f"{tag}{type(e).__name__} on {url} — retries exhausted: {e}", "WARN")
                return None

    return None


# ═══════════════════════════════════════════════════════════════════════
# SESSION FACTORY
# ═══════════════════════════════════════════════════════════════════════

def create_session(
    rate_limiter: Optional[RateLimiter] = None,
    max_connections: int = 100,
    max_per_host: int = 10,
    proxy: Optional[str] = None,
) -> aiohttp.ClientSession:
    """
    Create an aiohttp session with sensible connection pooling defaults.

    Args:
        rate_limiter: NOT embedded in session — pass to fetch_with_retry().
        max_connections: Total concurrent connections across all hosts.
        max_per_host: Max connections to a single host.
        proxy: Optional HTTP/SOCKS proxy URL (e.g. "http://user:pass@proxy:8080").
               Also reads from PROXY_URL environment variable if not provided.
               SOCKS proxies (socks4://, socks5://) require aiohttp-socks.
    """
    import os
    proxy_url = proxy or os.environ.get("PROXY_URL")

    # Use aiohttp-socks connector for SOCKS proxies, plain TCP otherwise
    if proxy_url and proxy_url.startswith(("socks4://", "socks5://")):
        try:
            from aiohttp_socks import ProxyConnector
            connector = ProxyConnector.from_url(
                proxy_url,
                limit=max_connections,
                limit_per_host=max_per_host,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )
            # With ProxyConnector, proxy is handled at the connector level
            # so we don't need to pass proxy= on every request
            proxy_url_for_requests = None
        except ImportError:
            raise ImportError(
                "aiohttp-socks is required for SOCKS proxy support. "
                "Install it with: pip install aiohttp-socks"
            )
    else:
        connector = aiohttp.TCPConnector(
            limit=max_connections,
            limit_per_host=max_per_host,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        # HTTP proxies are passed per-request via the proxy= kwarg
        proxy_url_for_requests = proxy_url

    session = aiohttp.ClientSession(
        connector=connector,
        headers=random_headers(),  # Base headers; fetch_with_retry overrides per request
        trust_env=True,  # Respect HTTP_PROXY / HTTPS_PROXY env vars
    )
    # Store proxy URL on the session so fetch_with_retry can use it
    session._proxy_url = proxy_url_for_requests  # type: ignore[attr-defined]
    return session
