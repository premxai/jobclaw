# JobClaw

Autonomous multi-threaded job scraping system designed to scale 25,000+ top tech companies safely. Uses decoupled, lightweight micro-scrapers coordinated by an OS-level Task Scheduler, pushing data concurrently to an SQLite database (`jobclaw.db`) with WAL mode enabled.

## Features

- **Decoupled Architecture:** Built around a plugin pattern supporting GreenHouse, Lever, SmartRecruiters, Ashby, Workday, BambooHR, and direct API endpoints (e.g., Apple, Amazon, Meta, TikTok, etc.).
- **Smart Data Layer:** Built-in deduplication mechanisms mapping `internal_hash` constraints in `SQLite` to prevent overlapping rows.
- **Enterprise Stealth:** Leverages `curl_cffi` to mimic Chrome/Safari TLS fingerprints to bypass strict WAF constraints like CloudFlare or generic firewalls.
- **AI Processing Layer:** Supports optional pipeline connections to build embeddings out of job descriptions, detect job matches from resumes, or auto-fetch job salary estimations via semantic matching.
- **Discord Headless Broadcasting:** Polls the database to immediately relay newly uncovered jobs that surpass an internal "quality score" threshold matching certain constraints to your configured Discord Webhooks.
- **FastAPI Backend:** Comes out of the box with a fully fledged, unauthenticated HTTP JSON API designed for frontend connectivity out-of-the-box (`http://localhost:8000`).
- **Realtime Pipeline State:** A NextJS-powered frontend UI connects directly to JobClaw's internal states parsing active logs.
- **Resiliency & Auto-Healing:** Implements `ScrapeTimer` monitoring and exponential back-off circuit breaking across its ATS adapter classes avoiding IP bans automatically.

## Micro-Scraper Architecture

```
jobclaw/
├── api/                             # FastAPI application
├── config/                          
│   └── company_registry.json        # Raw registry input for seeding/validation
├── data/
│   └── jobclaw.db                   # SQLite WAL database for high-concurrency 
├── scripts/
│   ├── database/
│   │   ├── init_db.py               # Main DB setup
│   │   └── db_utils.py              # Common injection & deduplication utils
│   ├── ingestion/
│   │   ├── ats_adapters.py          # Unified Interface returning `NormalizedJob`
│   │   ├── parallel_ingestor.py     # Task orchestration handler using aiohttp
│   │   ├── scrape_enterprise.py     # Micro-scraper: Apple/Microsoft/Meta (Bot Bypass)
│   │   └── run_all_scrapers.py      # Entry-point for orchestrator execution
│   ├── discord_push.py              # Headless Broadcaster (runs as daemon)
│   └── ai/                          # AI Job embedding/matching logic
└── web/                             # Next.js UI Application
```

### 1. Data Ingestion Lifecycle
1. Unique scrapers wake up on independent schedules triggered by GitHub Actions or OS-level Schedulers (ATS every 4 hours, Aggregators every hour).
2. They do not block each other nor do they conflict; they process their tasks leveraging async event loops bounded by Semaphores enforcing max concurrency and host limitations.
3. Each extracts, normalizes, applies role/time filters matching specific tech categories (AI/ML, SWE, Product, Data).
4. Each uses `INSERT OR IGNORE` to atomically add jobs with an `internal_hash` to the SQLite/PostgreSQL Database tracking its individual status.

### 2. Discord Broadcasting Layer
1. `discord_push.py` is entirely separated from the ingestion loops.
2. It polls the database every 15 minutes checking for `status = 'unposted'`.
3. Jobs are flushed to Discord gracefully via JSON webhooks and marked as `posted` instantly.

---

## Execution Instructions

### Prerequisites
- **Python 3.12+**: Built around the latest Python async capabilities (`pip install -r requirements.txt`)

### 1. Configure the Environment
Create a `.env` file in the root directory:
```env
# Production PostgreSQL (Defaults to local SQLite WAL mode if omitted)
DATABASE_URL="postgres://user:pass@host/db"

# Discord Webhooks targeting specific categories
DISCORD_WEBHOOK_SWE="https://discord.com/api/webhooks/..."
DISCORD_WEBHOOK_AI="https://discord.com/api/webhooks/..."
```

### 2. Initialize Database
```bash
python scripts/database/init_db.py
python scripts/database/seed_companies.py
```

### 3. Validate ATS Targets
Smoke-validation records target health in the canonical `companies` table. Bad
targets are quarantined (`is_dead = 1`) after repeated failures; raw registry
entries are not deleted.
```bash
python scripts/ingestion/validate_targets.py --limit 500
```

### 4. Start the Background Scrapers (Production)
Jobs can be executed ad-hoc based on execution tier types. ATS scrapers read due
targets from Postgres `companies` through the adaptive control plane. The
default `JOBCLAW_QUEUE_MODE=active` claims targets with short DB leases, applies
per-platform budgets, and checkpoints target health after each scrape.
`JOBCLAW_ATS_TARGET_LIMIT` caps how many targets one run can claim before
platform budgets defer the rest. Medium runs default to
`JOBCLAW_MEDIUM_TARGET_LIMIT=800` and `JOBCLAW_WORKDAY_SHARDS=16` so
Workday-heavy batches stay small and reliable.
```bash
# Light payload - 1 minute runs covering RSS + Boards
python scripts/ingestion/run_all_scrapers.py --tier fast

# Heavy payload - due slower ATS targets + Enterprise APIs
python scripts/ingestion/run_all_scrapers.py --tier medium
```

Production scheduling is split by workload. GitHub Actions owns bulk scraping so
larger ATS runs use fresh hosted runners and visible per-run logs. Railway owns
the always-on control-plane tasks that benefit from a persistent process:

| Owner | Task | Schedule |
| --- | --- |
| Railway worker | Hot scraper | Every 15 minutes |
| Railway worker | Discord push | `:05`, `:20`, `:35`, `:50` UTC |
| Railway worker | Target validation | Every 6 hours at `:40` UTC |
| GitHub Actions | Fast tier | Hourly at `:03` UTC |
| GitHub Actions | Medium tier | Hourly at `:33` UTC |
| GitHub Actions | Registry expander | Daily at `07:17` UTC |
| GitHub Actions | Deep tier | Daily at `08:17` UTC |

The Railway worker defaults to `JOBCLAW_RAILWAY_ENABLE_FAST=0`,
`JOBCLAW_RAILWAY_ENABLE_MEDIUM=0`, and `JOBCLAW_RAILWAY_ENABLE_DEEP=0` so it
does not duplicate GitHub's bulk ATS runs. If GitHub Actions is unavailable, set
`JOBCLAW_RAILWAY_BULK_FALLBACK=1` or enable an individual Railway bulk task to
temporarily move scraping back to Railway. Postgres queue leases still prevent
duplicate target claims if both environments overlap during an incident.

Discord posting is live when `JOBCLAW_DISCORD_DRY_RUN=0`, with
`JOBCLAW_DISCORD_STRICT_QUALITY=1` and `JOBCLAW_DIRECT_SOURCE_ONLY=1` rejecting
generic aggregator/search/salary pages before any card is sent.

### 5. Start the Application UI Layer
In a background terminal, spin up the HTTP Server:
```bash
uvicorn api.main:app --reload --port 8000
```
Then spin up the Web Application:
```bash
cd web && npm install && npm run build
```
