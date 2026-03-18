"""
ATS Company Discovery via Search Engine — finds new companies using known ATS platforms.

Uses Brave Search API (or fallback search) to discover companies by searching for:
  site:boards.greenhouse.io
  site:jobs.lever.co
  site:apply.workable.com
  site:jobs.ashbyhq.com

Extracts company slugs from URLs and adds new ones to the registry.
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from scripts.utils.logger import _log

BRAVE_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

# ATS patterns for company slug extraction.
# Each platform has multiple keyword-varied queries to maximize unique company discovery.
# Budget: ~32 discovery queries/day × 20 results = ~640 candidates → 60-180 new companies/day.
# Monthly usage: 30 (job scrape) + 32 (discovery) = 62/day = 1,860/month (free tier: 2,000).
ATS_DISCOVERY_PATTERNS = {
    "greenhouse": {
        "search_queries": [
            "site:boards.greenhouse.io software engineer",
            "site:boards.greenhouse.io machine learning engineer",
            "site:boards.greenhouse.io data scientist",
            "site:boards.greenhouse.io backend engineer",
            "site:boards.greenhouse.io hiring 2026",
        ],
        "url_patterns": [
            r"boards\.greenhouse\.io/(\w+)",
            r"boards-api\.greenhouse\.io/v1/boards/(\w+)",
            r"job-boards\.greenhouse\.io/(\w+)",
        ],
    },
    "lever": {
        "search_queries": [
            "site:jobs.lever.co software engineer",
            "site:jobs.lever.co machine learning",
            "site:jobs.lever.co data engineer",
            "site:jobs.lever.co hiring",
        ],
        "url_patterns": [
            r"jobs\.lever\.co/([\w-]+)",
        ],
    },
    "ashby": {
        "search_queries": [
            "site:jobs.ashbyhq.com software engineer",
            "site:jobs.ashbyhq.com engineer 2026",
            "site:jobs.ashbyhq.com data",
        ],
        "url_patterns": [
            r"jobs\.ashbyhq\.com/([\w-]+)",
        ],
    },
    "workable": {
        "search_queries": [
            "site:apply.workable.com software engineer",
            "site:apply.workable.com data engineer",
        ],
        "url_patterns": [
            r"apply\.workable\.com/([\w-]+)",
        ],
    },
    "rippling": {
        "search_queries": [
            "site:ats.rippling.com software engineer",
            "site:ats.rippling.com engineer",
        ],
        "url_patterns": [
            r"ats\.rippling\.com/([\w-]+)",
        ],
    },
    "smartrecruiters": {
        "search_queries": [
            "site:jobs.smartrecruiters.com software engineer",
            "site:jobs.smartrecruiters.com data scientist",
        ],
        "url_patterns": [
            r"jobs\.smartrecruiters\.com/([\w-]+)",
        ],
    },
    "bamboohr": {
        "search_queries": [
            "site:bamboohr.com/careers software engineer",
        ],
        "url_patterns": [
            r"([\w-]+)\.bamboohr\.com",
        ],
    },
    "workday": {
        "search_queries": [
            "site:myworkdayjobs.com software engineer",
            "site:myworkdayjobs.com data scientist",
            "site:myworkdayjobs.com machine learning",
            "site:myworkdayjobs.com data engineer",
            "site:myworkdayjobs.com backend engineer",
        ],
        "url_patterns": [
            r"([\w-]+)\.myworkdayjobs\.com",
            r"([\w-]+)\.wd\d+\.myworkdayjobs\.com",
        ],
    },
    "gem": {
        "search_queries": [
            "site:job-boards.gem.com software engineer",
            "site:job-boards.gem.com data scientist",
        ],
        "url_patterns": [
            r"job-boards\.gem\.com/([\w-]+)",
        ],
    },
}


def extract_slug_from_url(url: str, ats: str) -> Optional[str]:
    """Extract company slug from ATS URL."""
    patterns = ATS_DISCOVERY_PATTERNS.get(ats, {}).get("url_patterns", [])
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            slug = match.group(1).lower()
            # Filter out common non-company slugs
            if slug in ("embed", "api", "v1", "v0", "jobs", "careers", "www"):
                continue
            return slug
    return None


async def search_brave(query: str, count: int = 20) -> list[dict]:
    """Search Brave API and return results."""
    if not BRAVE_API_KEY:
        _log("BRAVE_SEARCH_API_KEY not set — skipping discovery", "WARN")
        return []
    
    try:
        import aiohttp
    except ImportError:
        _log("aiohttp not installed — skipping discovery", "WARN")
        return []
    
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_API_KEY,
    }
    params = {
        "q": query,
        "count": count,
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BRAVE_SEARCH_URL, headers=headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("web", {}).get("results", [])
                else:
                    _log(f"Brave API error: {resp.status}", "WARN")
                    return []
    except Exception as e:
        _log(f"Brave search failed: {e}", "ERROR")
        return []


async def discover_companies_for_ats(ats: str, existing_slugs: set) -> list[dict]:
    """
    Discover new companies for a specific ATS platform.

    Runs all search_queries for the platform (1-second gap between calls to
    respect Brave rate limits). Deduplicates against existing_slugs in-place.

    Returns list of new company dicts: {"company": name, "ats": ats, "slug": slug}
    """
    config = ATS_DISCOVERY_PATTERNS.get(ats)
    if not config:
        return []

    queries = config.get("search_queries", [])
    if not queries:
        return []

    discovered = []
    for i, query in enumerate(queries):
        if i > 0:
            await asyncio.sleep(1)  # 1 req/s — stay within Brave free tier

        results = await search_brave(query, count=20)
        for result in results:
            url = result.get("url", "")
            title = result.get("title", "")

            slug = extract_slug_from_url(url, ats)
            if slug and slug not in existing_slugs:
                company_name = title.split(" - ")[0].split(" | ")[0].strip()
                if not company_name or len(company_name) < 2:
                    company_name = slug.replace("-", " ").title()

                discovered.append({
                    "company": company_name,
                    "ats": ats,
                    "slug": slug,
                })
                existing_slugs.add(slug)  # Avoid duplicates within this run

    return discovered


def load_existing_slugs() -> dict[str, set]:
    """Load existing company slugs from registry and CSV files."""
    slugs_by_ats = {}
    
    # Load from company_registry.json
    registry_path = PROJECT_ROOT / "config" / "company_registry.json"
    if registry_path.exists():
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for company in data.get("companies", []):
                    ats = company.get("ats", "").lower()
                    slug = company.get("slug", "").lower()
                    if ats and slug:
                        if ats not in slugs_by_ats:
                            slugs_by_ats[ats] = set()
                        slugs_by_ats[ats].add(slug)
        except (json.JSONDecodeError, KeyError):
            pass
    
    # Load from CSV files
    import csv
    csv_files = {
        "greenhouse": "greenhouse_companies.csv",
        "lever": "lever_companies.csv",
        "workable": "workable_companies.csv",
        "workday": "workday_companies.csv",
        "rippling": "rippling_companies.csv",
        "ashby": "ashby_companies.csv",
        "gem": "gem_companies.csv",
    }
    
    for ats, filename in csv_files.items():
        csv_path = PROJECT_ROOT / "data" / filename
        if csv_path.exists():
            try:
                with open(csv_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Extract slug from URL
                        url = row.get("url", "")
                        slug = extract_slug_from_url(url, ats)
                        if slug:
                            if ats not in slugs_by_ats:
                                slugs_by_ats[ats] = set()
                            slugs_by_ats[ats].add(slug)
            except Exception:
                pass
    
    return slugs_by_ats


def save_discoveries(discoveries: list[dict]) -> int:
    """
    Save discovered companies to the registry.
    
    Returns number of companies added.
    """
    if not discoveries:
        return 0
    
    registry_path = PROJECT_ROOT / "config" / "company_registry.json"
    
    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"companies": []}
    
    # Build existing key set
    existing = {f"{c['ats']}:{c['slug']}" for c in data.get("companies", [])}
    
    added = 0
    for company in discoveries:
        key = f"{company['ats']}:{company['slug']}"
        if key not in existing:
            data["companies"].append(company)
            existing.add(key)
            added += 1
    
    if added > 0:
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    return added


async def run_discovery(platforms: list[str] = None) -> dict:
    """
    Run company discovery for specified ATS platforms.
    
    Args:
        platforms: List of ATS names to discover. Default: all discoverable.
    
    Returns:
        {"discovered": int, "by_ats": {ats: count}}
    """
    if platforms is None:
        platforms = list(ATS_DISCOVERY_PATTERNS.keys())
    
    _log(f">>> Starting ATS Company Discovery for: {', '.join(platforms)}")
    
    existing = load_existing_slugs()
    total_existing = sum(len(s) for s in existing.values())
    _log(f"Loaded {total_existing} existing company slugs")
    
    all_discoveries = []
    by_ats = {}
    
    for ats in platforms:
        existing_for_ats = existing.get(ats, set())
        discoveries = await discover_companies_for_ats(ats, existing_for_ats)
        
        if discoveries:
            _log(f"[{ats}] Discovered {len(discoveries)} new companies")
            all_discoveries.extend(discoveries)
            by_ats[ats] = len(discoveries)
        else:
            _log(f"[{ats}] No new companies found")
        
        # Rate limit between searches
        await asyncio.sleep(1)
    
    # Save to registry
    added = save_discoveries(all_discoveries)
    _log(f">>> Discovery complete: {added} new companies added to registry")
    
    return {
        "discovered": added,
        "by_ats": by_ats,
    }


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    platforms = sys.argv[1:] if len(sys.argv) > 1 else None
    
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    result = asyncio.run(run_discovery(platforms))
    print(f"\nDiscovered {result['discovered']} new companies")
    if result['by_ats']:
        for ats, count in result['by_ats'].items():
            print(f"  {ats}: {count}")
