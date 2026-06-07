import os
import unittest

from scripts.discord_push import _passes_strict_job_quality
from scripts.database.db_utils import classify_job_quality
from scripts.utils.target_diagnostics import apply_cached_metadata, classify_failure


class FailureClassificationTests(unittest.TestCase):
    def test_classifies_core_failure_categories(self):
        cases = [
            ({"status_code": 404, "error": "not found"}, "bad_target"),
            ({"status_code": 429, "error": "too many requests"}, "rate_limited"),
            ({"status_code": 403, "error": "captcha challenge"}, "anti_bot"),
            ({"error": "request timeout after 60s"}, "timeout"),
            ({"error": "connection reset by peer"}, "connection"),
            ({"error": "JSON decode failed"}, "parse"),
            ({"error": "empty board: no jobs"}, "empty_board"),
            ({"status_code": 503, "error": "service unavailable"}, "connection"),
        ]
        for kwargs, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(classify_failure(**kwargs)["category"], expected)


class WorkdayMetadataTests(unittest.TestCase):
    def test_cached_workday_site_rewrites_slug(self):
        slug, used_cache = apply_cached_metadata(
            {
                "ats": "workday",
                "slug": "acme:12:External",
                "validated_metadata": '{"workday_site":"Careers"}',
            }
        )

        self.assertTrue(used_cache)
        self.assertEqual(slug, "acme:12:Careers")

    def test_non_workday_metadata_does_not_rewrite_slug(self):
        slug, used_cache = apply_cached_metadata(
            {
                "ats": "greenhouse",
                "slug": "acme",
                "validated_metadata": '{"workday_site":"Careers"}',
            }
        )

        self.assertFalse(used_cache)
        self.assertEqual(slug, "acme")


class DiscordStrictQualityTests(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("JOBCLAW_DISCORD_STRICT_QUALITY")
        os.environ["JOBCLAW_DISCORD_STRICT_QUALITY"] = "1"

    def tearDown(self):
        if self._old is None:
            os.environ.pop("JOBCLAW_DISCORD_STRICT_QUALITY", None)
        else:
            os.environ["JOBCLAW_DISCORD_STRICT_QUALITY"] = self._old

    def test_accepts_specific_ats_job(self):
        ok, reason = _passes_strict_job_quality(
            {
                "title": "Machine Learning Engineer",
                "company": "Acme AI",
                "url": "https://boards.greenhouse.io/acme/jobs/123",
                "source_ats": "greenhouse",
            }
        )

        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_rejects_aggregator_salary_and_search_pages(self):
        cases = [
            (
                {
                    "title": "Software Engineer Salary in New York",
                    "company": "Indeed",
                    "url": "https://www.indeed.com/career/software-engineer/salaries/New-York--NY",
                    "source_ats": "indeed",
                },
                "generic_title",
            ),
            (
                {
                    "title": "10,000+ Python Jobs Hiring Now",
                    "company": "CareerBuilder",
                    "url": "https://www.careerbuilder.com/jobs?keywords=python",
                    "source_ats": "careerbuilder",
                },
                "generic_title",
            ),
            (
                {
                    "title": "Backend Engineer",
                    "company": "Unknown",
                    "url": "https://example.com/jobs/backend-engineer",
                    "source_ats": "unknown",
                },
                "unknown_company",
            ),
        ]
        for job, expected_reason in cases:
            with self.subTest(expected_reason=expected_reason):
                ok, reason = _passes_strict_job_quality(job)
                self.assertFalse(ok)
                self.assertEqual(reason, expected_reason)


class JobQualityClassifierTests(unittest.TestCase):
    def test_accepts_direct_ats_job(self):
        state, reasons, company, title, confidence = classify_job_quality(
            {
                "title": "Founding AI Engineer",
                "company": "Acme AI",
                "url": "https://jobs.ashbyhq.com/acme/123",
                "source_ats": "ashby",
            }
        )

        self.assertEqual(state, "accepted")
        self.assertEqual(reasons, [])
        self.assertEqual(company, "Acme AI")
        self.assertEqual(title, "Founding AI Engineer")
        self.assertEqual(confidence, 1.0)

    def test_rejects_non_job_aggregator_record(self):
        state, reasons, _company, _title, confidence = classify_job_quality(
            {
                "title": "Software Engineer Salary in Austin",
                "company": "Indeed",
                "url": "https://www.indeed.com/career/software-engineer/salaries/Austin--TX",
                "source_ats": "indeed",
            }
        )

        self.assertEqual(state, "rejected")
        self.assertIn("non_direct_source", reasons)
        self.assertIn("non_job_url", reasons)
        self.assertIn("aggregator_host", reasons)
        self.assertIn("generic_title", reasons)
        self.assertLess(confidence, 0.5)


if __name__ == "__main__":
    unittest.main()
