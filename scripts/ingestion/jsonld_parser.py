"""schema.org/JobPosting extraction from embedded JSON-LD.

Nearly every career page embeds a `JobPosting` JSON-LD block for Google-for-Jobs
SEO. Parsing it gives a single universal adapter that works across the 40+ ATS
platforms we have no dedicated code for — the long-tail coverage technique the
big boards rely on.

Pure functions here (no network): `extract_jsonld_blocks` → `find_job_postings`
→ `normalize_job_posting`. The network fetch lives in JsonLdAdapter.
"""

from __future__ import annotations

import json
import re

_SCRIPT_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def extract_jsonld_blocks(html: str) -> list:
    """Return every parsed JSON-LD object found in <script type=ld+json> tags.

    Malformed blocks are skipped rather than raising — real pages ship broken
    JSON-LD often enough that one bad block must not lose the others.
    """
    if not html:
        return []
    blocks: list = []
    for match in _SCRIPT_RE.finditer(html):
        raw = (match.group(1) or "").strip()
        if not raw:
            continue
        try:
            blocks.append(json.loads(raw))
        except (json.JSONDecodeError, ValueError):
            # Some sites emit multiple concatenated JSON objects or trailing
            # commas; try a lenient recovery of the first complete object.
            recovered = _recover_first_object(raw)
            if recovered is not None:
                blocks.append(recovered)
    return blocks


def _recover_first_object(raw: str):
    depth = 0
    start = None
    for i, ch in enumerate(raw):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(raw[start : i + 1])
                except (json.JSONDecodeError, ValueError):
                    return None
    return None


def _is_type(obj: dict, wanted: str) -> bool:
    t = obj.get("@type")
    if isinstance(t, str):
        return t.lower() == wanted.lower()
    if isinstance(t, list):
        return any(isinstance(x, str) and x.lower() == wanted.lower() for x in t)
    return False


def find_job_postings(blocks: list) -> list:
    """Walk parsed JSON-LD (objects, arrays, @graph, ItemList) for JobPosting nodes."""
    found: list = []
    stack = list(blocks)
    seen = 0
    while stack and seen < 10000:  # guard against pathological nesting
        seen += 1
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            if _is_type(node, "JobPosting"):
                found.append(node)
                continue
            # Common containers that wrap JobPosting nodes.
            for key in ("@graph", "itemListElement", "item", "mainEntity"):
                if key in node:
                    stack.append(node[key])
    return found


def _first(value):
    """schema.org fields are frequently either a value or a list of values."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _org_name(hiring) -> str:
    hiring = _first(hiring)
    if isinstance(hiring, dict):
        return str(hiring.get("name") or "").strip()
    if isinstance(hiring, str):
        return hiring.strip()
    return ""


def _location(job: dict) -> str:
    parts: list[str] = []
    loc = _first(job.get("jobLocation"))
    if isinstance(loc, dict):
        addr = _first(loc.get("address")) or {}
        if isinstance(addr, dict):
            for key in ("addressLocality", "addressRegion", "addressCountry"):
                val = addr.get(key)
                if isinstance(val, dict):
                    val = val.get("name")
                if val and str(val).strip():
                    parts.append(str(val).strip())
        elif isinstance(addr, str) and addr.strip():
            parts.append(addr.strip())
    remote = str(job.get("jobLocationType") or "").upper()
    if "TELECOMMUTE" in remote and not parts:
        return "Remote"
    return ", ".join(dict.fromkeys(parts)) or ("Remote" if "TELECOMMUTE" in remote else "Unknown")


def _salary(job: dict):
    base = _first(job.get("baseSalary"))
    if not isinstance(base, dict):
        return None, None, None
    currency = base.get("currency") or base.get("salaryCurrency")
    value = _first(base.get("value"))
    smin = smax = None
    if isinstance(value, dict):
        smin = value.get("minValue")
        smax = value.get("maxValue")
        if smin is None and smax is None and value.get("value") is not None:
            smin = smax = value.get("value")
    elif isinstance(value, (int, float, str)):
        smin = smax = value

    def _num(x):
        try:
            return float(str(x).replace(",", "")) if x is not None else None
        except (ValueError, TypeError):
            return None

    return _num(smin), _num(smax), (str(currency).strip() if currency else None)


def _identifier(job: dict, url: str) -> str:
    ident = _first(job.get("identifier"))
    if isinstance(ident, dict):
        val = ident.get("value")
        if val:
            return str(val)
    elif isinstance(ident, (str, int)):
        return str(ident)
    return url or (str(job.get("title") or "")[:80])


def normalize_job_posting(job: dict, source_url: str = "") -> dict | None:
    """Map one JobPosting node to a NormalizedJob kwargs dict, or None if unusable."""
    title = str(job.get("title") or "").strip()
    if not title:
        return None
    url = str(_first(job.get("url")) or job.get("hiringOrganizationUrl") or source_url or "").strip()
    company = _org_name(job.get("hiringOrganization")) or "Unknown"
    smin, smax, currency = _salary(job)
    description = job.get("description")
    if isinstance(description, str):
        description = description.strip() or None
    else:
        description = None
    return {
        "title": title,
        "company": company,
        "location": _location(job),
        "url": url or source_url,
        "date_posted": str(job.get("datePosted") or "").strip(),
        "source_ats": "jsonld",
        "job_id": _identifier(job, url or source_url),
        "description": description,
        "salary_min": smin,
        "salary_max": smax,
        "salary_currency": currency,
    }


def parse_job_postings_from_html(html: str, source_url: str = "") -> list[dict]:
    """End-to-end: HTML → list of NormalizedJob kwargs dicts for every JobPosting."""
    postings = find_job_postings(extract_jsonld_blocks(html))
    out: list[dict] = []
    for jp in postings:
        normalized = normalize_job_posting(jp, source_url)
        if normalized:
            out.append(normalized)
    return out
