"""
Live ATS target smoke validation.

Validates canonical rows in the companies table without running a full scrape.
Bad targets are not deleted; repeated failures are quarantined via is_dead=1.
"""

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from scripts.database.db_utils import (
    get_companies_for_scrape,
    get_connection,
    record_company_validation,
)
from scripts.database.seed_companies import seed_companies
from scripts.utils.http_client import RateLimiter, consume_last_failure, create_session, fetch_with_retry
from scripts.utils.logger import _log
from scripts.utils.target_diagnostics import classify_failure

CORE_PLATFORMS = {
    "greenhouse",
    "lever",
    "ashby",
    "workday",
    "workable",
    "rippling",
    "smartrecruiters",
    "bamboohr",
}


async def _probe(session, limiter: RateLimiter, company: dict) -> dict:
    ats = company["ats"]
    slug = company["slug"]

    try:
        if ats == "greenhouse":
            url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
            resp = await fetch_with_retry(
                session,
                "GET",
                url,
                rate_limiter=limiter,
                log_tag=f"validate/greenhouse/{slug}",
                params={"content": "false"},
                max_retries=1,
            )
        elif ats == "lever":
            url = f"https://api.lever.co/v0/postings/{slug}"
            resp = await fetch_with_retry(
                session, "GET", url, rate_limiter=limiter, log_tag=f"validate/lever/{slug}", max_retries=1
            )
        elif ats == "ashby":
            url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
            resp = await fetch_with_retry(
                session, "GET", url, rate_limiter=limiter, log_tag=f"validate/ashby/{slug}", max_retries=1
            )
        elif ats == "smartrecruiters":
            url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
            resp = await fetch_with_retry(
                session,
                "GET",
                url,
                rate_limiter=limiter,
                log_tag=f"validate/smartrecruiters/{slug}",
                params={"limit": 1, "offset": 0},
                max_retries=1,
            )
        elif ats == "bamboohr":
            url = f"https://{slug}.bamboohr.com/careers/list"
            resp = await fetch_with_retry(
                session,
                "GET",
                url,
                rate_limiter=limiter,
                log_tag=f"validate/bamboohr/{slug}",
                headers={"Accept": "application/json"},
                max_retries=1,
            )
        elif ats == "workable":
            url = f"https://apply.workable.com/api/v3/accounts/{slug}/jobs"
            resp = await fetch_with_retry(
                session,
                "POST",
                url,
                rate_limiter=limiter,
                log_tag=f"validate/workable/{slug}",
                json={"query": "", "location": [], "department": [], "worktype": [], "remote": []},
                max_retries=1,
            )
        elif ats == "rippling":
            url = f"https://ats.rippling.com/api/v1/board/{slug}/jobs"
            resp = await fetch_with_retry(
                session, "GET", url, rate_limiter=limiter, log_tag=f"validate/rippling/{slug}", max_retries=1
            )
        elif ats == "workday":
            parts = slug.split(":")
            if len(parts) != 3 or not parts[1].isdigit():
                return {"status": "bad_target", "category": "bad_target", "error": "malformed_workday_slug"}
            tenant, shard, site = parts
            base_url = f"https://{tenant}.wd{shard}.myworkdayjobs.com"
            payload = {"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""}
            resp = None
            for probe_site in [site, "External", "Jobs", "Careers", "careers", "external"]:
                url = f"{base_url}/wday/cxs/{tenant}/{probe_site}/jobs"
                resp = await fetch_with_retry(
                    session,
                    "POST",
                    url,
                    rate_limiter=limiter,
                    log_tag=f"validate/workday/{tenant}",
                    json=payload,
                    max_retries=0,
                )
                if resp:
                    break
        else:
            return {"status": "unsupported", "category": "bad_target", "error": f"unsupported_ats:{ats}"}

        if resp:
            return {
                "status": "ok",
                "category": "ok",
                "status_code": getattr(resp, "status_code", getattr(resp, "status", 200)),
            }

        failure = consume_last_failure() or classify_failure(error="empty validation response", ats=ats, slug=slug)
        return {
            "status": failure.get("category") or "unknown",
            "category": failure.get("category") or "unknown",
            "status_code": failure.get("status_code"),
            "error": failure.get("error") or "",
        }
    except Exception as e:
        failure = consume_last_failure() or classify_failure(error=e, ats=ats, slug=slug)
        return {
            "status": failure.get("category") or "unknown",
            "category": failure.get("category") or "unknown",
            "status_code": failure.get("status_code"),
            "error": failure.get("error") or str(e),
        }


async def validate_targets(limit: int = 200, platforms: set[str] | None = None, concurrency: int = 8) -> dict:
    platforms = platforms or CORE_PLATFORMS

    conn = get_connection()
    try:
        targets = get_companies_for_scrape(conn, platforms=platforms)
    finally:
        conn.close()

    if not targets:
        _log("[validate-targets] Companies table empty — seeding first.", "WARN")
        seed_companies()
        conn = get_connection()
        try:
            targets = get_companies_for_scrape(conn, platforms=platforms)
        finally:
            conn.close()

    targets.sort(key=lambda c: (c.get("validation_checked_at") or "", c.get("ats") or "", c.get("slug") or ""))
    if limit > 0:
        targets = targets[:limit]

    limiter = RateLimiter()
    semaphore = asyncio.Semaphore(concurrency)
    counts = Counter()

    async with create_session(limiter) as session:

        async def run_one(target):
            async with semaphore:
                result = await _probe(session, limiter, target)
                conn_inner = get_connection()
                try:
                    record_company_validation(conn_inner, target["ats"], target["slug"], result)
                finally:
                    conn_inner.close()
                counts[result.get("category") or result.get("status") or "unknown"] += 1

        await asyncio.gather(*(run_one(t) for t in targets))

    summary = {"checked": len(targets), "counts": dict(sorted(counts.items()))}
    _log(f"[validate-targets] Complete: {summary}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Smoke-validate canonical ATS targets.")
    parser.add_argument("--limit", type=int, default=200, help="Targets to validate. Use 0 for all.")
    parser.add_argument(
        "--platform", action="append", choices=sorted(CORE_PLATFORMS), help="Limit to one or more ATS platforms."
    )
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    platforms = set(args.platform) if args.platform else CORE_PLATFORMS
    asyncio.run(validate_targets(limit=args.limit, platforms=platforms, concurrency=args.concurrency))


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()
