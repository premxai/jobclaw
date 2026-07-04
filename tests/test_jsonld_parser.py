"""schema.org/JobPosting JSON-LD extraction — the universal scraper's core."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ingestion.jsonld_parser import (
    extract_jsonld_blocks,
    extract_sitemap_urls,
    find_job_postings,
    is_sitemap_content,
    normalize_job_posting,
    parse_job_postings_from_html,
)

SINGLE = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "JobPosting",
  "title": "Senior Software Engineer",
  "datePosted": "2026-06-15",
  "description": "Build things.",
  "hiringOrganization": {"@type": "Organization", "name": "Acme Corp"},
  "jobLocation": {"@type": "Place", "address": {"@type": "PostalAddress",
    "addressLocality": "Austin", "addressRegion": "TX", "addressCountry": "US"}},
  "baseSalary": {"@type": "MonetaryAmount", "currency": "USD",
    "value": {"@type": "QuantitativeValue", "minValue": 150000, "maxValue": 200000}},
  "identifier": {"@type": "PropertyValue", "value": "JR-42"},
  "url": "https://acme.example.com/jobs/JR-42"
}
</script></head><body></body></html>
"""

GRAPH = """
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"WebSite","name":"careers"},
  {"@type":"JobPosting","title":"Data Engineer","hiringOrganization":"Globex",
   "jobLocation":{"address":{"addressLocality":"Remote"}}},
  {"@type":"JobPosting","title":"ML Engineer","hiringOrganization":{"name":"Globex"},
   "jobLocationType":"TELECOMMUTE"}
]}
</script>
"""


class ExtractionTests(unittest.TestCase):
    def test_extracts_single_block(self):
        blocks = extract_jsonld_blocks(SINGLE)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(find_job_postings(blocks)[0]["title"], "Senior Software Engineer")

    def test_walks_graph_container(self):
        postings = find_job_postings(extract_jsonld_blocks(GRAPH))
        titles = sorted(p["title"] for p in postings)
        self.assertEqual(titles, ["Data Engineer", "ML Engineer"])

    def test_skips_malformed_block_but_keeps_others(self):
        html = (
            '<script type="application/ld+json">{bad json</script>'
            '<script type="application/ld+json">{"@type":"JobPosting","title":"OK Role"}</script>'
        )
        postings = find_job_postings(extract_jsonld_blocks(html))
        self.assertEqual(len(postings), 1)
        self.assertEqual(postings[0]["title"], "OK Role")

    def test_no_jsonld_returns_empty(self):
        self.assertEqual(extract_jsonld_blocks("<html>nothing</html>"), [])
        self.assertEqual(parse_job_postings_from_html("", "u"), [])


class NormalizationTests(unittest.TestCase):
    def test_full_normalization(self):
        job = parse_job_postings_from_html(SINGLE)[0]
        self.assertEqual(job["title"], "Senior Software Engineer")
        self.assertEqual(job["company"], "Acme Corp")
        self.assertEqual(job["location"], "Austin, TX, US")
        self.assertEqual(job["source_ats"], "jsonld")
        self.assertEqual(job["job_id"], "JR-42")
        self.assertEqual(job["salary_min"], 150000.0)
        self.assertEqual(job["salary_max"], 200000.0)
        self.assertEqual(job["salary_currency"], "USD")
        self.assertEqual(job["url"], "https://acme.example.com/jobs/JR-42")

    def test_type_as_list_and_string_org(self):
        node = {"@type": ["JobPosting", "Thing"], "title": "Role X", "hiringOrganization": "StringCo"}
        self.assertEqual(find_job_postings([node])[0]["title"], "Role X")
        norm = normalize_job_posting(node, "https://x.com/job")
        self.assertEqual(norm["company"], "StringCo")
        self.assertEqual(norm["url"], "https://x.com/job")

    def test_telecommute_location(self):
        norm = normalize_job_posting({"@type": "JobPosting", "title": "R", "jobLocationType": "TELECOMMUTE"}, "u")
        self.assertEqual(norm["location"], "Remote")

    def test_missing_title_dropped(self):
        self.assertIsNone(normalize_job_posting({"@type": "JobPosting"}, "u"))

    def test_source_url_fallback_for_id_and_url(self):
        norm = normalize_job_posting({"@type": "JobPosting", "title": "R"}, "https://co/job/9")
        self.assertEqual(norm["url"], "https://co/job/9")
        self.assertEqual(norm["job_id"], "https://co/job/9")


