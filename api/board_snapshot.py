"""Cached public job board snapshot.

The home page reads this small JSON payload instead of paginating DB-backed
`/jobs` directly. This keeps public traffic from scaling Postgres egress.
"""

import json
import os
import re
import time
from datetime import datetime, timezone

from api.database import _is_pg, _ph, get_db

BOARD_CATEGORIES = ("All Roles", "AI/ML", "SWE", "Data", "Other")
DISCORD_DATA_CATEGORIES = {"Data Science", "Data Engineering", "Data Analyst"}
DISCORD_CATEGORY_MAP = {
    "AI/ML": "AI/ML",
    "SWE": "SWE",
    "Product": "Other",
    "Research": "Other",
    "New Grad": "Other",
    "Uncategorized": "Other",
}

NON_US_LOCATION_RE = re.compile(
    r"\b(canada|india|united kingdom|uk|england|scotland|wales|ireland|germany|france|spain|italy|"
    r"netherlands|sweden|poland|portugal|australia|new zealand|singapore|japan|china|brazil|mexico|"
    r"argentina|colombia|europe|emea|apac|latam|asia|bengaluru|budapest|london|dublin|cork|"
    r"remote poland|remote spain|hybrid - madrid)\b",
    re.I,
)
NON_US_COUNTRY_CODE_RE = re.compile(r"(^|[\s,(/-])(IE|GB|UK|IN|DE|FR|ES|PL|NL|BR|MX|AU|NZ|SG|JP|CN)(?=$|[\s,)/-])")
BAD_COMPANY_RE = re.compile(r"\bis looking for\b.*\bin\b", re.I)
US_LOCATION_RE = re.compile(
    r"\b(united states|usa|u\.s\.a\.|u\.s\.|us only|remote us|remote - us|remote \(us\)|america|"
    r"north america|alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|"
    r"florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|"
    r"maryland|massachusetts|michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|"
    r"new hampshire|new jersey|new mexico|new york|north carolina|north dakota|ohio|oklahoma|"
    r"oregon|pennsylvania|rhode island|south carolina|south dakota|tennessee|texas|utah|"
    r"vermont|virginia|washington|west virginia|wisconsin|wyoming|washington dc|district of columbia|"
    r"nyc|san francisco|los angeles|seattle|austin|boston|chicago|atlanta|denver|miami|dallas|"
    r"houston|phoenix|portland|philadelphia|nashville|raleigh|charlotte|san diego|san jose)\b",
    re.I,
)
US_STATE_CODE_RE = re.compile(
    r"(^|[\s,(/-])(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|"
    r"MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|"
    r"WA|WV|WI|WY|DC)(?=$|[\s,)/-])"
)

_snapshot_cache: tuple[float, dict] | None = None


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def board_snapshot_ttl_seconds() -> int:
    return max(0, _env_int("JOBCLAW_BOARD_SNAPSHOT_TTL_SECONDS", 300))


def _parse_keywords(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(v) for v in parsed if v]
    except (TypeError, json.JSONDecodeError):
        pass
    return [v.strip().strip("[]\"'") for v in str(value).split(",") if v.strip()]


def _category_for(row: dict) -> str:
    for category in _parse_keywords(row.get("keywords_matched")):
        if category in DISCORD_DATA_CATEGORIES:
            return "Data"
        if category in DISCORD_CATEGORY_MAP:
            return DISCORD_CATEGORY_MAP[category]

    text = f"{row.get('title') or ''} {' '.join(_parse_keywords(row.get('keywords_matched')))}".lower()
    if re.search(r"\b(data scientist|analytics scientist|data engineer|analytics engineer|etl|data platform)\b", text):
        return "Data"
    if re.search(r"\b(data analyst|business intelligence analyst|bi analyst|reporting analyst)\b", text):
        return "Data"
    if re.search(r"\b(ai|ml|machine learning|llm|research scientist|deep learning)\b", text):
        return "AI/ML"
    if re.search(
        r"\b(software engineer|software developer|frontend|backend|full stack|fullstack|devops|sre|"
        r"infrastructure|platform engineer|mobile engineer|ios engineer|android engineer|security engineer)\b",
        text,
    ):
        return "SWE"
    return "Other"


def _clean_location(value) -> str:
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    if not raw or re.match(r"^(unknown|n/a|none|null|not specified|location tbd)$", raw, re.I):
        return "Remote"
    return f"{raw[:39].strip()}..." if len(raw) > 42 else raw


def _is_us_location(location: str) -> bool:
    normalized = re.sub(r"\s+", " ", location).strip()
    if not normalized:
        return False
    if normalized.lower() == "remote":
        return True
    if NON_US_LOCATION_RE.search(normalized) or NON_US_COUNTRY_CODE_RE.search(normalized):
        return False
    return bool(US_LOCATION_RE.search(normalized) or US_STATE_CODE_RE.search(normalized))


