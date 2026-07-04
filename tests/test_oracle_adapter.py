"""Oracle Recruiting Cloud adapter — URL building, parsing, and pagination."""

import asyncio
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ingestion import ats_adapters
from scripts.ingestion.ats_adapters import ADAPTERS, OracleAdapter


class _FakeResp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload
        self.headers = {}

    def json(self):
        return self._payload


class OracleUrlTests(unittest.TestCase):
    def test_registered(self):
        self.assertIs(ADAPTERS["oracle"], OracleAdapter)

    def test_finder_uses_raw_subdelims_and_site(self):
        url = OracleAdapter._build_url("eeho.fa.us2.oraclecloud.com", "CX_2", 25, 50)
        self.assertIn("recruitingCEJobRequisitions", url)
        self.assertIn("findReqs;siteNumber=CX_2,limit=25,offset=50", url)
        self.assertIn("sortBy=POSTING_DATES_DESC", url)

    def test_parse_reqs_builds_job_and_detail_url(self):
        reqs = [
            {
                "Id": "JR100200",
                "Title": "Software Engineer II",
                "PostedDate": "2026-06-01",
                "PrimaryLocation": "Austin, TX",
                "secondaryLocations": [{"Name": "Remote, US"}],
            },
            {"Id": "", "Title": "Missing Id — skipped"},  # dropped
        ]
        jobs = OracleAdapter._parse_reqs(reqs, "Acme", "acme.fa.us2.oraclecloud.com", "CX_1")
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job.source_ats, "oracle")
        self.assertEqual(job.title, "Software Engineer II")
        self.assertEqual(job.location, "Austin, TX, Remote, US")
        self.assertIn("/sites/CX_1/job/JR100200", job.url)


class OraclePaginationTests(unittest.TestCase):
    def test_paginates_until_total_drained(self):
        pages = [
            {
                "items": [
                    {
                        "TotalJobsCount": 30,
                        "requisitionList": [{"Id": f"A{i}", "Title": "Data Engineer"} for i in range(25)],
                    }
                ]
            },
            {
                "items": [
                    {
                        "TotalJobsCount": 30,
                        "requisitionList": [{"Id": f"B{i}", "Title": "Data Engineer"} for i in range(5)],
                    }
                ]
            },
        ]
        calls = {"n": 0}

        async def fake_fetch(session, method, url, **kwargs):
            resp = _FakeResp(pages[calls["n"]])
            calls["n"] += 1
            return resp

        orig = ats_adapters.fetch_with_retry
        ats_adapters.fetch_with_retry = fake_fetch
        try:
            jobs = asyncio.run(OracleAdapter.fetch(None, "acme.fa.us2.oraclecloud.com:CX_1", "Acme"))
        finally:
            ats_adapters.fetch_with_retry = orig

        self.assertEqual(calls["n"], 2)  # stopped once offset reached total
        self.assertEqual(len(jobs), 30)

    def test_default_site_when_omitted(self):
        async def fake_fetch(session, method, url, **kwargs):
            self.assertIn("siteNumber=CX_1", url)
            return _FakeResp({"items": [{"TotalJobsCount": 0, "requisitionList": []}]})

        orig = ats_adapters.fetch_with_retry
        ats_adapters.fetch_with_retry = fake_fetch
        try:
            asyncio.run(OracleAdapter.fetch(None, "acme.fa.us2.oraclecloud.com", "Acme"))
        finally:
            ats_adapters.fetch_with_retry = orig


if __name__ == "__main__":
    unittest.main()
