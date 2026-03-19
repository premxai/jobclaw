"""
expand_registry.py — Auto-expand the company ATS registry from multiple sources.

Sources (in priority order):
  1. SimplifyJobs GitHub repos — pre-parsed ATS URLs from intern/new-grad lists
  2. YC company directory (Algolia public API) — 4,000+ funded startups
  3. GitHub open company lists (original + new)
  4. Brave Search reverse-ATS discovery — site:greenhouse.io/jobs etc.
  5. Local jobs.csv URL extraction

Run daily via expand_registry.yml GitHub Action.
"""

import gzip
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
REGISTRY_FILE = PROJECT_ROOT / "config" / "company_registry.json"

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

BRAVE_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


# ─────────────────────────────────────────────────────────────────────────────
# ATS URL PARSER
# ─────────────────────────────────────────────────────────────────────────────

def parse_url_for_ats(link: str) -> tuple:
    """Returns (ats_platform, slug, name_guess) or (None, None, None)"""
    link = link.lower()
    try:
        if "greenhouse.io" in link:
            slug = link.split("greenhouse.io/")[1].split("/")[0].split("?")[0]
            if slug == "v1":
                try:
                    slug = link.split("boards/")[1].split("/")[0].split("?")[0]
                except IndexError:
                    return None, None, None
            if not slug or slug in ("embed", "jobs"):
                return None, None, None
            return "greenhouse", slug, slug.replace("-", " ").title()

        elif "lever.co" in link:
            if "api.lever.co" in link:
                slug = link.split("postings/")[1].split("/")[0].split("?")[0]
            else:
                slug = link.split("lever.co/")[1].split("/")[0].split("?")[0]
            if not slug:
                return None, None, None
            return "lever", slug, slug.replace("-", " ").title()

        elif "myworkdayjobs.com" in link:
            m = re.match(r"https?://([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/([^\s?#]+)", link)
            if m:
                tenant, shard_str, site = m.group(1), m.group(2), m.group(3).rstrip("/")
                shard_num = re.sub(r"\D", "", shard_str) or "5"
                if tenant in ("www",):
                    return None, None, None
                slug = f"{tenant}:{shard_num}:{site}"
                return "workday", slug, tenant.replace("-", " ").title()
            return None, None, None

        elif "ashbyhq.com" in link:
            slug = link.split("ashbyhq.com/")[1].split("/")[0].split("?")[0]
            if slug in ("api", ""):
                return None, None, None
            return "ashby", slug, slug.replace("-", " ").title()

        elif "apply.workable.com" in link:
            slug = link.split("workable.com/")[1].split("/")[0].split("?")[0]
            if slug == "api":
                try:
                    slug = link.split("accounts/")[1].split("/")[0].split("?")[0]
                except IndexError:
                    return None, None, None
            if not slug:
                return None, None, None
            return "workable", slug, slug.replace("-", " ").title()

        elif "ats.rippling.com" in link:
            slug = link.split("rippling.com/")[1].split("/")[0].split("?")[0]
            if not slug:
                return None, None, None
            return "rippling", slug, slug.replace("-", " ").title()

        elif "jobs.smartrecruiters.com" in link:
            slug = link.split("smartrecruiters.com/")[1].split("/")[0].split("?")[0]
            if not slug or slug in ("api", "jobs"):
                return None, None, None
            return "smartrecruiters", slug, slug.replace("-", " ").title()

        elif "bamboohr.com" in link and ("/careers" in link or "/jobs" in link):
            slug = link.split("bamboohr.com/")[1].split("/")[0]
            if not slug:
                return None, None, None
            return "bamboohr", slug, slug.replace("-", " ").title()

        elif "gem.com/" in link and "/jobs" in link:
            slug = link.split("gem.com/")[1].split("/")[0].split("?")[0]
            if not slug:
                return None, None, None
            return "gem", slug, slug.replace("-", " ").title()

    except Exception:
        pass
    return None, None, None


