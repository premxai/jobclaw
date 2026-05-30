"""Helpers for registry validation and scrape failure classification."""

from __future__ import annotations

import re
from urllib.parse import urlparse

SUPPORTED_ATS = {
    "greenhouse",
    "lever",
    "ashby",
    "workday",
    "workable",
    "rippling",
    "smartrecruiters",
    "bamboohr",
    "gem",
}

_WORKDAY_URL_RE = re.compile(
    r"^https?://([^.]+)\.wd(\d+)\.myworkdayjobs\.com/(?:en-[A-Za-z]{2}/)?([^/?#]+?)/?$",
    re.I,
)

_ATS_DOMAIN_HINTS = {
    "greenhouse": ("boards-api.greenhouse.io", "boards.greenhouse.io"),
    "lever": ("api.lever.co", "jobs.lever.co"),
    "ashby": ("api.ashbyhq.com", "jobs.ashbyhq.com"),
    "workday": ("myworkdayjobs.com",),
    "workable": ("apply.workable.com",),
    "rippling": ("ats.rippling.com", "rippling.com"),
    "smartrecruiters": ("api.smartrecruiters.com", "jobs.smartrecruiters.com"),
    "bamboohr": ("bamboohr.com",),
    "gem": ("job-boards.gem.com", "gem.com"),
}


def _infer_ats_from_url(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return None
    for ats, hints in _ATS_DOMAIN_HINTS.items():
        if any(host == hint or host.endswith(f".{hint}") for hint in hints):
            return ats
    return None


def normalize_registry_target(company: str, ats: str, slug: str) -> tuple[dict[str, str] | None, str | None]:
    """Validate and normalize a registry entry before scraping."""
    company = (company or "").strip()
    ats = (ats or "").strip().lower()
    slug = (slug or "").strip()

    if not company or not ats or not slug:
        return None, "missing_fields"

    if ats not in SUPPORTED_ATS:
        return None, f"unsupported_ats:{ats}"

    if ats == "workday":
        workday_host = (urlparse(slug).hostname or "").lower()
        if workday_host == "myworkdayjobs.com" or workday_host.endswith(".myworkdayjobs.com"):
            match = _WORKDAY_URL_RE.match(slug)
            if not match:
                return None, "malformed_workday_url"
            slug = f"{match.group(1)}:{match.group(2)}:{match.group(3)}"
        else:
            parts = slug.split(":")
            if len(parts) != 3 or not parts[1].isdigit() or not parts[0] or not parts[2]:
                return None, "malformed_workday_slug"
    else:
        if slug.startswith(("http://", "https://")):
            inferred = _infer_ats_from_url(slug)
            if inferred and inferred != ats:
                return None, f"ats_mismatch:{inferred}"

            # Extract a likely slug when the source entry used a full board URL.
            host = (urlparse(slug).hostname or "").lower()
            path = urlparse(slug).path.strip("/")
            if ats == "greenhouse" and (host == "greenhouse.io" or host.endswith(".greenhouse.io")):
                slug = path.split("/")[0]
            elif ats == "lever" and (host == "lever.co" or host.endswith(".lever.co")):
                slug = path.split("/")[0]
            elif ats == "ashby" and (host == "ashbyhq.com" or host.endswith(".ashbyhq.com")):
                slug = path.split("/")[0]
            elif ats == "workable" and (host == "workable.com" or host.endswith(".workable.com")):
                slug = path.split("/")[0]
            elif ats == "rippling" and (host == "rippling.com" or host.endswith(".rippling.com")):
                slug = path.split("/")[0]
            elif ats == "smartrecruiters" and (host == "smartrecruiters.com" or host.endswith(".smartrecruiters.com")):
                slug = path.split("/")[0]
            elif ats == "bamboohr" and (host == "bamboohr.com" or host.endswith(".bamboohr.com")):
                slug = path.split("/")[0]
            elif ats == "gem" and (host == "gem.com" or host.endswith(".gem.com")):
                slug = path.split("/")[0]

        if any(ch in slug for ch in " /?#"):
            return None, "malformed_slug"

    return {"company": company, "ats": ats, "slug": slug}, None


def classify_failure(
    *,
    status_code: int | None = None,
    error: str | Exception | None = None,
    url: str | None = None,
    ats: str | None = None,
    slug: str | None = None,
) -> dict[str, object]:
    """Classify a scrape failure into target-quality or anti-bot buckets."""
    message = str(error or "").strip()
    haystack = " ".join(part for part in [message, url or "", ats or "", slug or ""]).lower()

    if status_code in {404, 410, 422}:
        category = "bad_target"
    elif status_code == 429 or any(token in haystack for token in ("rate limit", "too many requests")):
        category = "anti_bot"
    elif status_code == 403 or any(token in haystack for token in ("forbidden", "captcha", "blocked", "bot", "waf", "csrf", "challenge")):
        category = "anti_bot"
    elif "timeout" in haystack:
        category = "timeout"
    elif any(token in haystack for token in ("json decode", "parse", "html response", "unexpected content", "malformed")):
        category = "parse"
    elif status_code is not None and status_code >= 500:
        category = "transient"
    else:
        category = "unknown"

    return {
        "category": category,
        "status_code": status_code,
        "error": message,
        "url": url,
        "ats": ats,
        "slug": slug,
        "is_bad_target": category == "bad_target",
        "is_anti_bot": category == "anti_bot",
    }
