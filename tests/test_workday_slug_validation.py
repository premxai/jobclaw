"""Workday slug validation — rejects job-URL paths misfiled as the site name.

Regression coverage for a bug discovered via a real validation run: pre-split
slugs like "tenant:1:some_site/job/full-posting-path" passed the bare shape
check (3 colon parts, numeric shard) even though the "site" segment was really
a job-detail URL fragment. Every request against it 404s, and because each
distinct job path is a distinct slug string, one real tenant silently
multiplied into dozens of duplicate registry/DB rows (found: 22,049 Workday
rows collapsing to 2,016 real tenants, 93.6% malformed this way).
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.target_diagnostics import normalize_registry_target


class WorkdaySlugValidationTests(unittest.TestCase):
    def test_plain_site_name_accepted(self):
        norm, err = normalize_registry_target("Activision", "workday", "activision:1:external")
        self.assertIsNone(err)
        self.assertEqual(norm["slug"], "activision:1:external")

    def test_job_url_path_as_site_rejected(self):
        slug = (
            "activision:1:blizzard_external_careers/job/irvine---blizzard---blizzard-way/ai-localization-intern_r025877"
        )
        _, err = normalize_registry_target("Activision", "workday", slug)
        self.assertEqual(err, "malformed_workday_slug")

    def test_query_string_in_site_rejected(self):
        _, err = normalize_registry_target("Acme", "workday", "acme:1:careers?utm_source=x")
        self.assertEqual(err, "malformed_workday_slug")

    def test_fragment_in_site_rejected(self):
        _, err = normalize_registry_target("Acme", "workday", "acme:1:careers#top")
        self.assertEqual(err, "malformed_workday_slug")

    def test_full_workday_url_still_normalizes(self):
        norm, err = normalize_registry_target(
            "Microsoft", "workday", "https://microsoft.wd5.myworkdayjobs.com/en-US/careers"
        )
        self.assertIsNone(err)
        self.assertEqual(norm["slug"], "microsoft:5:careers")

    def test_multi_site_tenant_each_accepted_distinctly(self):
        # Activision Blizzard King legitimately runs multiple career sites —
        # the fix must not reject distinct real sites for the same tenant.
        for site in ("external", "blizzard_external_careers", "king_external_careers"):
            norm, err = normalize_registry_target("Activision", "workday", f"activision:1:{site}")
            self.assertIsNone(err)
            self.assertEqual(norm["slug"], f"activision:1:{site}")


if __name__ == "__main__":
    unittest.main()