def _http_get(url: str, timeout: int = 12) -> str | None:
    """Simple synchronous HTTP GET. Returns text or None on failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 JobclawBot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            # Handle gzip-encoded responses
            if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            return raw.decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  ⚠ Failed to fetch {url[:60]}: {e}")
        return None


def _extract_urls(text: str) -> set:
    return set(re.findall(r'https?://[^\s)\]"\'><,\|]+', text))


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 1: SimplifyJobs — pre-parsed ATS apply links
# ─────────────────────────────────────────────────────────────────────────────

SIMPLIFY_SOURCES = [
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2025-Internships/dev/.github/scripts/listings.json",
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json",
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/.github/scripts/listings.json",
    # Also try the markdown README which has clickable apply links
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/main/README.md",
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/main/README.md",
]


def _fetch_simplify_urls() -> set:
    urls: set = set()
    for url in SIMPLIFY_SOURCES:
        print(f"[SimplifyJobs] Fetching: {url}")
        text = _http_get(url)
        if not text:
            continue
        # Try JSON format first
        if url.endswith(".json"):
            try:
                listings = json.loads(text)
                for item in listings:
                    for link_obj in item.get("links", []):
                        u = link_obj.get("url", "") if isinstance(link_obj, dict) else str(link_obj)
                        if u:
                            urls.add(u)
                    if item.get("url"):
                        urls.add(item["url"])
                continue
            except Exception:
                pass
        # Fallback: raw URL extraction
        urls.update(_extract_urls(text))

    print(f"  → {len(urls)} total URLs from SimplifyJobs")
    return urls


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 2: YC company directory via Algolia public API
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_yc_urls() -> set:
    """YC Algolia search — returns up to 4,000+ company websites."""
    urls: set = set()
    print("[YC] Fetching Y Combinator companies via Algolia API...")
    api_url = (
        "https://45bwzj1sgc-dsn.algolia.net/1/indexes/YCCompany_production/query"
        "?x-algolia-application-id=45BWZJ1SGC"
        "&x-algolia-api-key=Zjk5ZmI5ODBkMGJiNGJjNTc4ZTVlMmRiZjY4OWFmYjkyZDZjNjNlNjBlOWI5OWUzOGM3MDEzNWM5ZjhmOWMxYg=="
    )
    page = 0
    while True:
        payload = json.dumps({"query": "", "page": page, "hitsPerPage": 1000}).encode()
        try:
            req = urllib.request.Request(
                api_url,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                hits = data.get("hits", [])
                if not hits:
                    break
                for company in hits:
                    website = company.get("website", "")
                    if website:
                        urls.add(website)
                if len(hits) < 1000:
                    break
                page += 1
                time.sleep(0.3)
        except Exception as e:
            print(f"  ⚠ YC API error (page {page}): {e}")
            break

    print(f"  → {len(urls)} YC company websites found")
    return urls


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 3: GitHub open company lists (original + additional)
# ─────────────────────────────────────────────────────────────────────────────

GITHUB_SOURCES = [
    # Original sources
    "https://raw.githubusercontent.com/stapply-ai/ats-scrapers/main/ai_companies.json",
    "https://raw.githubusercontent.com/nihalrai/tech-companies-bay-area/master/Bay-Area-Companies-List.csv",
    "https://raw.githubusercontent.com/connor11528/tech-companies-and-startups/master/companies.csv",
    "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Miscellaneous/companies.txt",
    # New sources
    "https://raw.githubusercontent.com/poteto/hiring-without-whiteboards/master/README.md",
    "https://raw.githubusercontent.com/remoteintech/remote-jobs/main/README.md",
    "https://raw.githubusercontent.com/tramcar/awesome-job-boards/master/README.md",
    "https://raw.githubusercontent.com/philipwalton/easy-wins/main/README.md",
    "https://raw.githubusercontent.com/Kajalrana01/Top-tech-companies/main/README.md",
    # Crowdsourced ATS lists
    "https://raw.githubusercontent.com/coderQuad/New-Grad-Positions-2023/master/README.md",
    "https://raw.githubusercontent.com/ReaVNaiL/New-Grad-2024/main/README.md",
    "https://raw.githubusercontent.com/pittcsc/Summer2023-Internships/dev/README.md",
]


def _fetch_github_urls() -> set:
    urls: set = set()
    for url in GITHUB_SOURCES:
        print(f"[GitHub] Fetching: {url}")
        text = _http_get(url)
        if text:
            found = _extract_urls(text)
            urls.update(found)
    print(f"  → {len(urls)} total URLs from GitHub sources")
    return urls


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 4: Brave Search reverse-ATS discovery
# ─────────────────────────────────────────────────────────────────────────────

BRAVE_ATS_QUERIES = [
    # Greenhouse — largest ATS
    "site:boards.greenhouse.io software engineer",
    "site:boards.greenhouse.io machine learning engineer",
    "site:boards.greenhouse.io data engineer",
    "site:boards.greenhouse.io new grad 2026",
    "site:boards.greenhouse.io AI engineer",
    # Lever
    "site:jobs.lever.co software engineer",
    "site:jobs.lever.co machine learning engineer",
    "site:jobs.lever.co data scientist",
    "site:jobs.lever.co new grad 2026",
    # Ashby
    "site:jobs.ashbyhq.com software engineer",
    "site:jobs.ashbyhq.com machine learning",
    "site:jobs.ashbyhq.com data engineer",
    # Rippling
    "site:ats.rippling.com software engineer",
    "site:ats.rippling.com machine learning",
    # Workable
    "site:apply.workable.com software engineer",
    "site:apply.workable.com data engineer",
    # SmartRecruiters
    "site:jobs.smartrecruiters.com software engineer",
    "site:jobs.smartrecruiters.com machine learning",
]


def _fetch_brave_ats_urls() -> set:
    if not BRAVE_API_KEY:
        print("[Brave] BRAVE_SEARCH_API_KEY not set — skipping reverse-ATS discovery")
        return set()

    urls: set = set()
    print(f"[Brave] Running {len(BRAVE_ATS_QUERIES)} reverse-ATS discovery queries...")

    for query in BRAVE_ATS_QUERIES:
        params = urllib.parse.urlencode({"q": query, "count": "20", "country": "us"})
        api_url = f"{BRAVE_SEARCH_URL}?{params}"
        try:
            req = urllib.request.Request(
                api_url,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": BRAVE_API_KEY,
                    "User-Agent": "Mozilla/5.0",
                    # No Accept-Encoding → server sends plain JSON, not gzip
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
                if raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                data = json.loads(raw.decode("utf-8"))
                for result in data.get("web", {}).get("results", []):
                    u = result.get("url", "")
                    if u:
                        urls.add(u)
        except Exception as e:
            print(f"  ⚠ Brave query failed ({query[:50]}): {e}")

        time.sleep(1.0)  # Brave free tier: 1 req/sec

    print(f"  → {len(urls)} URLs discovered via Brave reverse-ATS")
    return urls


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 5: Local jobs.csv
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_local_urls() -> set:
    urls: set = set()
    local_jobs = PROJECT_ROOT / "jobs.csv"
    if local_jobs.exists():
        print(f"[Local] Reading: {local_jobs}")
        try:
            with open(local_jobs, encoding="utf-8", errors="ignore") as f:
                urls.update(_extract_urls(f.read()))
        except Exception as e:
            print(f"  ⚠ Failed to read jobs.csv: {e}")
    return urls


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def fetch_and_merge():
    with open(REGISTRY_FILE, encoding="utf-8") as f:
        data = json.load(f)
        registry = data.get("companies", [])

    known_slugs = {f"{c['ats']}::{c['slug']}" for c in registry}
    initial_count = len(registry)
    added_count = 0
    added_by_source: dict = {}

    sources = [
        ("local", _fetch_local_urls),
        ("simplify", _fetch_simplify_urls),
        ("yc", _fetch_yc_urls),
        ("github", _fetch_github_urls),
        ("brave", _fetch_brave_ats_urls),
    ]

    for source_name, fetcher in sources:
        source_urls = fetcher()
        source_added = 0
        for link in source_urls:
            ats, slug, name = parse_url_for_ats(link)
            if ats and slug:
                key = f"{ats}::{slug}"
                if key not in known_slugs:
                    registry.append({"company": name, "ats": ats, "slug": slug})
                    known_slugs.add(key)
                    added_count += 1
                    source_added += 1
        added_by_source[source_name] = source_added
        print(f"  [{source_name}] → {source_added} new companies added")

    # Save updated registry
    data["companies"] = registry
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    print(f"\n✅ Registry Expansion Complete.")
    print(f"   Added:    {added_count} new companies")
    print(f"   Before:   {initial_count}")
    print(f"   After:    {len(registry)}")
    print(f"   By source: {added_by_source}")


if __name__ == "__main__":
    fetch_and_merge()
