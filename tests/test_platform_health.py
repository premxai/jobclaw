"""Per-platform health aggregation — the 'is it actually working?' report."""

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ops.platform_health import aggregate_platform_health


class AggregatePlatformHealthTests(unittest.TestCase):
    def _run(self, platforms, breakdown=None):
        return {"platforms": platforms, "failure_breakdown": breakdown or {}}

    def test_sums_across_runs_and_computes_rates(self):
        runs = [
            self._run(
                {"workday": {"attempted": 100, "succeeded": 80, "failed": 20, "jobs_fetched": 500}},
                {"workday": {"rate_limited": 12, "bad_target": 8}},
            ),
            self._run(
                {"workday": {"attempted": 100, "succeeded": 90, "failed": 10, "jobs_fetched": 600}},
                {"workday": {"timeout": 4, "bad_target": 6}},
            ),
        ]
        health = aggregate_platform_health(runs)
        wd = health["workday"]
        self.assertEqual(wd["attempted"], 200)
        self.assertEqual(wd["succeeded"], 170)
        self.assertEqual(wd["jobs_fetched"], 1100)
        self.assertAlmostEqual(wd["success_rate"], 0.85)
        self.assertAlmostEqual(wd["error_rate"], 0.15)
        # infra errors = rate_limited(12)+timeout(4) = 16 / 200; bad_target excluded
        self.assertAlmostEqual(wd["infra_error_rate"], 0.08)
        self.assertEqual(wd["categories"]["bad_target"], 14)

    def test_accepts_json_strings(self):
        runs = [json.dumps(self._run({"lever": {"attempted": 10, "succeeded": 10, "failed": 0}}))]
        health = aggregate_platform_health(runs)
        self.assertEqual(health["lever"]["success_rate"], 1.0)
        self.assertEqual(health["lever"]["infra_error_rate"], 0.0)

    def test_zero_attempts_yields_none_rates(self):
        health = aggregate_platform_health([self._run({"ashby": {"attempted": 0, "succeeded": 0, "failed": 0}})])
        self.assertIsNone(health["ashby"]["success_rate"])
        self.assertIsNone(health["ashby"]["infra_error_rate"])

    def test_ignores_malformed_and_empty(self):
        health = aggregate_platform_health(["", None, "not json", {}])
        self.assertEqual(health, {})


if __name__ == "__main__":
    unittest.main()
