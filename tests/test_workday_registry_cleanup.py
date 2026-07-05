"""Workday registry cleanup: recover real site names, dedupe, drop garbage."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ops.cleanup_workday_registry_slugs import clean_companies, recover_workday_slug


class RecoverSlugTests(unittest.TestCase):
    def test_recovers_site_from_job_url_path(self):
        slug = (
            "activision:1:blizzard_external_careers/job/irvine---blizzard---blizzard-way/ai-localization-intern_r025877"
        )
        self.assertEqual(recover_workday_slug(slug), "activision:1:blizzard_external_careers")

    def test_plain_slug_passes_through(self):
        self.assertEqual(recover_workday_slug("microsoft:5:Microsoft"), "microsoft:5:Microsoft")

    def test_strips_query_and_fragment(self):
        self.assertEqual(recover_workday_slug("acme:1:careers?utm=x"), "acme:1:careers")
        self.assertEqual(recover_workday_slug("acme:1:careers#top"), "acme:1:careers")

    def test_unsalvageable_shape_returns_none(self):
        self.assertIsNone(recover_workday_slug("wd1"))
        self.assertIsNone(recover_workday_slug("tenant:notanumber:site"))
        self.assertIsNone(recover_workday_slug("tenant:1:"))
        self.assertIsNone(recover_workday_slug(":1:site"))


class CleanCompaniesTests(unittest.TestCase):
    def test_dedupes_duplicate_job_paths_to_one_row(self):
        companies = [
            {"company": "Bose", "ats": "workday", "slug": "bose:503:bose_careers/job/a/role-1_r1"},
            {"company": "Bose", "ats": "workday", "slug": "bose:503:bose_careers/job/b/role-2_r2"},
            {"company": "Bose Corp", "ats": "workday", "slug": "bose:503:bose_careers/job/c/role-3_r3"},
        ]
        cleaned, stats = clean_companies(companies)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0]["slug"], "bose:503:bose_careers")
        self.assertEqual(stats["workday_before"], 3)
        self.assertEqual(stats["workday_after"], 1)

    def test_preserves_distinct_legitimate_sites(self):
        companies = [
            {"company": "Activision", "ats": "workday", "slug": "activision:1:external/job/x/role_r1"},
            {"company": "Blizzard", "ats": "workday", "slug": "activision:1:blizzard_external_careers/job/y/role_r2"},
            {"company": "King", "ats": "workday", "slug": "activision:1:king_external_careers/job/z/role_r3"},
        ]
        cleaned, stats = clean_companies(companies)
        slugs = sorted(c["slug"] for c in cleaned)
        self.assertEqual(
            slugs,
            ["activision:1:blizzard_external_careers", "activision:1:external", "activision:1:king_external_careers"],
        )
        self.assertEqual(stats["workday_after"], 3)

    def test_prefers_longer_company_name_on_duplicate(self):
        companies = [
            {"company": "Bose", "ats": "workday", "slug": "bose:503:bose_careers/job/a/role_r1"},
            {"company": "Bose Corporation", "ats": "workday", "slug": "bose:503:bose_careers/job/b/role_r2"},
        ]
        cleaned, _ = clean_companies(companies)
        self.assertEqual(cleaned[0]["company"], "Bose Corporation")

    def test_drops_unsalvageable_garbage(self):
        companies = [{"company": "Software Engineer (E)", "ats": "workday", "slug": "wd1"}]
        cleaned, stats = clean_companies(companies)
        self.assertEqual(cleaned, [])
        self.assertEqual(stats["dropped_unsalvageable"], 1)

    def test_non_workday_entries_untouched(self):
        companies = [
            {"company": "Stripe", "ats": "greenhouse", "slug": "stripe"},
            {"company": "Bose", "ats": "workday", "slug": "bose:503:bose_careers/job/a/role_r1"},
        ]
        cleaned, stats = clean_companies(companies)
        self.assertIn({"company": "Stripe", "ats": "greenhouse", "slug": "stripe"}, cleaned)
        self.assertEqual(stats["non_workday"], 1)

    def test_empty_input(self):
        cleaned, stats = clean_companies([])
        self.assertEqual(cleaned, [])
        self.assertEqual(stats["workday_before"], 0)


if __name__ == "__main__":
    unittest.main()
