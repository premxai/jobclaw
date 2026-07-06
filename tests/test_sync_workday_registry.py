"""sync_workday_registry.py: precisely targets malformed Workday rows for deletion."""

import sqlite3
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.database.db_utils import _ensure_sqlite_schema
from scripts.ops.sync_workday_registry import delete_malformed_workday_rows


class DeleteMalformedWorkdayRowsTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _ensure_sqlite_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def _insert(self, slug, ats="workday"):
        self.conn.execute(
            "INSERT INTO companies (slug, name, ats_type, tier, priority_score) VALUES (?, ?, ?, 'P2', 0)",
            (slug, slug, ats),
        )
        self.conn.commit()

    def test_deletes_only_slash_containing_workday_rows(self):
        self._insert("acme:1:careers/job/full-posting-path_r1")
        self._insert("acme:1:careers/job/full-posting-path_r2")
        self._insert("microsoft:5:careers")  # clean, must survive

        deleted = delete_malformed_workday_rows(self.conn)
        self.assertEqual(deleted, 2)

        remaining = self.conn.execute("SELECT slug FROM companies").fetchall()
        self.assertEqual([r["slug"] for r in remaining], ["microsoft:5:careers"])

    def test_never_touches_other_platforms(self):
        # Greenhouse/Lever slugs are plain names but could coincidentally never
        # contain '/', so this mostly documents intent: the WHERE clause is
        # scoped to ats_type='workday' regardless of slug shape.
        self._insert("acme", ats="greenhouse")
        deleted = delete_malformed_workday_rows(self.conn)
        self.assertEqual(deleted, 0)
        remaining = self.conn.execute("SELECT slug FROM companies").fetchall()
        self.assertEqual(len(remaining), 1)

    def test_no_malformed_rows_is_a_safe_noop(self):
        self._insert("microsoft:5:careers")
        self._insert("nvidia:1:External")
        deleted = delete_malformed_workday_rows(self.conn)
        self.assertEqual(deleted, 0)
        self.assertEqual(len(self.conn.execute("SELECT slug FROM companies").fetchall()), 2)

    def test_idempotent_second_run_deletes_nothing(self):
        self._insert("acme:1:careers/job/x_r1")
        first = delete_malformed_workday_rows(self.conn)
        second = delete_malformed_workday_rows(self.conn)
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)


if __name__ == "__main__":
    unittest.main()