class JsonLdAdapterTests(unittest.TestCase):
    def test_adapter_fetches_and_normalizes(self):
        import asyncio

        from scripts.ingestion import ats_adapters
        from scripts.ingestion.ats_adapters import ADAPTERS, JsonLdAdapter

        self.assertIs(ADAPTERS["jsonld"], JsonLdAdapter)

        class _Resp:
            status_code = 200
            headers = {}
            text = SINGLE

        async def fake_fetch(session, method, url, **kwargs):
            return _Resp()

        orig = ats_adapters.fetch_with_retry
        ats_adapters.fetch_with_retry = fake_fetch
        try:
            jobs = asyncio.run(JsonLdAdapter.fetch(None, "https://acme.example.com/jobs/JR-42", "Registry Name"))
        finally:
            ats_adapters.fetch_with_retry = orig

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source_ats, "jsonld")
        self.assertEqual(jobs[0].company, "Acme Corp")

    def test_adapter_rejects_non_url_slug(self):
        import asyncio

        from scripts.ingestion.ats_adapters import JsonLdAdapter

        jobs = asyncio.run(JsonLdAdapter.fetch(None, "not-a-url", "Co"))
        self.assertEqual(jobs, [])

    def test_adapter_follows_sitemap_and_extracts_each_page(self):
        import asyncio

        from scripts.ingestion import ats_adapters
        from scripts.ingestion.ats_adapters import JsonLdAdapter

        sitemap_body = (
            "<urlset><url><loc>https://co.example.com/job/1</loc></url>"
            "<url><loc>https://co.example.com/job/2</loc></url></urlset>"
        )
        page_one = '<script type="application/ld+json">{"@type":"JobPosting","title":"Role One"}</script>'
        page_two = '<script type="application/ld+json">{"@type":"JobPosting","title":"Role Two"}</script>'
        bodies = {
            "https://co.example.com/sitemap.xml": sitemap_body,
            "https://co.example.com/job/1": page_one,
            "https://co.example.com/job/2": page_two,
        }

        class _Resp:
            status_code = 200
            headers = {}

            def __init__(self, text):
                self.text = text

        async def fake_fetch(session, method, url, **kwargs):
            return _Resp(bodies[url])

        orig = ats_adapters.fetch_with_retry
        ats_adapters.fetch_with_retry = fake_fetch
        try:
            jobs = asyncio.run(JsonLdAdapter.fetch(None, "https://co.example.com/sitemap.xml", "Co"))
        finally:
            ats_adapters.fetch_with_retry = orig

        titles = sorted(j.title for j in jobs)
        self.assertEqual(titles, ["Role One", "Role Two"])
        self.assertTrue(all(j.company == "Co" for j in jobs))

    def test_adapter_sitemap_cap_limits_pages_fetched(self):
        import asyncio

        from scripts.ingestion import ats_adapters
        from scripts.ingestion.ats_adapters import JsonLdAdapter

        urls = [f"https://co.example.com/job/{i}" for i in range(5)]
        sitemap_body = "<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>"
        calls: list[str] = []

        class _Resp:
            status_code = 200
            headers = {}

            def __init__(self, text):
                self.text = text

        async def fake_fetch(session, method, url, **kwargs):
            calls.append(url)
            if url == "https://co.example.com/sitemap.xml":
                return _Resp(sitemap_body)
            return _Resp('<script type="application/ld+json">{"@type":"JobPosting","title":"R"}</script>')

        orig = ats_adapters.fetch_with_retry
        orig_cap = JsonLdAdapter.SITEMAP_PAGE_CAP
        ats_adapters.fetch_with_retry = fake_fetch
        JsonLdAdapter.SITEMAP_PAGE_CAP = 2
        try:
            jobs = asyncio.run(JsonLdAdapter.fetch(None, "https://co.example.com/sitemap.xml", "Co"))
        finally:
            ats_adapters.fetch_with_retry = orig
            JsonLdAdapter.SITEMAP_PAGE_CAP = orig_cap

        # 1 sitemap fetch + 2 job-page fetches (capped), not all 5
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(jobs), 2)


SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://careers.example.com/job/1001</loc></url>
  <url><loc>https://careers.example.com/job/1002</loc></url>
</urlset>
"""

SITEMAP_INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://careers.example.com/sitemap-jobs-1.xml</loc></sitemap>
  <sitemap><loc>https://careers.example.com/sitemap-jobs-2.xml</loc></sitemap>
</sitemapindex>
"""


class SitemapParsingTests(unittest.TestCase):
    def test_detects_urlset_sitemap(self):
        self.assertTrue(is_sitemap_content(SITEMAP_XML))

    def test_detects_sitemapindex(self):
        self.assertTrue(is_sitemap_content(SITEMAP_INDEX_XML))

    def test_html_is_not_a_sitemap(self):
        self.assertFalse(is_sitemap_content(SINGLE))

    def test_empty_is_not_a_sitemap(self):
        self.assertFalse(is_sitemap_content(""))
        self.assertFalse(is_sitemap_content(None))

    def test_extracts_loc_urls(self):
        urls = extract_sitemap_urls(SITEMAP_XML)
        self.assertEqual(urls, ["https://careers.example.com/job/1001", "https://careers.example.com/job/1002"])

    def test_extracts_loc_urls_from_index(self):
        urls = extract_sitemap_urls(SITEMAP_INDEX_XML)
        self.assertEqual(len(urls), 2)
        self.assertTrue(all("sitemap-jobs" in u for u in urls))

    def test_no_locs_returns_empty(self):
        self.assertEqual(extract_sitemap_urls("<urlset></urlset>"), [])
        self.assertEqual(extract_sitemap_urls(""), [])


class JsonLdRegistryTests(unittest.TestCase):
    def test_url_slug_normalizes(self):
        from scripts.utils.target_diagnostics import normalize_registry_target

        norm, err = normalize_registry_target("Acme", "jsonld", "https://acme.example.com/careers/job/1")
        self.assertIsNone(err)
        self.assertEqual(norm["slug"], "https://acme.example.com/careers/job/1")

    def test_non_url_slug_rejected(self):
        from scripts.utils.target_diagnostics import normalize_registry_target

        _, err = normalize_registry_target("Acme", "jsonld", "acme-careers")
        self.assertEqual(err, "malformed_jsonld_url")


if __name__ == "__main__":
    unittest.main()
