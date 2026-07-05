#!/usr/bin/env python3
"""One-time cleanup: recover real Workday site names from malformed slugs.

Background: a real validate_targets.py run found that 20,641 of 22,059
Workday entries in config/company_registry.json's `companies` list store an
entire job-posting URL path in the "site" field instead of a plain site name
(e.g. "boseallaboutme:503:bose_careers/job/us-ma---framingham/software-
engineer-in-test-co-op_r28310" instead of "boseallaboutme:503:bose_careers").
Every request against a malformed slug 404s, and because each distinct job
path is a distinct slug string, one real tenant silently multiplied into
dozens of duplicate rows (worst: 'abb' x60). The bug and the validation gap
that let it in are fixed in scripts/utils/target_diagnostics.py; this script
is the one-time repair of already-committed registry data.

Recovery: the real site name is the substring before the first '/', '?', or
'#' in the malformed "site" field — this is the same rule the validation fix
now enforces going forward. After recovery, entries are deduped by
(tenant, shard, recovered_site), which correctly preserves companies that
legitimately run multiple Workday sites (e.g. Activision Blizzard King has
three: external, blizzard_external_careers, king_external_careers) while
collapsing the job-URL-path duplicates down to one row per real site.

Entries with fewer than 3 colon-separated parts (10 found, all unsalvageable
garbage like slug="wd1") are dropped rather than guessed at.

Usage: python scripts/ops/cleanup_workday_registry_slugs.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

REGISTRY_FILE = PROJECT_ROOT / "config" / "company_registry.json"


def recover_workday_slug(slug: str) -> str | None:
    """Return the recovered tenant:shard:site slug, or None if unsalvageable."""
    parts = slug.split(":")
    if len(parts) != 3:
        return None
    tenant, shard, site = parts
    if not tenant or not shard.isdigit():
        return None
    recovered_site = site.split("/")[0].split("?")[0].split("#")[0].strip()
    if not recovered_site:
        return None
    return f"{tenant}:{shard}:{recovered_site}"


def clean_companies(companies: list[dict]) -> tuple[list[dict], dict]:
    """Recover + dedupe workday entries; pass every other ats through untouched."""
    stats = {"workday_before": 0, "workday_after": 0, "dropped_unsalvageable": 0, "non_workday": 0}
    canonical: dict[str, dict] = {}
    others: list[dict] = []

    for c in companies:
        if (c.get("ats") or "").lower() != "workday":
            others.append(c)
            stats["non_workday"] += 1
            continue
        stats["workday_before"] += 1
        recovered = recover_workday_slug(c.get("slug") or "")
        if recovered is None:
            stats["dropped_unsalvageable"] += 1
            continue
        existing = canonical.get(recovered)
        name = (c.get("company") or "").strip()
        if not existing or len(name) > len(existing.get("company") or ""):
            canonical[recovered] = {"company": name or recovered, "ats": "workday", "slug": recovered}

    stats["workday_after"] = len(canonical)
    cleaned = others + list(canonical.values())
    return cleaned, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report stats without writing the file.")
    args = parser.parse_args()

    data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    companies = data.get("companies", [])
    cleaned, stats = clean_companies(companies)

    print("Workday registry cleanup")
    print("=" * 30)
    print(f"Workday rows before:  {stats['workday_before']}")
    print(f"Workday rows after:   {stats['workday_after']}")
    print(f"Dropped unsalvageable: {stats['dropped_unsalvageable']}")
    print(f"Non-workday rows (untouched): {stats['non_workday']}")
    print(f"Total companies: {len(companies)} -> {len(cleaned)}")

    if args.dry_run:
        print("\n--dry-run: file not modified.")
        return 0

    data["companies"] = cleaned
    REGISTRY_FILE.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
    print(f"\nWrote {REGISTRY_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
