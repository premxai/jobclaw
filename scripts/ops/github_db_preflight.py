#!/usr/bin/env python3
"""GitHub Actions preflight for DB-backed scheduled jobs.

Exits successfully every time and writes db_ok=true/false to GITHUB_OUTPUT.
Workflow steps can then skip expensive scraper work while the production DB is
unavailable, instead of turning every scheduled run into a noisy failure.
"""

from __future__ import annotations

import json
import os
import urllib.request


def _set_output(name: str, value: str) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        return
    safe_value = value.replace("\r", " ").replace("\n", " ")[:1000]
    with open(output_path, "a", encoding="utf-8") as fh:
        fh.write(f"{name}={safe_value}\n")


def _check_database_url(database_url: str) -> tuple[bool, str]:
    if not database_url:
        return False, "DATABASE_URL is not set"

    if not database_url.startswith("postgres"):
        return True, "non-Postgres DATABASE_URL configured"

    try:
        import psycopg2

        conn = psycopg2.connect(database_url, connect_timeout=10)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
        finally:
            conn.close()
        return True, "Postgres preflight query succeeded"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _check_api_health(api_url: str) -> tuple[bool, str]:
    req = urllib.request.Request(
        api_url, headers={"Accept": "application/json", "User-Agent": "jobclaw-db-preflight/1"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"

    database = data.get("checks", {}).get("database", {})
    if database.get("status") == "ok":
        return True, "API health reports database ok"

    return False, str(database.get("error") or database.get("status") or "API health database check failed")


def main() -> int:
    database_url = os.getenv("DATABASE_URL", "")
    api_url = os.getenv("JOBCLAW_API_HEALTH_URL", "https://api.norinote.xyz/health/deep")

    if database_url:
        ok, reason = _check_database_url(database_url)
        source = "database_url"
    else:
        ok, reason = _check_api_health(api_url)
        source = "api_health"

    _set_output("db_ok", "true" if ok else "false")
    _set_output("source", source)
    _set_output("reason", reason)

    status = "ok" if ok else "unavailable"
    print(f"Production DB preflight {status} via {source}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
