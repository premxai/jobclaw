import os
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

import scripts.database.db_utils as db_utils
from scripts.database.db_utils import _ensure_sqlite_schema, claim_adaptive_companies_for_scrape
from scripts.utils.platform_budgets import apply_platform_budgets


class ScraperControlPlaneTests(unittest.TestCase):
    def setUp(self):
        self._database_url = os.environ.pop("DATABASE_URL", None)
        self._module_database_url = db_utils.DATABASE_URL
        db_utils.DATABASE_URL = ""
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _ensure_sqlite_schema(self.conn)
        self.now = datetime.now(timezone.utc)

    def tearDown(self):
        self.conn.close()
        db_utils.DATABASE_URL = self._module_database_url
        if self._database_url is not None:
            os.environ["DATABASE_URL"] = self._database_url

    def _insert_company(self, slug, ats, tier="P2", priority=0, scrape_score=0, next_due_at=None):
        self.conn.execute(
            """
            INSERT INTO companies (
                slug, name, ats_type, tier, priority_score, scrape_score, next_due_at, is_dead
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (slug, slug.title(), ats, tier, priority, scrape_score, next_due_at),
        )
        self.conn.commit()

    def test_claim_uses_priority_order_and_lease_exclusivity(self):
        due = (self.now - timedelta(minutes=5)).isoformat()
        future = (self.now + timedelta(hours=1)).isoformat()
        self._insert_company("p2", "greenhouse", tier="P2", priority=10, next_due_at=due)
        self._insert_company("p0", "greenhouse", tier="P0", priority=1, next_due_at=due)
        self._insert_company("future", "greenhouse", tier="P0", priority=100, next_due_at=future)

        first_claim = claim_adaptive_companies_for_scrape(
            self.conn,
            limit=2,
            platforms={"greenhouse"},
            lease_owner="worker-a",
            lease_seconds=300,
        )
        second_claim = claim_adaptive_companies_for_scrape(
            self.conn,
            limit=2,
            platforms={"greenhouse"},
            lease_owner="worker-b",
            lease_seconds=300,
        )

        self.assertEqual([c["slug"] for c in first_claim], ["p0", "p2"])
        self.assertEqual(second_claim, [])

    def test_platform_budgets_cap_slow_platforms(self):
        old = os.environ.get("JOBCLAW_PLATFORM_BUDGET_SECONDS_WORKDAY")
        os.environ["JOBCLAW_PLATFORM_BUDGET_SECONDS_WORKDAY"] = "45"
        try:
            registry = [{"ats": "workday", "slug": f"target-{i}", "company": f"Target {i}"} for i in range(5)]
            selected, dropped, metrics = apply_platform_budgets(registry)
        finally:
            if old is None:
                os.environ.pop("JOBCLAW_PLATFORM_BUDGET_SECONDS_WORKDAY", None)
            else:
                os.environ["JOBCLAW_PLATFORM_BUDGET_SECONDS_WORKDAY"] = old

        self.assertEqual(len(selected), 1)
        self.assertEqual(len(dropped), 4)
        self.assertEqual(metrics["workday"]["cap"], 1)


if __name__ == "__main__":
    unittest.main()
