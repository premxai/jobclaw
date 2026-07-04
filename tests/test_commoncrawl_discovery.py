"""Common Crawl discovery: query building, JSONL parsing, and ATS routing."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.expand_registry import (
    CC_QUERY_PATTERNS,
    cc_index_query_url,
    parse_cc_index_lines,
    parse_url_for_ats,
)


class QueryUrlTests(unittest.TestCase):
    def test_builds_index_query(self):
        url = cc_index_query_url("CC-MAIN-2025-38", "boards.greenhouse.io/*", 2000)
        self.assertIn("CC-MAIN-2025-38-index", url)
        self.assertIn("output=json", url)
        self.assertIn("limit=2000", url)
        self.assertIn("boards.greenhouse.io", url)

    def test_patterns_cover_oracle_and_core_ats(self):
        joined = " ".join(CC_QUERY_PATTERNS)
        self.assertIn("oraclecloud.com/hcmUI/CandidateExperience", joined)
        self.assertIn("boards.greenhouse.io", joined)
        self.assertIn("jobs.lever.co", joined)


class ParseLinesTests(unittest.TestCase):
    def test_parses_jsonl_urls(self):
        text = (
            '{"url": "https://boards.greenhouse.io/acme", "status": "200"}\n'
            '{"url": "https://jobs.lever.co/globex", "status": "200"}\n'
        )
        urls = parse_cc_index_lines(text)
        self.assertEqual(urls, {"https://boards.greenhouse.io/acme", "https://jobs.lever.co/globex"})

    def test_skips_non_json_and_empty(self):
        text = 'Blocked: rate limited\n\n{not json}\n{"url": "https://jobs.ashbyhq.com/x"}\n'
        self.assertEqual(parse_cc_index_lines(text), {"https://jobs.ashbyhq.com/x"})

    def test_empty_input(self):
        self.assertEqual(parse_cc_index_lines(""), set())
        self.assertEqual(parse_cc_index_lines(None), set())


class RoutingTests(unittest.TestCase):
    """Discovered CC URLs must route to valid ATS targets via parse_url_for_ats."""

    def test_oracle_url_routes(self):
        ats, slug, _ = parse_url_for_ats(
            "https://eeho.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/requisitions"
        )
        self.assertEqual(ats, "oracle")
        self.assertEqual(slug, "eeho.fa.us2.oraclecloud.com:CX_1")

    def test_greenhouse_url_routes(self):
        ats, slug, _ = parse_url_for_ats("https://boards.greenhouse.io/acme")
        self.assertEqual(ats, "greenhouse")
        self.assertEqual(slug, "acme")

    def test_non_ats_url_ignored(self):
        ats, slug, _ = parse_url_for_ats("https://example.com/about")
        self.assertIsNone(ats)
        self.assertIsNone(slug)


if __name__ == "__main__":
    unittest.main()
