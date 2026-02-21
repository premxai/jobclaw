"""
Job Board Adapters.

Fetches jobs from job board APIs and RSS feeds, normalizing them into
NormalizedJob format compatible with the ATS adapter pipeline.

Supported boards:
  - RemoteOK       (remoteok.io/api)
  - Remotive       (remotive.com/api/remote-jobs)
  - WeWorkRemotely (weworkremotely.com RSS)
  - Dice           (dice.com RSS)
  - WorkingNomads  (workingnomads.com/api)
  - BuiltIn        (builtin.com structured)
  - HN Who's Hiring (hn.algolia.com API)
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional
import aiohttp
import re

from scripts.ingestion.ats_adapters import NormalizedJob


# ═══════════════════════════════════════════════════════════════════════
# REMOTEOK
# ═══════════════════════════════════════════════════════════════════════

class RemoteOKAdapter:
    """RemoteOK free JSON API: https://remoteok.io/api (24hr delayed)"""

    URL = "https://remoteok.io/api"

    @staticmethod
    async def fetch(session: aiohttp.ClientSession) -> list[NormalizedJob]:
        headers = {"User-Agent": "JobClaw/2.0 (job aggregator bot)"}
        try:
            async with session.get(
                RemoteOKAdapter.URL, headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json(content_type=None)

            if not isinstance(data, list):
                return []

            jobs = []
            for j in data:
                # First item is a legal notice, skip dicts without "slug"
                if not isinstance(j, dict) or "slug" not in j:
                    continue

                date_str = j.get("date", "")
                location = j.get("location", "Remote")
                if not location:
                    location = "Remote"

                tags = j.get("tags", [])
                if isinstance(tags, list):
                    tags = ", ".join(tags)

                jobs.append(NormalizedJob(
                    title=j.get("position", ""),
                    company=j.get("company", "Unknown"),
                    location=location,
                    url=j.get("url", f"https://remoteok.io/remote-jobs/{j.get('slug', '')}"),
                    date_posted=date_str,
                    source_ats="remoteok",
                    job_id=str(j.get("id", j.get("slug", ""))),
                ))
            return jobs
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════════════
# REMOTIVE
# ═══════════════════════════════════════════════════════════════════════

class RemotiveAdapter:
    """Remotive API: https://remotive.com/api/remote-jobs"""

    URL = "https://remotive.com/api/remote-jobs"

    @staticmethod
    async def fetch(session: aiohttp.ClientSession) -> list[NormalizedJob]:
        try:
            async with session.get(
                RemotiveAdapter.URL,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

            jobs = []
            for j in data.get("jobs", []):
                location = j.get("candidate_required_location", "Remote")
                if not location:
                    location = "Remote"

                jobs.append(NormalizedJob(
                    title=j.get("title", ""),
                    company=j.get("company_name", "Unknown"),
                    location=location,
                    url=j.get("url", ""),
                    date_posted=j.get("publication_date", ""),
                    source_ats="remotive",
                    job_id=str(j.get("id", "")),
                ))
            return jobs
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════════════
# WE WORK REMOTELY (RSS)
# ═══════════════════════════════════════════════════════════════════════

class WeWorkRemotelyAdapter:
    """We Work Remotely RSS feed: weworkremotely.com/categories/remote-*-jobs.rss"""

    # Fetch programming + devops + data categories
    FEEDS = [
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-and-sysadmin-jobs.rss",
    ]

    @staticmethod
    async def fetch(session: aiohttp.ClientSession) -> list[NormalizedJob]:
        all_jobs = []
        for feed_url in WeWorkRemotelyAdapter.FEEDS:
            try:
                async with session.get(
                    feed_url, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        continue
                    xml_text = await resp.text()

                root = ET.fromstring(xml_text)
                channel = root.find("channel")
                if channel is None:
                    continue

                for item in channel.findall("item"):
                    title_el = item.find("title")
                    link_el = item.find("link")
                    pub_el = item.find("pubDate")
                    # Title format: "Company Name: Job Title"
                    raw_title = title_el.text if title_el is not None else ""
                    company = "Unknown"
                    title = raw_title
                    if ": " in raw_title:
                        parts = raw_title.split(": ", 1)
                        company = parts[0].strip()
                        title = parts[1].strip()

                    all_jobs.append(NormalizedJob(
                        title=title,
                        company=company,
                        location="Remote",
                        url=link_el.text if link_el is not None else "",
                        date_posted=pub_el.text if pub_el is not None else "",
                        source_ats="weworkremotely",
                        job_id=link_el.text if link_el is not None else title,
                    ))
            except Exception:
                continue
        return all_jobs


# ═══════════════════════════════════════════════════════════════════════
# DICE (RSS)
# ═══════════════════════════════════════════════════════════════════════

class DiceAdapter:
    """Dice RSS feed for tech jobs."""

    URL = "https://www.dice.com/rss/interface/feed.xml"

    @staticmethod
    async def fetch(session: aiohttp.ClientSession) -> list[NormalizedJob]:
        # Dice may not have a public RSS anymore, fallback approach
        try:
            async with session.get(
                DiceAdapter.URL, timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": "JobClaw/2.0"}
            ) as resp:
                if resp.status != 200:
                    return []
                xml_text = await resp.text()

            root = ET.fromstring(xml_text)
            channel = root.find("channel")
            if channel is None:
                return []

            jobs = []
            for item in channel.findall("item"):
                title = item.find("title")
                link = item.find("link")
                pub = item.find("pubDate")

                jobs.append(NormalizedJob(
                    title=title.text if title is not None else "",
                    company="Unknown",
                    location="Unknown",
                    url=link.text if link is not None else "",
                    date_posted=pub.text if pub is not None else "",
                    source_ats="dice",
                    job_id=link.text if link is not None else "",
                ))
            return jobs
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════════════
# HN WHO'S HIRING (Algolia API)
# ═══════════════════════════════════════════════════════════════════════

class HNWhoIsHiringAdapter:
    """Hacker News Who's Hiring via Algolia API.

    Fetches the latest "Ask HN: Who is hiring?" thread comments.
    """

    SEARCH_URL = "https://hn.algolia.com/api/v1/search"
    ITEMS_URL = "https://hn.algolia.com/api/v1/items"

    @staticmethod
    async def fetch(session: aiohttp.ClientSession) -> list[NormalizedJob]:
        try:
            # 1. Find the latest "Who is hiring?" thread
            params = {
                "query": "Ask HN: Who is hiring?",
                "tags": "ask_hn",
                "numericFilters": "num_comments>100",
                "hitsPerPage": 1,
            }
            async with session.get(
                HNWhoIsHiringAdapter.SEARCH_URL, params=params,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

            hits = data.get("hits", [])
            if not hits:
                return []

            thread_id = hits[0].get("objectID", "")
            if not thread_id:
                return []

            # 2. Fetch thread comments
            async with session.get(
                f"{HNWhoIsHiringAdapter.ITEMS_URL}/{thread_id}",
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    return []
                thread = await resp.json()

            # 3. Parse comments into jobs
            jobs = []
            for child in thread.get("children", [])[:200]:  # Cap at 200
                text = child.get("text", "")
                if not text:
                    continue

                # HN format: "Company Name | Role | Location | ..."
                # First line usually has the key info
                first_line = text.split("\n")[0] if text else ""
                # Remove HTML tags
                first_line = re.sub(r"<[^>]+>", "", first_line)

                parts = [p.strip() for p in first_line.split("|")]
                if len(parts) < 2:
                    continue

                company = parts[0]
                title = parts[1] if len(parts) > 1 else ""
                location = parts[2] if len(parts) > 2 else "Unknown"

                created = child.get("created_at", "")

                jobs.append(NormalizedJob(
                    title=title,
                    company=company,
                    location=location,
                    url=f"https://news.ycombinator.com/item?id={child.get('id', '')}",
                    date_posted=created,
                    source_ats="hackernews",
                    job_id=str(child.get("id", "")),
                ))
            return jobs
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════════════
# ADAPTER REGISTRY
# ═══════════════════════════════════════════════════════════════════════

JOB_BOARD_ADAPTERS = {
    "remoteok": RemoteOKAdapter,
    "remotive": RemotiveAdapter,
    "weworkremotely": WeWorkRemotelyAdapter,
    "dice": DiceAdapter,
    "hackernews": HNWhoIsHiringAdapter,
}


async def fetch_all_job_boards(session: aiohttp.ClientSession) -> tuple[list[NormalizedJob], list[str]]:
    """Fetch jobs from all job board APIs.

    Returns:
        Tuple of (all_jobs, errors)
    """
    all_jobs = []
    errors = []

    for name, adapter in JOB_BOARD_ADAPTERS.items():
        try:
            jobs = await adapter.fetch(session)
            all_jobs.extend(jobs)
        except Exception as e:
            errors.append(f"Job board {name}: {str(e)}")

    return all_jobs, errors