def _source_label(source: str | None) -> str:
    if not source:
        return "Company Careers"
    labels = {
        "greenhouse": "Greenhouse",
        "lever": "Lever",
        "ashby": "Ashby",
        "workday": "Workday",
        "workable": "Workable",
        "rippling": "Rippling",
        "smartrecruiters": "SmartRecruiters",
        "bamboohr": "BambooHR",
        "rss": "RSS",
        "linkedin": "LinkedIn",
        "indeed": "Indeed",
    }
    return labels.get(source, source.replace("-", " ").replace("_", " "))


def _company_label(company: str | None, source: str) -> str:
    raw = re.sub(r"\s+", " ", str(company or "")).strip()
    if not raw or re.match(r"^(unknown|n/a|none|null)$", raw, re.I):
        return source
    return f"{raw[:69].strip()}..." if len(raw) > 72 else raw


def build_snapshot_from_rows(rows: list[dict], *, freshness_hours: int, max_jobs: int) -> dict:
    jobs = []
    counts = {category: 0 for category in BOARD_CATEGORIES}

    for index, row in enumerate(rows):
        if BAD_COMPANY_RE.search(str(row.get("company") or "")):
            continue

        location = _clean_location(row.get("location"))
        if not _is_us_location(location):
            continue

        source = _source_label(str(row.get("source_ats") or ""))
        category = _category_for(row)
        job = {
            "id": row.get("internal_hash") or row.get("job_id") or f"snapshot-job-{index}",
            "title": row.get("title") or "Untitled Role",
            "category": category,
            "company": _company_label(row.get("company"), source),
            "location": location,
            "applicationUrl": row.get("url") or "#",
            "postedAt": row.get("date_posted") or row.get("first_seen") or datetime.now(timezone.utc).isoformat(),
            "source": source,
        }
        if job["applicationUrl"] == "#":
            continue

        jobs.append(job)
        counts["All Roles"] += 1
        counts[category] += 1
        if len(jobs) >= max_jobs:
            break

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "freshness_hours": freshness_hours,
        "total": len(jobs),
        "counts": counts,
        "jobs": jobs,
    }


def _fetch_snapshot_rows(freshness_hours: int, max_jobs: int) -> list[dict]:
    conn = get_db()
    p = _ph()
    candidate_limit = max(max_jobs * 5, max_jobs)
    active = "TRUE" if _is_pg() else "1"
    try:
        cursor = conn.cursor()
        if _is_pg():
            cursor.execute(
                f"""
                SELECT internal_hash, job_id, title, company, location, url, date_posted,
                       source_ats, first_seen, keywords_matched, quality_state
                FROM jobs
                WHERE is_active = {active}
                  AND first_seen::timestamptz >= NOW() - ({p} * INTERVAL '1 hour')
                  AND COALESCE(quality_state, 'needs_review') <> 'rejected'
                ORDER BY
                  CASE WHEN COALESCE(quality_state, 'needs_review') = 'accepted' THEN 0 ELSE 1 END,
                  first_seen DESC
                LIMIT {p}
                """,
                (freshness_hours, candidate_limit),
            )
        else:
            cursor.execute(
                f"""
                SELECT internal_hash, job_id, title, company, location, url, date_posted,
                       source_ats, first_seen, keywords_matched, quality_state
                FROM jobs
                WHERE is_active = {active}
                  AND datetime(first_seen) >= datetime('now', {p})
                  AND COALESCE(quality_state, 'needs_review') <> 'rejected'
                ORDER BY
                  CASE WHEN COALESCE(quality_state, 'needs_review') = 'accepted' THEN 0 ELSE 1 END,
                  first_seen DESC
                LIMIT {p}
                """,
                (f"-{freshness_hours} hours", candidate_limit),
            )
        rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        return [dict(row) if hasattr(row, "keys") else dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()


def clear_board_snapshot_cache() -> None:
    global _snapshot_cache
    _snapshot_cache = None


def get_board_snapshot() -> dict:
    global _snapshot_cache
    ttl = board_snapshot_ttl_seconds()
    now = time.monotonic()
    if ttl > 0 and _snapshot_cache and now - _snapshot_cache[0] < ttl:
        return _snapshot_cache[1]

    freshness_hours = max(1, _env_int("JOBCLAW_BOARD_FRESHNESS_HOURS", 48))
    max_jobs = max(1, _env_int("JOBCLAW_BOARD_SNAPSHOT_MAX_JOBS", 1000))
    try:
        rows = _fetch_snapshot_rows(freshness_hours, max_jobs)
    except Exception:
        if _snapshot_cache:
            return _snapshot_cache[1]
        raise

    snapshot = build_snapshot_from_rows(rows, freshness_hours=freshness_hours, max_jobs=max_jobs)
    _snapshot_cache = (now, snapshot)
    return snapshot
