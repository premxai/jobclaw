import os
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

import scripts.database.db_utils as db_utils
from scripts.database.db_utils import _ensure_sqlite_schema, claim_adaptive_companies_for_scrape, insert_job
from scripts.database.db_utils import run_database_maintenance
from scripts.utils.platform_budgets import apply_platform_budgets, platform_target_cap


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

    def test_platform_target_cap_uses_budget_workers_and_estimate(self):
        old = os.environ.get("JOBCLAW_PLATFORM_BUDGET_SECONDS_WORKDAY")
        os.environ["JOBCLAW_PLATFORM_BUDGET_SECONDS_WORKDAY"] = "90"
        try:
            self.assertEqual(platform_target_cap("workday"), 2)
        finally:
            if old is None:
                os.environ.pop("JOBCLAW_PLATFORM_BUDGET_SECONDS_WORKDAY", None)
            else:
                os.environ["JOBCLAW_PLATFORM_BUDGET_SECONDS_WORKDAY"] = old

    def test_insert_job_caps_description_storage(self):
        old = os.environ.get("JOBCLAW_DESCRIPTION_MAX_CHARS")
        os.environ["JOBCLAW_DESCRIPTION_MAX_CHARS"] = "24"
        try:
            inserted = insert_job(
                self.conn,
                {
                    "job_id": "abc",
                    "title": "Software Engineer",
                    "company": "Acme",
                    "location": "Remote - USA",
                    "url": "https://boards.greenhouse.io/acme/jobs/abc",
                    "source_ats": "greenhouse",
                    "description": "x" * 100,
                },
            )
        finally:
            if old is None:
                os.environ.pop("JOBCLAW_DESCRIPTION_MAX_CHARS", None)
            else:
                os.environ["JOBCLAW_DESCRIPTION_MAX_CHARS"] = old

        self.assertTrue(inserted)
        row = self.conn.execute("SELECT description FROM jobs WHERE company = 'Acme'").fetchone()
        self.assertEqual(len(row["description"]), 24)

    def test_database_maintenance_prunes_low_value_rows_only(self):
        old_env = {
            key: os.environ.get(key)
            for key in [
                "JOBCLAW_RETENTION_REJECTED_DAYS",
                "JOBCLAW_RETENTION_NEEDS_REVIEW_DAYS",
                "JOBCLAW_RETENTION_ARCHIVED_DAYS",
                "JOBCLAW_RETENTION_INACTIVE_DAYS",
                "JOBCLAW_DESCRIPTION_CLEAR_AFTER_DAYS",
            ]
        }
        for key in old_env:
            os.environ[key] = "3"

        old_seen = (self.now - timedelta(days=5)).isoformat()
        self.conn.executemany(
            """
            INSERT INTO jobs (
                internal_hash, job_id, title, company, location, url, date_posted,
                source_ats, first_seen, status, keywords_matched, description,
                is_active, last_seen_at, quality_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "greenhouse::bad::1",
                    "1",
                    "Software Engineer Salary in Austin",
                    "Bad",
                    "Austin, TX",
                    "https://example.com/salary",
                    old_seen,
                    "greenhouse",
                    old_seen,
                    "unposted",
                    "[]",
                    "junk",
                    1,
                    old_seen,
                    "rejected",
                ),
                (
                    "greenhouse::good::1",
                    "1",
                    "Software Engineer",
                    "Good",
                    "Austin, TX",
                    "https://boards.greenhouse.io/good/jobs/1",
                    old_seen,
                    "greenhouse",
                    old_seen,
                    "posted",
                    "[]",
                    "valuable",
                    1,
                    old_seen,
                    "accepted",
                ),
            ],
        )
        self.conn.commit()

        try:
            summary = run_database_maintenance(self.conn)
        finally:
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertGreaterEqual(summary["rejected_deleted"], 1)
        rows = self.conn.execute("SELECT company, description FROM jobs ORDER BY company").fetchall()
        self.assertEqual([row["company"] for row in rows], ["Good"])
        self.assertEqual(rows[0]["description"], "")


if __name__ == "__main__":
    unittest.main()
