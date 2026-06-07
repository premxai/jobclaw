#!/usr/bin/env python3
"""Print a compact scraper control-plane report."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.database.db_utils import get_connection, get_scraper_control_snapshot, is_postgres


def _rows(conn, sql: str, params: tuple = ()) -> list[dict]:
    cursor = conn.cursor()
    cursor.execute(sql, params)
    return [
        dict(row) if hasattr(row, "keys") else dict(zip([desc[0] for desc in cursor.description], row))
        for row in cursor.fetchall()
    ]


def main() -> int:
    conn = get_connection()
    try:
        snapshot = get_scraper_control_snapshot(conn)
        print("JobClaw Scraper Control Plane")
        print("=" * 34)
        print(f"Mode: {snapshot['mode']}")
        print(f"Due backlog: {snapshot['backlog_due']}")
        print(f"Active leases: {snapshot['leased']}")
        print(f"Dead/quarantined targets: {snapshot['dead_targets']}")
        print(f"Stale P0/P1 targets: {snapshot['stale_hot_targets']}")

        print("\nPlatform health")
        for platform in snapshot["platforms"][:12]:
            avg_score = platform.get("avg_score") or 0
            print(
                f"- {platform.get('platform')}: targets={platform.get('targets', 0)} "
                f"leased={platform.get('leased', 0)} dead={platform.get('dead', 0)} "
                f"avg_score={float(avg_score):.2f}"
            )

        print("\nTop failing targets")
        if snapshot["top_failing_targets"]:
            for target in snapshot["top_failing_targets"]:
                print(
                    f"- {target.get('ats_type')}/{target.get('slug')} "
                    f"failures={target.get('consecutive_failures')} "
                    f"category={target.get('failure_category') or 'unknown'}"
                )
        else:
            print("- none")

        active_expr = "TRUE" if is_postgres() else "1"
        recent = _rows(
            conn,
            f"""
            SELECT title, company, source_ats, first_seen, source_confidence
            FROM jobs
            WHERE is_active = {active_expr}
              AND COALESCE(quality_state, 'needs_review') = 'accepted'
            ORDER BY first_seen DESC
            LIMIT 10
            """,
        )
        print("\nLatest accepted jobs")
        if recent:
            for job in recent:
                print(
                    f"- {job.get('title')} @ {job.get('company')} "
                    f"({job.get('source_ats')}, confidence={job.get('source_confidence')})"
                )
        else:
            print("- none")

        print("\nJSON")
        print(json.dumps(snapshot, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
