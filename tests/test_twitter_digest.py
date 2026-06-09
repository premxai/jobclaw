"""Tests for the Twitter/X digest formatter (pure functions, no API/DB)."""

import unittest

from scripts.twitter_push import TWEET_MAX_CHARS, _tweet_length, _truncate, build_digest

WEB = "https://norinote.xyz"
LINK = WEB + "/jobs"


def _job(title, company, cat, score=0.0):
    return {"title": title, "company": company, "keywords_matched": [cat], "quality_score": score}


class TweetLengthTests(unittest.TestCase):
    def test_url_counts_as_23(self):
        long_url = "https://example.com/" + "x" * 100
        self.assertEqual(_tweet_length(f"hi {long_url}", long_url), len("hi ") + 23)

    def test_truncate_adds_ellipsis(self):
        self.assertEqual(_truncate("abcdefgh", 5), "abcd…")
        self.assertEqual(_truncate("short", 10), "short")


class BuildDigestTests(unittest.TestCase):
    def test_basic_digest_default_has_no_url(self):
        jobs = (
            [_job(f"SWE {i}", f"Co{i}", "SWE", 90 - i) for i in range(7)]
            + [_job(f"ML {i}", f"AiCo{i}", "AI/ML", 80 - i) for i in range(5)]
            + [_job(f"Data {i}", f"DCo{i}", "Data", 50) for i in range(3)]
        )
        text = build_digest(jobs, WEB, window_hours=3)
        self.assertLessEqual(_tweet_length(text), TWEET_MAX_CHARS)
        self.assertIn("Fresh US tech roles from the last 3 hours", text)
        self.assertIn("15 new roles added:", text)
        self.assertIn("SWE: 7", text)
        self.assertIn("AI/ML: 5", text)
        # Default omits the URL to avoid X's $0.20 link surcharge.
        self.assertNotIn("http", text)
        self.assertIn("Full list in bio.", text)

    def test_thousands_separator(self):
        jobs = [_job(f"SWE {i}", f"Co{i}", "SWE", 1) for i in range(1000)]
        text = build_digest(jobs, WEB)
        self.assertIn("1,000 new roles added:", text)
        self.assertIn("SWE: 1,000", text)

    def test_includes_url_when_enabled(self):
        text = build_digest([_job("Staff Eng", "Stripe", "SWE", 99)], WEB, include_url=True)
        self.assertIn(LINK, text)
        self.assertLessEqual(_tweet_length(text, LINK), TWEET_MAX_CHARS)

    def test_singular_role(self):
        text = build_digest([_job("Staff Eng", "Stripe", "SWE", 99)], WEB)
        self.assertIn("1 new role added:", text)  # singular, no trailing 's'

    def test_picks_list_highest_quality_first(self):
        jobs = [_job("Senior Backend Engineer", "Stripe", "SWE", 99), _job("Junior Dev", "SmallCo", "SWE", 10)]
        text = build_digest(jobs, WEB, max_top=1)
        self.assertIn("A few fresh picks:", text)
        self.assertIn("@ Stripe", text)

    def test_stays_under_limit_with_many_long_entries(self):
        long_title = "Principal Distributed Systems Engineer " * 3
        long_co = "A Very Long Company Name Inc " * 2
        jobs = [_job(long_title, long_co, "SWE", 50) for _ in range(40)]
        self.assertLessEqual(_tweet_length(build_digest(jobs, WEB)), TWEET_MAX_CHARS)
        with_url = build_digest(jobs, WEB, include_url=True)
        self.assertLessEqual(_tweet_length(with_url, LINK), TWEET_MAX_CHARS)
        self.assertIn(LINK, with_url)

    def test_long_mode_keeps_picks_and_tagline(self):
        jobs = (
            [_job(f"SWE {i}", f"Co{i}", "SWE", 90 - i) for i in range(7)]
            + [_job(f"ML {i}", f"AiCo{i}", "AI/ML", 80 - i) for i in range(5)]
            + [_job(f"Data {i}", f"DCo{i}", "Data", 50) for i in range(3)]
        )
        text = build_digest(jobs, WEB, max_chars=4000)
        self.assertIn("A few fresh picks:", text)
        self.assertIn("Clean list, direct links, less noise.", text)

    def test_uncategorized_excluded_from_counts(self):
        jobs = [_job("X", "Y", "SWE", 1), {"title": "Z", "company": "W", "keywords_matched": [], "quality_score": 1}]
        text = build_digest(jobs, WEB)
        self.assertIn("2 new roles added:", text)  # both counted in total
        self.assertIn("SWE: 1", text)  # only categorized one in breakdown


if __name__ == "__main__":
    unittest.main()
