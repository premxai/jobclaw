# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**JobClaw** is an autonomous job scraping and alerting system. It aggregates tech job postings from 27,922 companies across 8 ATS platforms (Greenhouse, Lever, Ashby, Workday, etc.), job boards, and enterprise sites, then filters and broadcasts to Discord channels by role category.

## Commands

### Python Setup
```bash
pip install -r requirements.txt
python scripts/database/init_db.py   # Initialize DB schema
```

### Linting (Ruff — 120 char lines, Python 3.10 target)
```bash
ruff check scripts/
ruff format scripts/
```

### Run Scrapers
```bash
python scripts/ingestion/run_all_scrapers.py --tier fast    # RSS + GitHub (~2 min)
python scripts/ingestion/run_all_scrapers.py --tier medium  # + Enterprise + 1 ATS shard
python scripts/ingestion/run_all_scrapers.py --tier deep    # Everything including Brave/OpenClaw
```

### Discord Push
```bash
python scripts/discord_push.py   # Post unposted jobs to Discord channels
```

### API Server
```bash
uvicorn api.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

### Web Frontend
```bash
cd web && npm install && npm run dev   # http://localhost:3000
```

### Docker (full stack)
```bash
docker compose up -d   # services: api (8000), postgres, redis, prometheus, grafana
```

### Environment Setup
```bash
cp .env.example .env   # then fill in secrets
```
Key env vars: `DATABASE_URL` (Neon PostgreSQL URL; defaults to SQLite if unset), `DISCORD_WEBHOOK_AI/SWE/DATA/NEWGRAD/PRODUCT/RESEARCH` (per-category webhook URLs; at least one required), `BRAVE_SEARCH_API_KEY`, `JOBCLAW_API_KEY` (leave blank for dev).

### CI Validation (mirrors deploy.yml checks)
```bash
ruff check scripts/ api/ && ruff format --check scripts/ api/
python -c "from api.main import app; from scripts.database.db_utils import get_connection"
```
No formal test suite — `tests/` directory doesn't exist. The 12 `test_*.py` files in repo root are ad-hoc exploration scripts, not a test suite.

## Architecture

### Data Flow
```
company_registry.json → ATS/RSS/Enterprise scrapers
    → NormalizedJob dataclass
    → role_filter() + us_filter()
    → SHA256 dedup (internal_hash unique constraint)
    → SQLite INSERT (status='unposted')
    → discord_push.py (every 15 min via GitHub Actions)
    → Discord channels by category
    → status='posted'
```

### Scraping Tiers & GitHub Actions Schedule
| Workflow | Trigger | Sources |
|---|---|---|
| `scrape_hot.yml` | Every 5 min | `hot_companies.json` only |
| `scrape_fast.yml` | Hourly | RSS feeds + GitHub boards |
| `scrape_medium.yml` | Every 4 hrs | + Enterprise + 1 ATS shard |
| `scrape_deep.yml` | Daily 11 PM | Everything + Brave + OpenClaw |
| `discord_push.yml` | Every 15 min | Posts unposted jobs |

### Shard Rotation
The 27,922-company registry is split into 4 shards. Each run processes 1 shard; `get_next_shard_from_db()` persists rotation state in the DB so ephemeral GitHub Actions runners maintain continuity. Do not break this — it guarantees 100% company coverage across runs.

### Anti-Bot Stack
- **curl_cffi**: TLS fingerprint impersonation (Chrome/Safari/Edge) — bypasses Cloudflare/WAF
- **UA rotation**: 50+ user agents per request
- **Rate limiting**: Per-host bounded worker pools (Workday: 2 workers, Greenhouse: 5 workers)
- **Circuit breaker**: Skip platform after 15 consecutive failures
- **TLS connection limit**: Capped at 15 concurrent to prevent exhaustion

### Deduplication (Two Layers)
1. `internal_hash = f"{source_ats}::{company}::{job_id}"` — unique DB constraint
2. `data/posted_hashes.json` — file-based dedup for Discord, committed by CI after each push

### Quality Scoring (0–100)
Jobs below score 20 are not posted to Discord. Scores come from: hot company bonus (+25), salary transparency (+15), freshness (+10), description depth, role match weight, seniority penalty (−30 for Director/VP/C-level).

### Database
- **SQLite** (default, WAL mode): `data/jobclaw.db`
- **PostgreSQL** (production): set `DATABASE_URL` env var
- Backend is transparent — same schema, `db_utils.py` handles both

### Role Categories (7)
Defined in `scripts/ingestion/role_filter.py`: AI/ML, SWE, Data, New Grad, Product, Research, Design. 142+ keywords. Jobs not matching any category are dropped.

### Logging
Dual-mode structured logging via `scripts/utils/logger.py`:
- `logs/jobclaw.jsonl` — machine-parseable JSON (for log aggregators)
- `logs/jobclaw.log` — human-readable combined log
- Legacy `_log(msg, level, tag)` pattern used throughout; new code can use structured kwargs: `log.info("msg", companies=500, shard=2)`
- `ScrapeTimer` context manager for automatic operation timing

## Key Files

| File | Purpose |
|---|---|
| `scripts/ingestion/run_all_scrapers.py` | Scraper orchestrator — shard rotation, tier logic |
| `scripts/ingestion/ats_adapters.py` | Per-platform API adapters returning `NormalizedJob` |
| `scripts/ingestion/role_filter.py` | Keyword-based role classification |
| `scripts/database/db_utils.py` | Job insert, dedup, quality scoring, shard rotation |
| `scripts/discord_push.py` | Query unposted → Discord embeds → mark posted |
| `scripts/utils/http_client.py` | `RateLimiter`, `create_session`, curl_cffi TLS |
| `scripts/utils/logger.py` | Structured JSON + console logging, `ScrapeTimer` |
| `scripts/utils/retry_queue.py` | Failed job retry management across runs |
| `scripts/ai/` | Embeddings, semantic dedup, salary estimation, job matching |
| `scripts/discovery/` | Company career page discovery crawlers |
| `config/company_registry.json` | 27,922 companies with ATS platform + slug |
| `config/hot_companies.json` | Fast-track companies (scraped every 5 min) |
| `api/main.py` | FastAPI server — REST endpoints + WebSocket |

## Adding a New ATS Scraper
1. Add adapter to `scripts/ingestion/ats_adapters.py` returning list of `NormalizedJob`
2. Register companies in `config/company_registry.json` with `"ats": "<platform>"`
3. The orchestrator will pick them up automatically via shard rotation

## Ruff Ignore Rules (pyproject.toml)
- `E402`: Module-level imports after `sys.path.insert()` — intentional project root setup pattern
- `SIM105`: `try/except/pass` — accepted pattern
- `UP045/UP006/UP007/UP035`: Python 3.9 compatibility aliases kept for 3.10 target
