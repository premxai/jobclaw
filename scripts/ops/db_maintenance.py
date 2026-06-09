"""Run JobClaw database retention and compaction.

This is intentionally small and safe to run from GitHub Actions, Railway, or a
local shell. It trims bulky job descriptions, removes stale low-quality rows,
archives stale unposted jobs, and prunes old scraper run records.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.database.db_utils import get_connection, run_database_maintenance
from scripts.utils.logger import _log


def main() -> int:
    conn = get_connection()
    try:
        summary = run_database_maintenance(conn)
    finally:
        conn.close()

    _log(f"[db-maintenance] {json.dumps(summary, sort_keys=True)}")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
