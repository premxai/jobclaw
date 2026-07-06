#!/usr/bin/env python3
"""One-time production sync for the Workday registry cleanup.

Background: config/company_registry.json's Workday entries used to store an
entire job-posting URL path in the "site" field instead of a plain site name
(e.g. "boseallaboutme:503:bose_careers/job/us-ma---framingham/software-
engineer-in-test-co-op_r28310"), silently multiplying one real tenant into
dozens of duplicate rows. scripts/ops/cleanup_workday_registry_slugs.py
already fixed the registry FILE (22,063 -> 2,884 rows), and
scripts/utils/target_diagnostics.py now rejects any new malformed slug.

Neither of those touches an already-seeded production database: a fresh
seed_companies() call only inserts/updates rows still present in the
registry (by (ats_type, slug) key) -- it never deletes rows whose slug was
dropped/renamed during the cleanup. Those stale malformed rows would sit in
production forever, still consuming scrape claims, unless explicitly removed.

This script does both steps against whatever DATABASE_URL is configured:
  1. Delete companies rows where ats_type='workday' AND slug LIKE '%/%' --
     a valid tenant:shard:site slug never contains '/', so this precisely
     targets the known bug pattern without touching any legitimate row.
  2. Re-run seed_companies() to upsert the current clean registry.

Safe to run more than once (idempotent): once step 1 has nothing left to
delete, step 2 alone is a normal no-op-ish upsert.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.database.db_utils import get_connection
from scripts.database.seed_companies import seed_companies


def delete_malformed_workday_rows(conn) -> int:
    """Delete companies rows whose Workday slug still has a '/' in the site field.

    Returns the number of rows deleted.
    """
    cursor = conn.cursor()
    cursor.execute("DELETE FROM companies WHERE LOWER(ats_type) = 'workday' AND slug LIKE '%/%'")
    deleted = cursor.rowcount if cursor.rowcount is not None else 0
    conn.commit()
    return deleted


def main() -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM companies WHERE LOWER(ats_type) = 'workday'")
        before = cursor.fetchone()[0]
        print(f"Workday rows before cleanup: {before}")

        deleted = delete_malformed_workday_rows(conn)
        print(f"Deleted malformed rows: {deleted}")
    finally:
        conn.close()

    print("\nRe-seeding from the cleaned registry...")
    seed_companies()

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM companies WHERE LOWER(ats_type) = 'workday'")
        after = cursor.fetchone()[0]
        print(f"\nWorkday rows after cleanup + reseed: {after}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
