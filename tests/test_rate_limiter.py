"""Two-layer adaptive rate limiter: per-tenant buckets + platform ceilings."""

import sys
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.http_client import (
    PLATFORM_CEILING_RPS,
    RateLimiter,
    _HostBucket,
    _platform_group,
)


class PlatformGroupTests(unittest.TestCase):
    def test_maps_known_platforms(self):
        self.assertEqual(_platform_group("acme.wd5.myworkdayjobs.com"), "workday")
        self.assertEqual(_platform_group("acme.fa.us2.oraclecloud.com"), "oracle")

    def test_unknown_host_has_no_group(self):
        self.assertIsNone(_platform_group("boards-api.greenhouse.io"))
        self.assertIsNone(_platform_group("api.lever.co"))


class TwoLayerBucketTests(unittest.TestCase):
    def setUp(self):
        RateLimiter._shared_buckets.clear()
        self.rl = RateLimiter()

    def test_tenants_get_separate_host_buckets(self):
        b1 = self.rl._get_bucket("https://acme.wd5.myworkdayjobs.com/x")
        b2 = self.rl._get_bucket("https://globex.wd1.myworkdayjobs.com/y")
        self.assertIsNot(b1, b2)

    def test_tenants_share_one_platform_ceiling_bucket(self):
        p1 = self.rl._get_platform_bucket("https://acme.wd5.myworkdayjobs.com/x")
        p2 = self.rl._get_platform_bucket("https://globex.wd1.myworkdayjobs.com/y")
        self.assertIs(p1, p2)
        self.assertIsNotNone(p1)
        self.assertAlmostEqual(p1.rps, PLATFORM_CEILING_RPS["workday"])

    def test_non_ceiling_platform_has_no_platform_bucket(self):
        self.assertIsNone(self.rl._get_platform_bucket("https://boards-api.greenhouse.io/z"))

    def test_record_429_backs_off_both_layers(self):
        url = "https://acme.wd5.myworkdayjobs.com/x"
        host = self.rl._get_bucket(url)
        platform = self.rl._get_platform_bucket(url)
        host_rps, platform_rps = host.rps, platform.rps
        self.rl.record_429(url)
        self.assertLess(host.rps, host_rps)
        self.assertLess(platform.rps, platform_rps)


class RetryAfterTests(unittest.TestCase):
    def test_retry_after_sets_cooldown_floor(self):
        bucket = _HostBucket(rps=1.0)
        bucket.record_429(retry_after=90)
        self.assertGreaterEqual(bucket._cooldown_until - time.monotonic(), 80)

    def test_retry_after_capped(self):
        bucket = _HostBucket(rps=1.0)
        bucket.record_429(retry_after=100000)
        # capped at 900s
        self.assertLessEqual(bucket._cooldown_until - time.monotonic(), 901)

    def test_no_retry_after_uses_exponential(self):
        bucket = _HostBucket(rps=1.0)
        bucket.record_429()
        self.assertGreater(bucket._cooldown_until - time.monotonic(), 0)


if __name__ == "__main__":
    unittest.main()
