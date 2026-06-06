import sys
import json
from collections import Counter
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.database.db_utils import compute_company_priority, get_connection, get_hot_slugs, is_postgres
from scripts.utils.target_diagnostics import normalize_registry_target

REGISTRY_FILE = PROJECT_ROOT / "config" / "company_registry.json"


def load_registry() -> list[dict[str, str]]:
    """Load and normalize config/company_registry.json without scraper dependencies."""
    if not REGISTRY_FILE.exists():
        return []

    data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    flat_registry: list[dict[str, str]] = []

    def append(company: str, ats: str, slug: str):
        normalized, _reason = normalize_registry_target(company, ats, slug)
        if normalized:
            flat_registry.append(normalized)

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                append(
                    item.get("company", "") or item.get("name", ""),
                    item.get("ats", ""),
                    item.get("slug", "") or item.get("url", ""),
                )
        return flat_registry

    if isinstance(data, dict):
        if isinstance(data.get("companies"), list):
            for c in data["companies"]:
                append(c.get("company", "") or c.get("name", ""), c.get("ats", ""), c.get("slug", "") or c.get("url", ""))

        for platform, companies in data.items():
            if platform == "companies" or not isinstance(companies, list):
                continue
            for c in companies:
                append(
                    c.get("name", "") or c.get("company", ""),
                    platform,
                    c.get("slug", "") or c.get("url", ""),
                )

    return flat_registry


def seed_companies():
    """Seed the canonical companies table from company_registry.json and tag P0 tiers.

    Runtime scrapers read from the DB, not directly from the raw registry. The
    raw registry intentionally keeps duplicates from multiple discovery sources;
    this seeder collapses them by (ats_type, slug) and stores source_count.
    """
    print(">>> Seeding companies table...")

    registry = load_registry()
    hot_slugs = get_hot_slugs()

    if not registry:
        print("Error: Registry is empty.")
        return

    conn = get_connection()
    cursor = conn.cursor()

    canonical = {}
    source_counts = Counter()
    for c in registry:
        ats = (c.get("ats") or "").lower().strip()
        slug = (c.get("slug") or "").strip()
        name = (c.get("company") or c.get("name") or slug).strip()
        if not ats or not slug:
            continue
        key = (ats, slug)
        source_counts[key] += 1
        existing = canonical.get(key)
        if not existing or len(name) > len(existing["name"]):
            canonical[key] = {"name": name, "ats": ats, "slug": slug}

    count = 0
    hot_tagged = 0

    try:
        BATCH_SIZE = 100
        for i, c in enumerate(canonical.values()):
            name = c.get("company")
            if name is None:
                name = c.get("name")
            ats = c.get("ats")
            slug = c.get("slug")

            if not slug:
                continue

            tier = "P2"
            if slug in hot_slugs or name in hot_slugs:
                tier = "P0"
                hot_tagged += 1
            priority_score = compute_company_priority(
                {
                    "tier": tier,
                    "source_count": source_counts[(ats, slug)],
                    "total_jobs_found": 0,
                    "total_relevant_jobs_found": 0,
                    "consecutive_failures": 0,
                }
            )

            try:
                if is_postgres():
                    cursor.execute(
                        """
                        INSERT INTO companies (slug, name, ats_type, tier, source_count, priority_score, next_scrape_at)
                        VALUES (%s, %s, %s, %s, %s, %s, NULL)
                        ON CONFLICT (ats_type, slug) DO UPDATE SET
                            name = EXCLUDED.name,
                            tier = CASE
                                WHEN companies.tier = 'P0' OR EXCLUDED.tier = 'P0' THEN 'P0'
                                ELSE EXCLUDED.tier
                            END,
                            source_count = EXCLUDED.source_count,
                            priority_score = GREATEST(companies.priority_score, EXCLUDED.priority_score)
                    """,
                        (slug, name, ats, tier, source_counts[(ats, slug)], priority_score),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO companies (slug, name, ats_type, tier, source_count, priority_score, next_scrape_at)
                        VALUES (?, ?, ?, ?, ?, ?, NULL)
                        ON CONFLICT (ats_type, slug) DO UPDATE SET
                            name = excluded.name,
                            tier = CASE
                                WHEN companies.tier = 'P0' OR excluded.tier = 'P0' THEN 'P0'
                                ELSE excluded.tier
                            END,
                            source_count = excluded.source_count,
                            priority_score = MAX(companies.priority_score, excluded.priority_score)
                    """,
                        (slug, name, ats, tier, source_counts[(ats, slug)], priority_score),
                    )
                count += 1

                if count % BATCH_SIZE == 0:
                    conn.commit()
                    print(f"Processed {count}/{len(canonical)} canonical companies...")
            except Exception as e:
                print(f"Error inserting {ats}/{slug}: {e}")

        conn.commit()
        print(
            f"Successfully seeded {count} canonical companies "
            f"from {len(registry)} registry entries ({hot_tagged} tagged as P0/Hot)."
        )

    finally:
        conn.close()


if __name__ == "__main__":
    seed_companies()
