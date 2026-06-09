"""Tests for the coverage/scheduling and rate-limit hardening.

These run against an in-memory SQLite database (the default backend when
DATABASE_URL is unset), so they exercise the real SQL paths without a server.
"""

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.database import db_utils
from scripts.utils.retry_queue import REVIEW_DELAY, RetryQueue


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db_utils._ensure_sqlite_schema(conn)
    return conn


def _insert_company(conn, *, slug, ats="workday", tier="P2", next_due_at=None, last_success_at=None, scrape_score=0.0):
    conn.execute(
        """
        INSERT INTO companies (slug, name, ats_type, tier, next_due_at, next_scrape_at,
                               last_success_at, scrape_score, priority_score, is_dead)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (slug, slug, ats, tier, next_due_at, next_due_at, last_success_at, scrape_score, scrape_score),
    )
    conn.commit()


class AgingFairnessTests(unittest.TestCase):
    """A severely-overdue low-score target should be claimed ahead of a fresher,
    higher-score one — otherwise the long tail starves."""

    def test_aged_target_is_claimed_before_high_score_fresh_target(self):
        conn = _make_db()
        now = datetime.now(timezone.utc)
        # Aged 60 days, zero score.
        _insert_company(conn, slug="aged-co", next_due_at=_iso(now - timedelta(days=60)), scrape_score=0.0)
        # Due an hour ago, very high score (would win without the aging term).
        _insert_company(conn, slug="fresh-co", next_due_at=_iso(now - timedelta(hours=1)), scrape_score=999.0)
        # Not due yet — must be excluded entirely.
        _insert_company(conn, slug="future-co", next_due_at=_iso(now + timedelta(days=1)), scrape_score=500.0)

        claimed = db_utils.claim_adaptive_companies_for_scrape(
            conn, limit=1, platforms={"workday"}, lease_owner="test", lease_seconds=300
        )
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0]["slug"], "aged-co")

    def test_not_due_targets_excluded(self):
        conn = _make_db()
        now = datetime.now(timezone.utc)
        _insert_company(conn, slug="future-only", next_due_at=_iso(now + timedelta(days=2)))
        claimed = db_utils.claim_adaptive_companies_for_scrape(
            conn, limit=10, platforms={"workday"}, lease_owner="test", lease_seconds=300
        )
        self.assertEqual(claimed, [])


class ShardRotationTests(unittest.TestCase):
    def test_cursor_advances_and_wraps(self):
        conn = _make_db()
        seq = [db_utils.get_next_shard_from_db(conn, "medium_ats_workday", 4) for _ in range(6)]
        self.assertEqual(seq, [0, 1, 2, 3, 0, 1])

    def test_single_shard_is_zero(self):
        conn = _make_db()
        self.assertEqual(db_utils.get_next_shard_from_db(conn, "x", 1), 0)

    def test_distinct_keys_rotate_independently(self):
        conn = _make_db()
        a = [db_utils.get_next_shard_from_db(conn, "fast", 4) for _ in range(3)]
        b = [db_utils.get_next_shard_from_db(conn, "medium", 4) for _ in range(2)]
        self.assertEqual(a, [0, 1, 2])
        self.assertEqual(b, [0, 1])


class CoverageAgeTests(unittest.TestCase):
    def test_counts_aged_and_never_scraped(self):
        conn = _make_db()
        now = datetime.now(timezone.utc)
        _insert_company(conn, slug="never")  # last_success_at NULL
        _insert_company(conn, slug="fresh", last_success_at=_iso(now - timedelta(days=1)))
        _insert_company(conn, slug="stale", last_success_at=_iso(now - timedelta(days=60)))

        rows = {r["platform"]: r for r in db_utils.get_coverage_age_by_platform(conn)}
        wd = rows["workday"]
        self.assertEqual(int(wd["total"]), 3)
        self.assertEqual(int(wd["never_scraped"]), 1)
        self.assertEqual(int(wd["aged"]), 1)  # only the 60-day-old one is past the 14d SLO


class RetryAfterTests(unittest.TestCase):
    def _queue(self) -> RetryQueue:
        tmp = Path(tempfile.mkdtemp()) / "retry_queue.json"
        return RetryQueue(path=tmp)

    def test_retry_after_overrides_review_bucket(self):
        q = self._queue()
        q.add_failure("Acme", "workday", "acme", "429", failure_type="rate_limited", status_code=429, retry_after=120)
        entry = q._queue[-1]
        next_retry = datetime.fromisoformat(entry["next_retry"].replace("Z", "+00:00"))
        delta = (next_retry - datetime.now(timezone.utc)).total_seconds()
        # ~120s, definitely not the 7-day review bucket.
        self.assertLess(delta, 600)
        self.assertLess(delta, REVIEW_DELAY)

    def test_without_retry_after_429_uses_review_bucket(self):
        q = self._queue()
        q.add_failure("Acme", "workday", "acme", "429", failure_type="rate_limited", status_code=429)
        entry = q._queue[-1]
        next_retry = datetime.fromisoformat(entry["next_retry"].replace("Z", "+00:00"))
        delta = (next_retry - datetime.now(timezone.utc)).total_seconds()
        self.assertGreater(delta, REVIEW_DELAY - 3600)  # ~7 days


class TierIntervalTests(unittest.TestCase):
    def test_relevant_jobs_accelerate_interval(self):
        company = {"tier": "P2"}
        # With relevant jobs found, P2's 24h interval is pulled in to <= 1h.
        nxt = db_utils.compute_next_scrape_at(company, job_count=5, relevant_count=2)
        nxt_dt = datetime.fromisoformat(nxt)
        delta = (nxt_dt - datetime.now(timezone.utc)).total_seconds()
        self.assertLessEqual(delta, 3600 + 5)

    def test_failure_backs_off(self):
        company = {"tier": "P1", "consecutive_failures": 3}
        nxt = db_utils.compute_next_scrape_at(company, failed=True)
        nxt_dt = datetime.fromisoformat(nxt)
        delta = (nxt_dt - datetime.now(timezone.utc)).total_seconds()
        # P1 base 1h, multiplied by failure factor → well over an hour.
        self.assertGreater(delta, 3600)


if __name__ == "__main__":
    # Ensure SQLite backend regardless of ambient env.
    os.environ.pop("DATABASE_URL", None)
    unittest.main()
