"""CircuitBreaker: consecutive trip + sliding-window error-rate trip."""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ingestion.scrape_ats import CircuitBreaker


def _fresh_breaker(threshold=1000, min_samples=5, max_rate=0.30):
    # Nonexistent state path -> _load/save are safe no-ops; high threshold isolates
    # the error-rate path from the consecutive path unless a test wants both.
    tmp = Path(tempfile.mkdtemp()) / "cb.json"
    cb = CircuitBreaker(threshold=threshold, state_path=tmp)
    cb.MIN_SAMPLES = min_samples
    cb.MAX_ERROR_RATE = max_rate
    return cb


class ConsecutiveTripTests(unittest.TestCase):
    def test_consecutive_threshold_still_trips(self):
        cb = _fresh_breaker(threshold=3)
        for _ in range(3):
            cb.record_failure("workday")
        self.assertTrue(cb.should_skip("workday"))


class ErrorRateTripTests(unittest.TestCase):
    def test_interleaved_failures_trip_on_rate(self):
        cb = _fresh_breaker(threshold=1000, min_samples=10, max_rate=0.30)
        # 7 ok then 3 fail -> 10 samples, rate 0.30, consecutive only 3 (< 1000)
        for _ in range(7):
            cb.record_success("workday")
        for _ in range(3):
            cb.record_failure("workday")
        self.assertTrue(cb.should_skip("workday"))

    def test_below_min_samples_does_not_trip(self):
        cb = _fresh_breaker(threshold=1000, min_samples=20, max_rate=0.30)
        for _ in range(4):  # 100% error but only 4 samples
            cb.record_failure("workday")
        self.assertFalse(cb.should_skip("workday"))

    def test_lone_success_does_not_clear_window_trip(self):
        cb = _fresh_breaker(threshold=1000, min_samples=5, max_rate=0.30)
        for _ in range(5):
            cb.record_failure("workday")  # rate 1.0 -> tripped
        self.assertIn("workday", cb._skip_remaining)
        cb.record_success("workday")  # 5 fail / 6 = 0.83 still > 0.30
        self.assertIn("workday", cb._skip_remaining)

    def test_recovery_closes_circuit(self):
        cb = _fresh_breaker(threshold=1000, min_samples=5, max_rate=0.30)
        for _ in range(5):
            cb.record_failure("workday")
        for _ in range(30):  # flood with successes -> rate drops below 0.30
            cb.record_success("workday")
        self.assertNotIn("workday", cb._skip_remaining)

    def test_healthy_platform_never_trips(self):
        cb = _fresh_breaker(threshold=1000, min_samples=5, max_rate=0.30)
        for _ in range(40):
            cb.record_success("greenhouse")
        self.assertFalse(cb.should_skip("greenhouse"))


if __name__ == "__main__":
    unittest.main()
