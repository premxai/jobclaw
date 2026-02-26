# Scraping Infrastructure Analysis

**Two-System Comparison: `temp_ats_scrapers` (stapply) vs Main Pipeline (`scripts/`)**

*Analysis date: 2025-02-20*
*Files read: 60+ across both systems*

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [What stapply Does That the Main Pipeline DOESN'T](#2-what-stapply-does-that-the-main-pipeline-doesnt)
3. [What the Main Pipeline Does WRONG (or Worse)](#3-what-the-main-pipeline-does-wrong-or-worse)
4. [What the Main Pipeline Does That stapply DOESN'T](#4-what-the-main-pipeline-does-that-stapply-doesnt)
5. [Security & Anti-Detection Analysis](#5-security--anti-detection-analysis)
6. [Database Architecture Comparison](#6-database-architecture-comparison)
7. [Integration Opportunities](#7-integration-opportunities)
8. [Recommendation](#8-recommendation)

---

## 1. Architecture Overview

### stapply (`temp_ats_scrapers/`)

```
Discovery → Scraping → JSON Storage → CSV Export → DB Sync → Enrichment
   │            │            │             │           │          │
SearXNG    Per-ATS      companies/     export_     fetch_    salary/
SerpAPI    async        {slug}.json    to_csv.py   job.py   experience
           scrapers                                          embeddings
```

- **Language**: Python 3.12+
- **Async framework**: `aiohttp` for ATS APIs, `requests` for enterprise, Playwright for Google/Meta/Tesla
- **Database**: PostgreSQL via SQLAlchemy ORM (UUID primary keys, vector embeddings)
- **Data flow**: Scrape → JSON files → CSV (with diff tracking) → PostgreSQL
- **Storage**: Cloudflare R2 (S3-compatible)
- **ML**: OpenAI embeddings (`text-embedding-3-small`), Ollama classifier for EU internships, torch/transformers
- **API layer**: FastAPI REST API wrapping SerpAPI + JSearch

### Main Pipeline (`scripts/`)

```
Registry → Parallel Fetch → Role Filter → US Filter → Time Filter → Dedup → SQLite
              │                                                                 │
        ATS Adapters                                                      Discord Bot
        Job Boards                                                        (unposted → posted)
        Aggregators
        Enterprise APIs
        GitHub Repos
```

- **Language**: Python (no version constraint)
- **Async framework**: `aiohttp` throughout (unified)
- **Database**: SQLite with WAL mode
- **Data flow**: Direct API → NormalizedJob dataclass → filter pipeline → SQLite → Discord
- **Registry**: `company_registry.json` (48,582 lines, hundreds of companies)
- **Output**: Discord webhook (status: `unposted` → `posted`)

---

## 2. What stapply Does That the Main Pipeline DOESN'T

### 2.1 Company Discovery Engines

**SearXNG Discovery** (`searxng_discovery.py` — 978 lines)
- Self-hosted SearXNG instance for **unlimited, free** company discovery
- ~150 search strategies: site-specific queries combined with role keywords, VC portfolios, city names, regions
- Supports 8 platforms: Rippling, Ashby, Greenhouse, Lever, Workable, SmartRecruiters, Workday, Gem
- URL normalization per platform (e.g., greenhouse slug extraction from board URLs)
- Checkpoint system: saves progress after EACH query so crashes don't lose work
- Configurable search engines, rate limiting, exponential backoff for 429s
- Atomic CSV writes via tempfile

**SerpAPI Discovery** (`serpapi_discovery.py`)
- Google search-based discovery for 4 platforms (Ashby, Greenhouse, Lever, Workable)
- Extracts company names from URL slugs

**Main pipeline equivalent**: None. The main pipeline relies entirely on a static `company_registry.json` that must be manually curated. There is no automated way to discover new companies. This is a **critical gap** — stapply can continuously expand its company coverage while the main pipeline stagnates.

### 2.2 JSON Caching Layer with Scrape Cooldowns

Every stapply scraper (Ashby, Greenhouse, Lever, Workable, SmartRecruiters, Rippling, Workday) stores raw API responses as `companies/{slug}.json` with a `last_scraped` timestamp. On subsequent runs:
- If scraped within 12-24 hours (configurable per ATS), the company is **skipped**
- This prevents hammering APIs and provides a cached data layer for enrichment

The main pipeline **fetches fresh on every run** with no caching. Every cycle hits every API endpoint regardless of recency.

### 2.3 Job Description Storage & Extraction

stapply stores **full job descriptions** (HTML) in per-company JSON files. `fetch_job.py` (1,329 lines) has per-ATS description extractors for all 15+ platforms:
- Ashby: `content.descriptionHtml`
- Greenhouse: `content` field
- Lever: `descriptionPlain` + `lists[].content` concatenation
- Workable: `description`
- Rippling: `description.role` + `description.company` HTML
- Plus: Google, Microsoft, NVIDIA, Amazon, Meta, TikTok, Tesla, Cursor, Apple, Uber

The main pipeline **stores only metadata** (title, company, location, URL, date) — no descriptions at all. This means:
- No salary extraction possible
- No experience extraction possible
- No embeddings possible
- No NLP-based filtering or classification
- Users must visit the URL to see the job description

### 2.4 Salary & Experience Extraction

`extract_salary_experience.py` (785 lines):
- **Salary**: 
  - Multi-currency support ($, €, £, ¥, ₹)
  - Range detection ("$120k - $180k", "$120,000 to $180,000")
  - European number formats (dots as thousand separators)
  - False positive filtering (excludes revenue figures, ARR, customer counts)
  - Handles hourly/yearly/monthly periods
- **Experience**:
  - 14+ regex patterns ordered by specificity
  - Handles "3+ years", "3-5 years", "minimum 3 years", etc.
  - Extracts structured `(min_years, max_years)` tuples

The main pipeline has **zero** salary or experience extraction.

### 2.5 OpenAI Embeddings

`ashby/process_ashby.py` generates vector embeddings via OpenAI:
- `text-embedding-3-small` for both descriptions and titles
- Stored directly in PostgreSQL (vector columns)
- Checkpoint/resume system via `processed_companies.txt`
- Job lifecycle tracking: deactivates jobs removed from ATS

The database model (`models/db.py`) has dedicated fields:
```python
embedding: Optional[str]        # vector type
title_embedding: Optional[str]  # vector type
```

The main pipeline has **no embedding support**.

### 2.6 CSV Diff Tracking

`export_utils.py` implements a sophisticated diff engine:
- Compares current scrape against previous CSV
- Generates `jobs_diff_{timestamp}.csv` with status column: `new`, `updated`, `removed`
- Deterministic UUID5 job IDs: `generate_job_id(platform, url, ats_id)`
- `_compute_diff()` classifies every row by comparing URL+ats_id combinations

The main pipeline uses a simple hash-based dedup (`sha256(title|company|location)`) with no change tracking.

### 2.7 Posted-At Backfill

`backfill_posted_at.py`:
- Extracts timestamps from raw JSON data per ATS
- Ashby: `publishedAt`, Greenhouse: `updated_at`/`first_published`, Lever: `createdAt` (ms epoch), Rippling: `created_on`, Workable: `published_on`/`created_at`
- Keeps earliest timestamp on conflicts
- Atomic file writes with backup

### 2.8 FastAPI Job Search API

`api/` directory provides a REST API:
- `GET/POST /search` with query, location, provider, pagination, employment_type, date_posted, remote_only
- Multi-provider aggregation (SerpAPI + JSearch)
- Result deduplication and date sorting
- Pydantic models with salary, benefits, requirements, tags

The main pipeline has no API whatsoever — it's a one-way pipeline into SQLite/Discord.

### 2.9 Workday HTML Scraping

stapply's Workday scraper (`workday/main.py`, 280+ lines):
- Uses BeautifulSoup to parse HTML job listing pages
- Extracts: title, location, posted date, job requisition ID from `data-automation-id` attributes
- Fetches **detail pages** with concurrent semaphore control (8 parallel)
- Extracts full description HTML, remote type, apply URL

The main pipeline's `WorkdayAdapter` uses the CXS JSON API (`/wday/cxs/`) which:
- Only returns metadata (title, location, `externalPath`)
- Is capped at 200 jobs (10 pages × 20)
- Requires a non-standard `tenant:shard:site` slug format
- Returns no descriptions

### 2.10 EU Internship Classifier

`classifier/main.py` (505 lines):
- Local Ollama model (custom `euro_intern_classifier`)
- Classifies jobs as "European tech internship" or not
- Checkpoint system with processed job IDs
- Reads descriptions from JSON files for context
- ATS-aware description extraction (Lever concatenation, Greenhouse HTML decoding)

### 2.11 Cloudflare R2 Upload

`upload_to_cloudflare.py`: Uploads scraped data to Cloudflare R2 (S3-compatible storage) for external access/backup.

---

## 3. What the Main Pipeline Does WRONG (or Worse)

### 3.1 No HTTP Headers on ATS Requests

The main pipeline's `ats_adapters.py` makes **bare aiohttp requests** with no custom headers:

```python
# ats_adapters.py — ALL adapters do this:
async with session.get(url, params=params, timeout=...) as resp:
```

No User-Agent. No Accept-Language. No Referer. This means:
- aiohttp's default User-Agent (`aiohttp/X.Y.Z`) is sent
- Many APIs will reject or rate-limit this immediately
- Basic bot detection catches this trivially

stapply is only slightly better — some scrapers set headers (Workday, Rippling, enterprise scrapers) while others don't (Ashby, Greenhouse, Lever use bare aiohttp). But the enterprise scrapers all have proper headers.

### 3.2 No Retry Logic in ATS Adapters

Every adapter in `ats_adapters.py` wraps everything in a bare `try/except Exception: return []`:

```python
try:
    async with session.get(url, ...) as resp:
        if resp.status != 200:
            return []
        data = await resp.json()
    # ... parse ...
    return jobs
except Exception:
    return []  # Silent failure!
```

- No retries on transient failures (429, 500, 502, 503)
- No exponential backoff
- No error logging — failures are completely **silent**
- No distinction between "API is down" and "company doesn't exist"

`scrape_ats.py` adds a wrapper with 2 retries, but the error is only captured as a string — not logged or reported in detail.

stapply's scrapers all have proper retry loops with exponential backoff and detailed logging.

### 3.3 Pagination Limits

| Platform | Main Pipeline Limit | stapply Limit |
|---|---|---|
| Workday | 200 jobs (10 pages × 20) | 200 pages × variable |
| SmartRecruiters | Proper pagination ✓ | Proper pagination ✓ |
| Workable | **Single page only** | Single page (API limit) |
| Amazon | Single page (25 jobs) | 10,000 jobs (400 pages, parallel batches) |
| Microsoft | Single page (20 jobs) | Full pagination with description caching |
| NVIDIA | Single page (10 jobs) | Full pagination with description caching |
| Uber | Single page (10 jobs) | Full pagination |
| Apple | 5 pages | API supports all pages |
| TikTok | 5 pages | Full pagination |

The enterprise scraper (`scrape_enterprise.py`) fetches only 5 pages per API, while stapply's standalone scrapers paginate to exhaustion. For Amazon alone, this is the difference between **25 jobs** and **10,000 jobs**.

### 3.4 SQLite vs PostgreSQL

| Feature | Main Pipeline (SQLite) | stapply (PostgreSQL) |
|---|---|---|
| Vector search | ❌ | ✅ (pgvector) |
| Concurrent writes | Limited (WAL helps) | ✅ Full MVCC |
| Full-text search | Basic | ✅ Native |
| Scaling | Single file | Distributed |
| Embeddings | ❌ | ✅ (vector columns) |
| Job descriptions | ❌ | ✅ |
| Salary data | ❌ | ✅ |
| Company table | ❌ | ✅ (with get-or-create) |
| Job lifecycle | ❌ | ✅ (is_active, verified_at) |
| Geo data | ❌ | ✅ (lat/lon/point/country/city) |

### 3.5 No Description Storage

The main pipeline's NormalizedJob dataclass:
```python
@dataclass
class NormalizedJob:
    title: str
    company: str
    location: str
    url: str
    date_posted: str
    source_ats: str
    job_id: str
    first_seen: str = ""
    keywords_matched: list[str] = field(default_factory=list)
```

No `description` field. The SQLite schema also has no description column. This is the single biggest architectural gap — without descriptions, most enrichment features are impossible.

### 3.6 Dedup Strategy Is Fragile

Main pipeline dedup key:
```python
raw = f"{self.title}|{self.company}|{self.location}".lower().strip()
return hashlib.sha256(raw.encode()).hexdigest()[:16]
```

Problems:
- Same job posted in two locations = **two different entries** (not deduplicated by job ID)
- Title changes (e.g., "Software Engineer" → "Software Engineer, Backend") = **duplicate**
- Doesn't use the ATS job ID at all for the dedup key

stapply uses deterministic UUID5: `uuid5(NAMESPACE_URL, f"{platform}:{ats_id}:{url}")` — more robust, and the real ATS job ID is the primary key.

### 3.7 Enterprise Scraper Design

The main pipeline's `scrape_enterprise.py` duplicates a lot of code from stapply but:
- Google/Meta: Uses exact same Playwright interception pattern as stapply (literally copied) but with less error handling
- No description caching (Microsoft/NVIDIA fetch descriptions fresh every time)
- Meta's GraphQL response parsing is less robust (no scroll pagination for all 1000+ jobs)
- No force/freshness flags — always scrapes (wastes API calls)

### 3.8 Workable API Version

Main pipeline uses `apply.workable.com/api/v3/accounts/{slug}/jobs` (POST with filters).
stapply uses `apply.workable.com/api/v1/widget/accounts/{slug}` (older widget API).

Both should work, but the v3 API is better. This is one area where the main pipeline is actually ahead.

---

## 4. What the Main Pipeline Does That stapply DOESN'T

### 4.1 Multi-Source Aggregation

The main pipeline ingests from **5 additional source categories** that stapply completely lacks:

| Source | Adapter | Jobs |
|---|---|---|
| RemoteOK | `RemoteOKAdapter` | JSON API |
| Remotive | `RemotiveAdapter` | JSON API |
| We Work Remotely | `WeWorkRemotelyAdapter` | RSS |
| Dice | `DiceAdapter` | RSS |
| HN Who's Hiring | `HNWhoIsHiringAdapter` | Algolia API |
| HiringCafe | `HiringCafeAdapter` | Internal API |
| Jobright.ai | `JobrightAdapter` | Internal API |
| YC Work at a Startup | `YCWorkAtStartupAdapter` | Algolia API |
| SimplifyJobs repos | `SimplifyJobsParser` | GitHub JSON |
| Markdown table repos | `MarkdownTableParser` | GitHub markdown |

### 4.2 Role Keyword Filtering

`role_filter.py` has **142+ curated role patterns** across 8 categories:
- AI/ML (34 patterns)
- Data Science (14 patterns)
- Data Engineering (17 patterns)
- Data Analyst (16 patterns)
- SWE (25 patterns)
- New Grad / Early Career (12 patterns)
- Product (2 patterns)
- Research (3 patterns)

stapply has no role filtering at the scraping level. It scrapes ALL jobs from every company.

### 4.3 US Location Filtering

`us_filter.py`:
- Uses `config/us_locations.json` with include/exclude patterns
- Word-boundary matching for 2-letter state codes
- Exclude patterns for non-US countries/cities
- "Include rather than exclude" philosophy for unknowns

stapply has no location filtering — it scrapes all locations.

### 4.4 Discord Integration

The main pipeline has a Discord bot (`scripts/discord_bot.py`) that:
- Queries SQLite for `status = 'unposted'` jobs
- Posts them to a Discord channel via webhook
- Marks jobs as `status = 'posted'` after send

stapply has no notification/distribution system.

### 4.5 Massive Company Registry

`company_registry.json` is 48,582 lines with hundreds of companies spanning:
- Greenhouse, Lever, Ashby, Workday, Workable, Rippling, SmartRecruiters, BambooHR

stapply has per-ATS CSVs (e.g., `ashby/companies.csv`) that are typically smaller. However, stapply's discovery engines can automatically find new companies.

### 4.6 Unified Run Orchestration

`parallel_ingestor.py` provides a complete single-command cycle:
1. Load registry
2. Parallel ATS fetch (25 concurrent, 5 per host)
3. Job board fetch
4. Aggregator fetch
5. Role filter
6. US location filter
7. Time window filter
8. Dedup against known jobs
9. Store results
10. Log run metrics

stapply has no unified orchestrator — each scraper runs independently, and `gather_jobs.py` merges CSVs afterward.

### 4.7 BambooHR Adapter

The main pipeline supports BambooHR (`{slug}.bamboohr.com/careers/list`), which stapply doesn't cover.

---

## 5. Security & Anti-Detection Analysis

### 5.1 User-Agent Handling

| Component | User-Agent | Grade |
|---|---|---|
| Main pipeline ATS adapters | **None** (aiohttp default) | 🔴 F |
| Main pipeline enterprise scrapers | `"Mozilla/5.0"` stub | 🟡 D |
| stapply Ashby/Greenhouse/Lever | **None** (aiohttp default) | 🔴 F |
| stapply Workday | Full Chrome UA + Accept-Language | 🟢 B |
| stapply Rippling | Full macOS Chrome UA | 🟢 B |
| stapply Amazon | `"Mozilla/5.0"` stub | 🟡 D |
| stapply Microsoft/NVIDIA | `"Mozilla/5.0"` stub | 🟡 D |
| stapply Uber | Full UA + Origin + Referer + CSRF token | 🟢 A |
| stapply TikTok | Full UA + Origin + Referer + website-path | 🟢 A |
| stapply Google/Meta (Playwright) | Full browser UA via `new_context()` | 🟢 A |
| stapply Cursor | `"StapplyMap/1.0"` bot identifier | 🟡 C |

### 5.2 SSL/TLS Handling

- **stapply**: Multiple scrapers use `aiohttp.TCPConnector(ssl=False)` — **disables SSL verification entirely**. This is a security risk (MITM vulnerability) and also a detection signal (some CDNs log clients that don't verify certs).
- **Main pipeline**: Uses default SSL via `aiohttp.TCPConnector(limit=MAX_CONCURRENT, limit_per_host=5)` — proper SSL, no issues.

### 5.3 Rate Limiting & Delays

| System | Inter-Company Delay | Inter-Request Delay | Concurrency |
|---|---|---|---|
| Main pipeline ATS | None | None | 50 concurrent, 5/host |
| Main pipeline enterprise | 1s between page batches | None | Sequential within API |
| stapply ATS scrapers | 1-3s random between companies | None within company | Sequential |
| stapply Workday | 1-3s between companies | None (8 concurrent details) | Sequential companies |
| stapply Amazon | Jitter-based backoff | None (10 parallel pages) | Batch parallel |
| stapply Microsoft/NVIDIA | 0.5s between requests | 0.5s between detail fetches | Sequential |
| stapply Uber | 0.5s via API client | 0.5s | Sequential pages |

**Analysis**: The main pipeline's 50-concurrent approach with zero delay is the most aggressive. It will hit the 5/host limit, but multiple companies on the same ATS platform could still trigger rate limits. stapply is more conservative with sequential processing and randomized delays.

### 5.4 IP Rotation / Proxy Support

- **stapply**: Has **commented-out** proxy code in `ashby/main.py` (evomi.com residential proxy). `pyproject.toml` lists `playwright-stealth` as a dependency. `tesla/api_client.py` has exhaustive documentation about Akamai bot detection with recommendations for ScraperAPI, Bright Data, Oxylabs, SmartProxy. Some scrapers import `cloudscraper` (Rippling). **However, none of these are actively used.**
- **Main pipeline**: No proxy support whatsoever.

### 5.5 Cookie/Session Handling

- **stapply**: Tesla scraper documents the need for `_abck`, `bm_sz`, `bm_s` cookies for Akamai-protected sites. Uber scraper sets `x-csrf-token: x`. Apple sets `browserlocale` and `locale` headers plus CSRF token negotiation. Meta/Google use Playwright (full browser sessions with cookies).
- **Main pipeline's `scrape_enterprise.py`**: Copies Apple's CSRF pattern and Uber's `x-csrf-token: x`. Google/Meta use same Playwright approach.

### 5.6 Fingerprinting Evasion

Neither system implements:
- Browser fingerprint randomization
- Canvas/WebGL spoofing
- WebRTC leak protection
- TLS fingerprint randomization (JA3)
- Mouse movement simulation

The `playwright-stealth` dependency in stapply's `pyproject.toml` could address some of these, but it's not imported or used in any read file.

### 5.7 Overall Security Grade

| Area | Main Pipeline | stapply |
|---|---|---|
| User-Agent rotation | 🔴 None | 🟡 Per-scraper static UAs |
| SSL verification | 🟢 Proper | 🔴 Disabled in some scrapers |
| Rate limiting | 🔴 Aggressive (50 concurrent) | 🟡 Conservative but no backpressure |
| Proxy rotation | 🔴 None | 🔴 None (commented out) |
| Cookie management | 🟡 Playwright for some | 🟡 Playwright for some |
| Retry with backoff | 🔴 Silent failure | 🟢 Exponential backoff |
| Bot detection evasion | 🔴 None | 🟡 Playwright + stealth (partial) |

---

## 6. Database Architecture Comparison

### Main Pipeline (SQLite)

```sql
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    internal_hash TEXT UNIQUE NOT NULL,     -- source_ats::company::job_id
    job_id TEXT,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    url TEXT NOT NULL,
    date_posted TEXT,
    source_ats TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    status TEXT DEFAULT 'unposted',         -- unposted | posted
    keywords_matched TEXT                   -- JSON array
);
```

- 11 columns, flat structure
- Dedup via `internal_hash` unique constraint
- Status tracking for Discord posting
- No foreign keys, no normalization

### stapply (PostgreSQL)

```python
# models/db.py DatabaseJob model (32+ fields)
class DatabaseJob(pydantic.BaseModel):
    id: Optional[UUID]
    url: str
    title: str
    location: Optional[str]
    company: str
    description: Optional[str]
    employment_type: Optional[str]
    industry: Optional[str]
    embedding: Optional[str]          # vector
    posted_at: Optional[datetime]
    created_at: Optional[datetime]
    source: Optional[str]
    is_active: bool = True
    remote: Optional[bool]
    wfh: Optional[bool]
    application_url: Optional[str]
    language: Optional[str]
    title_embedding: Optional[str]    # vector
    verified_at: Optional[datetime]
    lon: Optional[float]
    lat: Optional[float]
    country: Optional[str]
    point: Optional[str]
    salary_min: Optional[float]
    salary_max: Optional[float]
    salary_currency: Optional[str]
    salary_period: Optional[str]
    city: Optional[str]
    ats_type: Optional[str]
    company_id: Optional[UUID]
```

- 32+ columns with rich types
- Separate Company table with UUID FK
- Vector embeddings for semantic search
- Geolocation (lat/lon/point)
- Salary fields (min/max/currency/period)
- Lifecycle tracking (is_active, verified_at)
- Remote/WFH flags

---

## 7. Integration Opportunities

### 7.1 Direct Replacements (HIGH VALUE)

| stapply Feature | Replaces/Enhances | Effort | Value |
|---|---|---|---|
| `searxng_discovery.py` | Static registry → dynamic discovery | Medium | 🔴 Critical |
| `extract_salary_experience.py` | Nothing → salary+exp extraction | Low (standalone) | 🔴 Critical |
| `export_utils.py` diff tracking | Simple dedup → change tracking | Low | 🟡 High |
| Retry + backoff patterns | Silent failures → resilient fetching | Low | 🟡 High |
| JSON caching layer | Always-fresh → smart caching | Medium | 🟡 High |

### 7.2 Adaptations Needed (MEDIUM VALUE)

| stapply Feature | Integration Path | Effort |
|---|---|---|
| Enterprise scrapers (full pagination) | Replace `scrape_enterprise.py` page limits with stapply's full pagination | Medium |
| Workday HTML scraper | Replace CXS JSON adapter with HTML scraper for more data | Medium |
| Description storage | Add `description` column to SQLite + extract from responses | Medium |
| PostgreSQL migration | Migrate from SQLite to PostgreSQL for vectors/scale | High |
| OpenAI embeddings | Add embedding generation post-scrape | Medium |

### 7.3 Redundancies to Resolve

| Feature | Main Pipeline | stapply | Winner |
|---|---|---|---|
| Greenhouse adapter | `ats_adapters.py` | `greenhouse/main.py` | Main (async) + stapply (caching) → merge |
| Lever adapter | `ats_adapters.py` | `lever/main.py` | Main (async) + stapply (caching) → merge |
| Ashby adapter | `ats_adapters.py` | `ashby/main.py` | Main (async) + stapply (caching) → merge |
| Workable adapter | `ats_adapters.py` (v3 API) | `workable/main.py` (v1 API) | Main (v3 is better) |
| SmartRecruiters adapter | `ats_adapters.py` | `smartrecruiters/main.py` | Main (pagination) |
| Rippling adapter | `ats_adapters.py` (JSON API) | `rippling/main.py` (HTML + cloudscraper) | stapply (richer data) |
| Amazon scraper | `scrape_enterprise.py` (25 jobs) | `amazon/main.py` (10K+ jobs) | **stapply** |
| Microsoft scraper | `scrape_enterprise.py` (20 jobs) | `microsoft/main.py` (full + caching) | **stapply** |
| NVIDIA scraper | `scrape_enterprise.py` (10 jobs) | `nvidia/main.py` (full + caching) | **stapply** |
| Google scraper | `scrape_enterprise.py` (Playwright) | `google/main.py` (Playwright) | **stapply** (parser module) |
| Meta scraper | `scrape_enterprise.py` (Playwright) | `meta/main.py` (Playwright) | Equivalent |
| Uber scraper | `scrape_enterprise.py` | `uber/main.py + api_client.py` | **stapply** (full API client) |
| TikTok scraper | `scrape_enterprise.py` | `tiktok/main.py` | **stapply** (full pagination) |

### 7.4 Features Unique to Each System (NO Overlap)

**Keep from Main Pipeline:**
- Job board adapters (RemoteOK, Remotive, WWR, Dice, HN)
- Aggregator adapters (HiringCafe, Jobright, YC)
- GitHub repo parsers (SimplifyJobs, markdown tables)
- Role keyword filter (142+ patterns)
- US location filter
- Discord bot integration
- BambooHR adapter
- Run history / health logging

**Keep from stapply:**
- SearXNG/SerpAPI company discovery
- JSON caching + scrape cooldowns
- CSV diff tracking
- Salary/experience extraction
- OpenAI embeddings
- Posted-at backfill
- Job lifecycle tracking (is_active)
- FastAPI search API
- Cloudflare R2 upload
- EU internship classifier
- Full enterprise pagination (Amazon/Microsoft/NVIDIA/Uber/TikTok)

---

## 8. Recommendation

### The Ideal Merged Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    UNIFIED JOB PIPELINE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [1] DISCOVERY (from stapply)                                  │
│      SearXNG + SerpAPI → auto-expand company_registry.json     │
│                                                                 │
│  [2] SCRAPING (merged)                                         │
│      ├─ ATS Adapters (main pipeline architecture)              │
│      │   └─ + JSON caching + scrape cooldowns (from stapply)   │
│      │   └─ + retry/backoff (from stapply)                     │
│      │   └─ + proper User-Agent headers                        │
│      ├─ Enterprise APIs (stapply's full pagination)            │
│      ├─ Job Boards (from main pipeline)                        │
│      ├─ Aggregators (from main pipeline)                       │
│      └─ GitHub Repos (from main pipeline)                      │
│                                                                 │
│  [3] FILTERING (from main pipeline)                            │
│      Role filter → US filter → Time filter → Dedup            │
│                                                                 │
│  [4] ENRICHMENT (from stapply)                                 │
│      ├─ Description extraction from cached JSON                │
│      ├─ Salary/experience regex extraction                     │
│      ├─ Posted-at backfill                                     │
│      └─ OpenAI embeddings                                      │
│                                                                 │
│  [5] STORAGE (upgrade path)                                    │
│      SQLite → PostgreSQL (for vectors + scale)                 │
│      + Cloudflare R2 backup                                    │
│                                                                 │
│  [6] DISTRIBUTION (from main pipeline + stapply)               │
│      ├─ Discord bot (main pipeline)                            │
│      ├─ FastAPI search API (stapply)                           │
│      └─ CSV diff exports (stapply)                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Priority Actions

1. **P0 — Fix silent failures**: Add retry + exponential backoff to `ats_adapters.py`. Takes 1 hour.
2. **P0 — Add User-Agent headers**: Every adapter in `ats_adapters.py` should send a realistic browser UA. Takes 30 minutes.
3. **P1 — Adopt stapply's enterprise scrapers**: Replace `scrape_enterprise.py`'s 5-page limits with stapply's full-pagination scrapers. The main pipeline currently captures ~100 enterprise jobs per run; stapply captures 10,000+.
4. **P1 — Port salary/experience extraction**: `extract_salary_experience.py` is self-contained. Wire it into the post-scrape pipeline. Requires storing descriptions first.
5. **P1 — Add description storage**: Add a `description TEXT` column to SQLite and populate it from API responses. This unblocks salary extraction, embeddings, and classification.
6. **P2 — Port SearXNG discovery**: Set up the self-hosted SearXNG instance and run discovery weekly to auto-expand the company registry.
7. **P2 — Add JSON caching**: Implement stapply's `should_scrape_company()` + `save_company_data()` pattern to avoid re-scraping fresh data.
8. **P3 — PostgreSQL migration**: When SQLite limitations become real (concurrent access, vector search needs), migrate to PostgreSQL.

### Key Takeaway

**stapply is a deeper, more feature-rich scraping system** that extracts far more data per job (descriptions, salary, experience, embeddings, lifecycle tracking) and has better engineering practices (caching, retries, checkpoints, diff tracking).

**The main pipeline is a wider, better-orchestrated system** that covers more sources (job boards, aggregators, GitHub repos), has better filtering (role + location), better output (Discord), and a unified run cycle.

The optimal path is to use the main pipeline's architecture as the skeleton (registry → parallel fetch → filter → store → distribute) and graft stapply's capabilities onto it (caching, descriptions, enrichment, discovery). The enterprise scrapers should be wholesale replaced with stapply's versions.
