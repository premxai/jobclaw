"""
Career Page Crawler — detects ATS platform from company career pages.

Given a list of company domains, this module:
1. Checks common career page paths (/careers, /jobs, etc.)
2. Detects ATS platform via URL patterns, redirects, and embedded scripts
3. Extracts company slug
4. Adds to registry

Use case: Given a list of startup domains (from YC, Crunchbase, etc.),
automatically detect which ATS they use and add to scraping pipeline.
"""

import asyncio
import re
import sys
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.logger import _log

# Common career page paths to check
CAREER_PATHS = [
    "/careers",
    "/jobs",
    "/join-us",
    "/join",
    "/work-with-us",
    "/about/careers",
    "/company/careers",
]

# ATS detection patterns — checked against final URL and page content
ATS_DETECTION_PATTERNS = {
    "greenhouse": {
        "url_patterns": [
            r"boards\.greenhouse\.io/(\w+)",
            r"boards-api\.greenhouse\.io/v1/boards/(\w+)",
        ],
        "content_patterns": [
            r"greenhouse\.io/embed/job_board/(?:js/)?(\w+)",
            r'data-greenhouse-board="(\w+)"',
        ],
    },
    "lever": {
        "url_patterns": [
            r"jobs\.lever\.co/([\w-]+)",
        ],
        "content_patterns": [
            r"jobs\.lever\.co/([\w-]+)",
            r"api\.lever\.co/v0/postings/([\w-]+)",
        ],
    },
    "workable": {
        "url_patterns": [
            r"apply\.workable\.com/([\w-]+)",
        ],
        "content_patterns": [
            r"apply\.workable\.com/([\w-]+)",
            r"workable\.com/widget/job_board",
        ],
    },
    "ashby": {
        "url_patterns": [
            r"jobs\.ashbyhq\.com/([\w-]+)",
        ],
        "content_patterns": [
            r"jobs\.ashbyhq\.com/([\w-]+)",
        ],
    },
    "workday": {
        "url_patterns": [
            r"(\w+)\.wd\d+\.myworkdayjobs\.com",
        ],
        "content_patterns": [
            r"myworkdayjobs\.com",
        ],
    },
    "rippling": {
        "url_patterns": [
            r"ats\.rippling\.com/([\w-]+)",
        ],
        "content_patterns": [
            r"ats\.rippling\.com/([\w-]+)",
        ],
    },
    "smartrecruiters": {
        "url_patterns": [
            r"(\w+)\.smartrecruiters\.com",
            r"careers\.smartrecruiters\.com/([\w-]+)",
        ],
        "content_patterns": [
            r"smartrecruiters\.com",
        ],
    },
    "bamboohr": {
        "url_patterns": [
            r"(\w+)\.bamboohr\.com",
        ],
        "content_patterns": [
            r"bamboohr\.com/careers",
        ],
    },
}


def detect_ats_from_url(url: str) -> Optional[Tuple[str, str]]:
    """
    Detect ATS and extract slug from URL.
    
    Returns: (ats_name, slug) or None
    """
    for ats, config in ATS_DETECTION_PATTERNS.items():
        for pattern in config.get("url_patterns", []):
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                slug = match.group(1).lower()
                return (ats, slug)
    return None


def detect_ats_from_content(html: str) -> Optional[Tuple[str, str]]:
    """
    Detect ATS from page content (embedded scripts, iframes).
    
    Returns: (ats_name, slug) or None
    """
    for ats, config in ATS_DETECTION_PATTERNS.items():
        for pattern in config.get("content_patterns", []):
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                # Some patterns have groups, some don't
                try:
                    slug = match.group(1).lower()
                except IndexError:
                    slug = None
                if slug:
                    return (ats, slug)
    return None


async def check_career_page(domain: str, timeout: float = 10.0) -> Optional[dict]:
    """
    Check a company domain for career page and detect ATS.
    
    Returns: {"company": name, "ats": ats, "slug": slug, "career_url": url} or None
    """
    try:
        import aiohttp
    except ImportError:
        return None
    
    # Normalize domain
    if not domain.startswith(("http://", "https://")):
        domain = f"https://{domain}"
    
    parsed = urlparse(domain)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    company_name = parsed.netloc.replace("www.", "").split(".")[0].title()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }
    
    async with aiohttp.ClientSession() as session:
        for path in CAREER_PATHS:
            url = f"{base_url}{path}"
            try:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    allow_redirects=True,
                ) as resp:
                    if resp.status != 200:
                        continue
                    
                    final_url = str(resp.url)
                    html = await resp.text()
                    
                    # Check final URL first (handles redirects to ATS)
                    result = detect_ats_from_url(final_url)
                    if result:
                        ats, slug = result
                        return {
                            "company": company_name,
                            "ats": ats,
                            "slug": slug,
                            "career_url": final_url,
                        }
                    
                    # Check page content
                    result = detect_ats_from_content(html)
                    if result:
                        ats, slug = result
                        return {
                            "company": company_name,
                            "ats": ats,
                            "slug": slug,
                            "career_url": final_url,
                        }
            
            except asyncio.TimeoutError:
                continue
            except Exception:
                continue
    
    return None


async def crawl_domains(domains: list[str], concurrency: int = 5) -> list[dict]:
    """
    Crawl multiple domains for ATS detection.
    
    Returns list of detected companies.
    """
    semaphore = asyncio.Semaphore(concurrency)
    
    async def check_with_semaphore(domain: str) -> Optional[dict]:
        async with semaphore:
            result = await check_career_page(domain)
            if result:
                _log(f"[{domain}] Detected {result['ats']}: {result['slug']}")
            return result
    
    tasks = [check_with_semaphore(d) for d in domains]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter out errors and None results
    return [r for r in results if isinstance(r, dict)]


async def run_career_crawler(
    domains: list[str] = None,
    domains_file: str = None,
    concurrency: int = 5,
) -> dict:
    """
    Run career page crawler on provided domains.
    
    Args:
        domains: List of company domains to check
        domains_file: Path to file with domains (one per line)
        concurrency: Max concurrent requests
    
    Returns:
        {"discovered": int, "companies": list}
    """
    if domains_file:
        path = Path(domains_file)
        if path.exists():
            with open(path, "r") as f:
                domains = [line.strip() for line in f if line.strip()]
    
    if not domains:
        _log("No domains provided", "WARN")
        return {"discovered": 0, "companies": []}
    
    _log(f">>> Crawling {len(domains)} domains for ATS detection")
    
    companies = await crawl_domains(domains, concurrency)
    
    _log(f">>> Detected ATS for {len(companies)} companies")
    
    return {
        "discovered": len(companies),
        "companies": companies,
    }


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    # Usage: python career_crawler.py domain1.com domain2.com
    # Or: python career_crawler.py --file domains.txt
    
    if len(sys.argv) < 2:
        print("Usage: python career_crawler.py domain1.com domain2.com")
        print("   Or: python career_crawler.py --file domains.txt")
        sys.exit(1)
    
    if sys.argv[1] == "--file" and len(sys.argv) > 2:
        domains = None
        domains_file = sys.argv[2]
    else:
        domains = sys.argv[1:]
        domains_file = None
    
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    result = asyncio.run(run_career_crawler(domains=domains, domains_file=domains_file))
    
    print(f"\nDiscovered {result['discovered']} companies:")
    for c in result["companies"]:
        print(f"  {c['company']}: {c['ats']} ({c['slug']})")
