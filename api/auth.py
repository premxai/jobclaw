"""
API Key Authentication Middleware for JobClaw.

Simple header-based auth: clients send `X-API-Key: <key>` header.
The key is stored in the JOBCLAW_API_KEY environment variable.

If JOBCLAW_API_KEY is not set, auth is DISABLED (development mode).

Usage:
    # In .env:
    JOBCLAW_API_KEY=your-secret-key-here

    # In requests:
    curl -H "X-API-Key: your-secret-key-here" http://localhost:8000/jobs
"""

import os
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

# Public routes that don't require auth
PUBLIC_ROUTES = {"/", "/health", "/docs", "/redoc", "/openapi.json"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Validate X-API-Key header on protected routes."""

    async def dispatch(self, request: Request, call_next):
        api_key = os.getenv("JOBCLAW_API_KEY")

        # If no key configured, auth is disabled (dev mode)
        if not api_key:
            return await call_next(request)

        # Skip auth for public routes
        path = request.url.path
        if path in PUBLIC_ROUTES or path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/web"):
            return await call_next(request)

        # Skip auth for WebSocket (handled separately)
        if path.startswith("/ws/"):
            return await call_next(request)

        # Validate API key
        provided_key = request.headers.get("X-API-Key", "")
        if provided_key != api_key:
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing API key. Set the X-API-Key header.",
            )

        return await call_next(request)
