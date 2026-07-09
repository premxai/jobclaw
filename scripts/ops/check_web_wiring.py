#!/usr/bin/env python3
"""Check whether the JobClaw web/API/database deployment is wired correctly.

This script intentionally uses only the Python standard library so it can run
from a laptop, CI shell, or Railway console without installing project deps.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


def _clean_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        raise ValueError("empty URL")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid URL: {value}")
    return value


def _get_json(url: str, timeout: int) -> tuple[int, Any | None, str | None]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "jobclaw-wiring-check/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            try:
                return response.status, json.loads(body), None
            except json.JSONDecodeError:
                return response.status, None, body[:300]
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, None, body[:300]
    except Exception as exc:
        return 0, None, f"{type(exc).__name__}: {exc}"


def _get_text(url: str, timeout: int) -> tuple[int, str | None]:
    req = urllib.request.Request(url, headers={"User-Agent": "jobclaw-wiring-check/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")[:2000]
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def _print_check(ok: bool, title: str, detail: str) -> None:
    marker = "PASS" if ok else "FAIL"
    print(f"[{marker}] {title}")
    print(f"       {detail}")


def _latest_run_age(runs: list[dict[str, Any]]) -> str:
    if not runs:
        return "no runs returned"
    raw = runs[0].get("timestamp") or runs[0].get("run_at")
    if not raw:
        return "latest run has no run_at"
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return f"latest run_at is not parseable: {raw}"
    age = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    scraper = runs[0].get("script_name") or runs[0].get("scraper") or "unknown"
    return f"latest run {scraper} at {raw} ({age.total_seconds() / 3600:.1f}h ago)"


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose JobClaw web/API/DB wiring.")
    parser.add_argument(
        "--api-url",
        default=os.getenv("NEXT_PUBLIC_API_URL") or os.getenv("JOBCLAW_API_INTERNAL_URL") or "",
        help="Base URL of the FastAPI service, e.g. https://api.up.railway.app",
    )
    parser.add_argument(
        "--web-url",
        default=os.getenv("JOBCLAW_WEB_URL") or "",
        help="Optional public web URL to sanity-check, e.g. https://web.up.railway.app",
    )
    parser.add_argument("--hours", type=int, default=48, help="Freshness window for board jobs.")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds.")
    args = parser.parse_args()

    try:
        api_url = _clean_base_url(args.api_url)
    except ValueError as exc:
        print(f"API URL is required and must be valid: {exc}")
        print("Pass --api-url https://YOUR-API-DOMAIN.up.railway.app")
        return 2

    failures = 0
    print(f"Checking JobClaw API: {api_url}")
    print()

    health_status, health, health_error = _get_json(f"{api_url}/health", args.timeout)
    health_ok = health_status == 200 and isinstance(health, dict)
    _print_check(
        health_ok,
        "API /health responds",
        f"status={health_status}" if health_ok else f"status={health_status}, error={health_error}",
    )
    failures += 0 if health_ok else 1

    stats_status, stats, stats_error = _get_json(f"{api_url}/stats", args.timeout)
    stats_ok = stats_status == 200 and isinstance(stats, dict)
    total_jobs = int(stats.get("total_jobs") or 0) if isinstance(stats, dict) else 0
    jobs_last_24h = int(stats.get("jobs_last_24h") or 0) if isinstance(stats, dict) else 0
    _print_check(
        stats_ok and total_jobs > 0,
        "API is connected to a populated jobs database",
        (
            f"total_jobs={total_jobs:,}, jobs_last_24h={jobs_last_24h:,}"
            if stats_ok
            else f"status={stats_status}, error={stats_error}"
        ),
    )
    failures += 0 if stats_ok and total_jobs > 0 else 1

    jobs_path = f"/jobs?per_page=10&recent_hours={args.hours}"
    jobs_status, jobs_data, jobs_error = _get_json(f"{api_url}{jobs_path}", args.timeout)
    jobs = jobs_data.get("jobs", []) if isinstance(jobs_data, dict) else []
    jobs_ok = jobs_status == 200 and bool(jobs)
    _print_check(
        jobs_ok,
        f"API has jobs for the public board window ({args.hours}h)",
        f"returned={len(jobs)} from {jobs_path}" if jobs_status == 200 else f"status={jobs_status}, error={jobs_error}",
    )
    failures += 0 if jobs_ok else 1

    accepted_path = f"/jobs?per_page=10&recent_hours={args.hours}&quality=accepted"
    accepted_status, accepted_data, accepted_error = _get_json(f"{api_url}{accepted_path}", args.timeout)
    accepted_jobs = accepted_data.get("jobs", []) if isinstance(accepted_data, dict) else []
    accepted_ok = accepted_status == 200
    _print_check(
        accepted_ok,
        "Accepted-quality job query works",
        (
            f"accepted_returned={len(accepted_jobs)}; board falls back to real fresh jobs if this is 0"
            if accepted_ok
            else f"status={accepted_status}, error={accepted_error}"
        ),
    )
    failures += 0 if accepted_ok else 1

    runs_status, runs_data, runs_error = _get_json(f"{api_url}/stats/runs?limit=1", args.timeout)
    runs = runs_data if isinstance(runs_data, list) else []
    runs_ok = runs_status == 200 and bool(runs)
    _print_check(
        runs_ok,
        "Scraper run history is visible to the API",
        _latest_run_age(runs) if runs_status == 200 else f"status={runs_status}, error={runs_error}",
    )
    failures += 0 if runs_ok else 1

    if args.web_url:
        try:
            web_url = _clean_base_url(args.web_url)
        except ValueError as exc:
            _print_check(False, "Web URL is valid", str(exc))
            failures += 1
        else:
            web_status, web_text = _get_text(web_url, args.timeout)
            web_ok = web_status == 200 and bool(web_text)
            detail = f"status={web_status}"
            if web_text and "JobClaw is waiting for the backend API" in web_text:
                detail += "; rendered API waiting state"
                web_ok = False
            _print_check(web_ok, "Web page responds", detail if web_ok else detail + f", error={web_text}")
            failures += 0 if web_ok else 1

    print()
    if failures:
        print("Diagnosis: not fully wired yet.")
        print("- If /health fails: fix or redeploy the API service first.")
        print("- If total_jobs is 0: API is connected to an empty/wrong DB.")
        print("- If recent jobs are 0: run/check scraper workflows or widen the freshness window.")
        print("- If web fails but API passes: set JOBCLAW_API_INTERNAL_URL on the web service and redeploy.")
        return 1

    print("Diagnosis: API, DB, fresh jobs, and scraper run history are wired.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
