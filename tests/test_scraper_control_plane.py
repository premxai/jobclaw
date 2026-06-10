import os
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

import scripts.database.db_utils as db_utils
from api.board_snapshot import build_snapshot_from_rows
from scripts.database.db_utils import _ensure_sqlite_schema, claim_adaptive_companies_for_scrape
from scripts.database.db_utils import get_unposted_jobs, insert_job, mark_jobs_posted
from scripts.database.db_utils import run_database_maintenance
from scripts.ops.workday_sweep_guard import evaluate_workday_guard
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

    def test_fingerprint_survives_old_inactive_accepted_job_cleanup(self):
        old_env = {
            "JOBCLAW_RETENTION_INACTIVE_ACCEPTED_DAYS": os.environ.get("JOBCLAW_RETENTION_INACTIVE_ACCEPTED_DAYS"),
            "JOBCLAW_RETENTION_FINGERPRINT_DAYS": os.environ.get("JOBCLAW_RETENTION_FINGERPRINT_DAYS"),
        }
        os.environ["JOBCLAW_RETENTION_INACTIVE_ACCEPTED_DAYS"] = "30"
        os.environ["JOBCLAW_RETENTION_FINGERPRINT_DAYS"] = "180"
        old_seen = (self.now - timedelta(days=45)).isoformat()
        try:
            insert_job(
                self.conn,
                {
                    "job_id": "posted",
                    "title": "Software Engineer",
                    "company": "Keep Fingerprint",
                    "location": "Remote - USA",
                    "url": "https://boards.greenhouse.io/keep/jobs/posted",
                    "source_ats": "greenhouse",
                    "description": "Useful role",
                },
            )
            internal_hash = "greenhouse::keep fingerprint::posted"
            mark_jobs_posted(self.conn, [internal_hash])
            self.conn.execute(
                """
                UPDATE jobs
                SET is_active = 0, first_seen = ?, last_seen_at = ?, quality_state = 'accepted'
                WHERE internal_hash = ?
                """,
                (old_seen, old_seen, internal_hash),
            )
            self.conn.execute(
                "UPDATE job_fingerprints SET last_seen = ? WHERE internal_hash = ?",
                (old_seen, internal_hash),
            )
            self.conn.commit()

            summary = run_database_maintenance(self.conn)
        finally:
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertGreaterEqual(summary["inactive_accepted_deleted"], 1)
        job_count = self.conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE internal_hash = ?",
            (internal_hash,),
        ).fetchone()[0]
        fingerprint_count = self.conn.execute(
            "SELECT COUNT(*) FROM job_fingerprints WHERE internal_hash = ?",
            (internal_hash,),
        ).fetchone()[0]
        self.assertEqual(job_count, 0)
        self.assertEqual(fingerprint_count, 1)

    def test_discord_unposted_jobs_select_newest_inside_window(self):
        old_env = {
            "JOBCLAW_DISCORD_LOOKBACK_HOURS": os.environ.get("JOBCLAW_DISCORD_LOOKBACK_HOURS"),
            "JOBCLAW_DISCORD_CANDIDATE_LIMIT": os.environ.get("JOBCLAW_DISCORD_CANDIDATE_LIMIT"),
        }
        os.environ["JOBCLAW_DISCORD_LOOKBACK_HOURS"] = "24"
        os.environ["JOBCLAW_DISCORD_CANDIDATE_LIMIT"] = "200"
        try:
            for job_id, hours_old in [("old", 25), ("middle", 2), ("new", 1)]:
                insert_job(
                    self.conn,
                    {
                        "job_id": job_id,
                        "title": f"Software Engineer {job_id}",
                        "company": "FreshCo",
                        "location": "Remote - USA",
                        "url": f"https://boards.greenhouse.io/freshco/jobs/{job_id}",
                        "source_ats": "greenhouse",
                        "description": "Build software.",
                    },
                )
                seen = (self.now - timedelta(hours=hours_old)).isoformat()
                self.conn.execute(
                    """
                    UPDATE jobs
                    SET first_seen = ?, date_posted = '', last_seen_at = ?, quality_state = 'accepted'
                    WHERE job_id = ?
                    """,
                    (seen, seen, job_id),
                )
            self.conn.commit()

            jobs = get_unposted_jobs(self.conn)
        finally:
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertEqual([job["job_id"] for job in jobs], ["new", "middle"])

    def test_board_snapshot_filters_us_jobs_and_counts_categories(self):
        snapshot = build_snapshot_from_rows(
            [
                {
                    "internal_hash": "greenhouse::acme::1",
                    "job_id": "1",
                    "title": "Machine Learning Engineer",
                    "company": "Acme",
                    "location": "San Francisco, CA",
                    "url": "https://boards.greenhouse.io/acme/jobs/1",
                    "source_ats": "greenhouse",
                    "first_seen": self.now.isoformat(),
                    "keywords_matched": '["AI/ML"]',
                },
                {
                    "internal_hash": "lever::beta::2",
                    "job_id": "2",
                    "title": "Senior Software Engineer",
                    "company": "Beta",
                    "location": "Remote - USA",
                    "url": "https://jobs.lever.co/beta/2",
                    "source_ats": "lever",
                    "first_seen": self.now.isoformat(),
                    "keywords_matched": '["SWE"]',
                },
                {
                    "internal_hash": "lever::foreign::3",
                    "job_id": "3",
                    "title": "Data Scientist",
                    "company": "Foreign",
                    "location": "London, United Kingdom",
                    "url": "https://jobs.lever.co/foreign/3",
                    "source_ats": "lever",
                    "first_seen": self.now.isoformat(),
                    "keywords_matched": '["Data Science"]',
                },
                {
                    "internal_hash": "smartrecruiters::bad::4",
                    "job_id": "4",
                    "title": "IT Infrastructure Engineer",
                    "company": "Eurofins is looking for a IT Software Engineer in Bengaluru, Karnataka, India",
                    "location": "Cork, CO, ie",
                    "url": "https://jobs.smartrecruiters.com/eurofins/4",
                    "source_ats": "smartrecruiters",
                    "first_seen": self.now.isoformat(),
                    "keywords_matched": '["SWE"]',
                },
            ],
            freshness_hours=48,
            max_jobs=10,
        )

        self.assertEqual(snapshot["total"], 2)
        self.assertEqual(snapshot["counts"]["All Roles"], 2)
        self.assertEqual(snapshot["counts"]["AI/ML"], 1)
        self.assertEqual(snapshot["counts"]["SWE"], 1)
        self.assertNotIn("description", snapshot["jobs"][0])

    def test_workday_guard_blocks_large_backlog_and_allows_force(self):
        thresholds = {
            "max_total_jobs": 50000,
            "max_accepted_unposted": 1000,
            "max_recent_bad_runs": 2,
        }
        should_run, reasons = evaluate_workday_guard(
            {
                "total_jobs": 10000,
                "accepted_unposted": 1200,
                "active_workday_leases": 0,
                "recent_workday_statuses": ["success"],
            },
            thresholds,
        )
        forced, forced_reasons = evaluate_workday_guard(
            {
                "total_jobs": 999999,
                "accepted_unposted": 999999,
                "active_workday_leases": 9,
                "recent_workday_statuses": ["failed", "degraded"],
            },
            thresholds,
            force=True,
        )

        self.assertFalse(should_run)
        self.assertIn("accepted_unposted_backlog_high", reasons)
        self.assertTrue(forced)
        self.assertEqual(forced_reasons, ["forced"])


if __name__ == "__main__":
    unittest.main()
