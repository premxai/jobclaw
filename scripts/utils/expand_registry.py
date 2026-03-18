import json
import re
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
REGISTRY_FILE = PROJECT_ROOT / "config" / "company_registry.json"


def parse_url_for_ats(link: str) -> tuple[str, str, str]:
    """Returns (ats_platform, slug, name_guess) or (None, None, None)"""
    link = link.lower()
    try:
        if "greenhouse.io" in link:
            # handle boards.greenhouse.io and boards-api.greenhouse.io
            slug = link.split("greenhouse.io/")[1].split("/")[0].split("?")[0]
            if slug == "v1":
                slug = link.split("boards/")[1].split("/")[0].split("?")[0]
            if not slug or slug == "embed":
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
            # Extract tenant:shard:site — WorkdayAdapter requires this format
            import re as _re

            m = _re.match(r"https?://([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/([^\s?#]+)", link)
            if m:
                tenant, shard_str, site = m.group(1), m.group(2), m.group(3).rstrip("/")
                shard_num = _re.sub(r"\D", "", shard_str) or "5"
                if tenant in ("www",):
                    return None, None, None
                slug = f"{tenant}:{shard_num}:{site}"
                return "workday", slug, tenant.replace("-", " ").title()
            return None, None, None

        elif "ashbyhq.com" in link:
            slug = link.split("ashbyhq.com/")[1].split("/")[0].split("?")[0]
            if slug == "api":
                return None, None, None
            if not slug:
                return None, None, None
            return "ashby", slug, slug.replace("-", " ").title()

        elif "apply.workable.com" in link:
            slug = link.split("workable.com/")[1].split("/")[0].split("?")[0]
            if slug == "api":
                slug = link.split("accounts/")[1].split("/")[0].split("?")[0]
            if not slug:
                return None, None, None
            return "workable", slug, slug.replace("-", " ").title()

        elif "ats.rippling.com" in link:
            slug = link.split("rippling.com/")[1].split("/")[0].split("?")[0]
            if not slug:
                return None, None, None
            return "rippling", slug, slug.replace("-", " ").title()

    except Exception:
        pass
    return None, None, None


def fetch_and_merge():
    with open(REGISTRY_FILE, encoding="utf-8") as f:
        data = json.load(f)
        registry = data.get("companies", [])

    known_slugs = {f"{c['ats']}::{c['slug']}" for c in registry}
    added_count = 0
    urls_found = set()

    targets = [
        "https://raw.githubusercontent.com/stapply-ai/ats-scrapers/main/ai_companies.json",
        "https://raw.githubusercontent.com/nihalrai/tech-companies-bay-area/master/Bay-Area-Companies-List.csv",
        "https://raw.githubusercontent.com/connor11528/tech-companies-and-startups/master/companies.csv",
        "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Miscellaneous/companies.txt",
    ]

    # 1. Parse local jobs.csv if it exists (since the online link is dead)
    local_jobs = PROJECT_ROOT / "jobs.csv"
    if local_jobs.exists():
        print(f"Fetching data from local file: {local_jobs}")
        try:
            with open(local_jobs, encoding="utf-8", errors="ignore") as f:
                text = f.read()
                links = re.findall(r'https?://[^\s)\]"\'>,]+', text)
                urls_found.update(links)
        except Exception as e:
            print(f"Failed to read local jobs.csv: {e}")

    for url in targets:
        print(f"Fetching data from: {url}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp:
                text = resp.read().decode("utf-8", errors="ignore")

                # Fast URL extraction excluding trailing punctuation from CSVs
                links = re.findall(r'https?://[^\s)\]"\'>,]+', text)
                urls_found.update(links)
        except Exception as e:
            print(f"Failed to fetch {url}: {e}")

    # Process all discovered URLs
    print(f"Processing {len(urls_found)} extracted URLs for ATS slugs...")
    for link in urls_found:
        ats, slug, name = parse_url_for_ats(link)
        if ats and slug:
            key = f"{ats}::{slug}"
            if key not in known_slugs:
                registry.append({"company": name, "ats": ats, "slug": slug})
                known_slugs.add(key)
                added_count += 1

    # Save
    data["companies"] = registry
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    print(f"\n✅ Injection Complete. Added {added_count} new companies to the registry.")
    print(f"Total Companies monitored: {len(registry)}")


if __name__ == "__main__":
    fetch_and_merge()
