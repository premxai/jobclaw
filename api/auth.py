"""
API Key Authentication Middleware for JobClaw.

Header-based auth: clients send `X-API-Key: <key>` header. The key is stored in
the JOBCLAW_API_KEY environment variable.

Posture (see plan: "public reads, locked writes"):
  - GET on public read prefixes (/jobs, /board, /stats, /companies) is always allowed so the
    website works without a key.
  - Mutating / admin routes (/scraper, /admin, /applications, /resume) and any other
    non-GET request ALWAYS require a valid key. If no key is configured, these routes
    FAIL CLOSED (503) so writes can never be accidentally exposed in production.
  - When no key is configured, read-only requests are still allowed (dev convenience).

Usage:
    # In .env (REQUIRED in production):
    JOBCLAW_API_KEY=your-secret-key-here

    # In requests:
    curl -H "X-API-Key: your-secret-key-here" http://localhost:8000/applications
"""

import hmac
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Routes that never require auth.
PUBLIC_ROUTES = {"/", "/health", "/health/deep", "/docs", "/redoc", "/openapi.json"}
PUBLIC_PREFIXES = ("/docs", "/redoc", "/web")
# GETs under these prefixes are public so the website can read without a key.
PUBLIC_GET_PREFIXES = ("/jobs", "/board", "/stats", "/companies")
# Anything under these prefixes is a mutation/admin action and always needs a key.
PROTECTED_PREFIXES = ("/scraper", "/admin", "/applications", "/resume")
# Read-only HTTP methods.
SAFE_METHODS = {"GET", "HEAD"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Validate X-API-Key header; fail closed on writes when no key is configured."""

    async def dispatch(self, request, call_next):
        path = request.url.path
        method = request.method

        # Let CORS preflight through (handled by CORSMiddleware downstream).
        if method == "OPTIONS":
            return await call_next(request)

        # Always-public routes (health, docs, root, static web).
        if path in PUBLIC_ROUTES or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)

        # WebSocket upgrades authenticate themselves (token in the handshake).
        if path.startswith("/ws/"):
            return await call_next(request)

        api_key = os.getenv("JOBCLAW_API_KEY")

        # A request is a "write" if it uses an unsafe method OR targets an admin/
        # mutation prefix (covers e.g. GET /admin/* helpers too).
        is_write = method not in SAFE_METHODS or path.startswith(PROTECTED_PREFIXES)

        # No key configured: allow reads (dev), but FAIL CLOSED on writes/admin so a
        # misconfigured production deploy never exposes mutations.
        if not api_key:
            if is_write:
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "API authentication is not configured; mutating and admin "
                        "endpoints are disabled. Set JOBCLAW_API_KEY to enable them."
                    },
                )
            return await call_next(request)

        # Key configured: public reads stay open.
        if method in SAFE_METHODS and path.startswith(PUBLIC_GET_PREFIXES) and not path.startswith(PROTECTED_PREFIXES):
            return await call_next(request)

        # Everything else requires a valid key (constant-time compare).
        provided_key = request.headers.get("X-API-Key", "")
        if not provided_key or not hmac.compare_digest(provided_key, api_key):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key. Set the X-API-Key header."},
            )

        return await call_next(request)
