"""
Discovery Module — automatic company discovery for ATS scraping.

This module provides two discovery methods:
1. search_discovery: Uses Brave Search API to find companies via site: queries
2. career_crawler: Detects ATS from company career pages given domain list
"""

from scripts.discovery.career_crawler import run_career_crawler
from scripts.discovery.search_discovery import run_discovery

__all__ = ["run_discovery", "run_career_crawler"]
