# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**JobClaw** is an autonomous job scraping and alerting system. It aggregates tech job postings from ~34,000 company targets across ATS platforms (by volume: Workday, Workable, Greenhouse, Lever, Ashby, Rippling, SmartRecruiters, Oracle Recruiting Cloud, BambooHR — Gem was purged as permanently dead), job boards, and enterprise sites, then filters and broadcasts to Discord channels by role category. Adapters live in `scripts/ingestion/ats_adapters.py` and are keyed in the `ADAPTERS` registry.

## Commands

### Python Setup
```bash
pip install -r requirements.txt
python scripts/database/init_db.py   # Initialize DB schema
python scripts/database/seed_companies.py  # Seed canonical companies table from registry
python scripts/ingestion/validate_targets.py --limit 500  # Smoke-check slugs and quarantine bad targets
```

### Linting (Ruff — 120 char lines, Python 3.10 target)
CI lints the **whole repo**, not just `scripts/`. Config is duplicated in both `ruff.toml` and `pyproject.toml` `[tool.ruff]` — keep them in sync if you change ignore rules.
```bash
ruff check .          # lint everything (matches CI)
ruff format --check .  # format check (matches CI); drop --check to apply
```
Note the Python version split: ruff targets `py310` (3.9 aliases kept); workflows are mixed — fast/medium/deep/workday-sweep run 3.10, hot/controller/discord/validate/expand/db-maintenance run 3.11 — and the CI lint/test job (`deploy.yml`) runs 3.12. README says 3.12+ for local dev. Code must stay 3.10-compatible.

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
Key env vars:
- `DATABASE_URL` — Neon/Postgres URL; defaults to SQLite (`data/jobclaw.db`, WAL) if unset
- `DISCORD_WEBHOOK_AI/SWE/DATA/NEWGRAD/PRODUCT/RESEARCH` — per-category webhooks; at least one required for live posting
- `JOBCLAW_DISCORD_DRY_RUN=1` — default safety mode (workflows set `0` for live posting)
- `JOBCLAW_DISCORD_STRICT_QUALITY=1` + `JOBCLAW_DIRECT_SOURCE_ONLY=1` — reject generic aggregator/search/salary pages before any card is sent
- `BRAVE_SEARCH_API_KEY`, `JOBCLAW_BRAVE_ENRICHMENT_ONLY=1`, `JOBCLAW_API_KEY` (leave blank for dev)
- Queue/throttle (active mode): `JOBCLAW_QUEUE_MODE`, `JOBCLAW_QUEUE_LEASE_SECONDS`, `JOBCLAW_ATS_TARGET_LIMIT`, `JOBCLAW_MEDIUM_TARGET_LIMIT`, `JOBCLAW_WORKDAY_SHARDS`, `JOBCLAW_PLATFORM_CLAIM_MULTIPLIER`
- Railway worker fallback (all default off): `JOBCLAW_RAILWAY_ENABLE_{HOT,FAST,MEDIUM,DEEP,DISCORD,VALIDATION}`, `JOBCLAW_RAILWAY_BULK_FALLBACK`, `JOBCLAW_SCHEDULER_TIMEZONE` (default `America/New_York`)

### Tests
`tests/` holds the real (pytest) suite — scraper control plane, scraper quality, scheduling, API auth, and Twitter digest tests. CI runs them with `|| true`, so they are non-blocking today.
```bash
pytest tests/ -v                          # full suite
pytest tests/test_scraper_quality.py -v   # single file
pytest tests/test_scraper_quality.py::test_name -v   # single test
```
The ~12 `test_*.py` files in the **repo root** (and `scripts/test_*.py`) are ad-hoc exploration scripts (e.g. probing Meta/Google endpoints), NOT part of the pytest suite — ruff relaxes lint rules for them via `per-file-ignores`.

### CI Validation (mirrors deploy.yml)
```bash
ruff check . && ruff format --check .                              # lint + format (Python 3.12 in CI)
pytest tests/ -v --tb=short                                        # non-blocking tests
python -c "from api.main import app; print('Routes:', len(app.routes))"   # API import smoke
python -c "from scripts.database.db_utils import get_connection; print('DB OK')"  # DB import smoke
```

## Architecture

### Data Flow
```
company_registry.json → seed_companies.py → companies DB table → ATS/RSS/Enterprise scrapers
    → NormalizedJob dataclass
    → role_filter() + us_filter()
    → SHA256 dedup (internal_hash unique constraint)
    → SQLite INSERT (status='unposted')
    → discord_push.py (every 15 min via GitHub Actions)
    → Discord dry-run/live channels by category
    → status='posted'
```

### Scraping Tiers & Scheduling
**Production scheduling is owned by GitHub Actions cron workflows** (`.github/workflows/scrape_*.yml`) — each run gets a fresh hosted runner and centralized logs. The Railway worker (`scripts/worker/standalone_worker.py`, an APScheduler in-process scheduler) is a **fallback that is disabled by default**: all its `JOBCLAW_RAILWAY_ENABLE_*` flags default to `0` (except `discord_push`, which enables itself when Discord is configured). Set `JOBCLAW_RAILWAY_BULK_FALLBACK=1` to turn on the fast/medium/deep tiers there if Actions is down. Postgres queue leases prevent duplicate target claims if both environments overlap.

> Note: `requirements.txt` comments call APScheduler "replaces GitHub Actions crons" — that comment is stale; Actions is the current owner.

GitHub Actions workflows (cron is UTC):

| Workflow file | Schedule (UTC) | Sources |
|---|---|---|
| `scrape_controller.yml` | Every 15 min | **DB-gated catch-up safety net** — runs only overdue tiers (hot→fast→medium→Discord) |
| `scrape_hot.yml` | Every 15 min (`:07,:22,:37,:52`) | `hot_companies.json` only |
| `scrape_fast.yml` | Hourly (`:03`) | RSS + GitHub boards + due Greenhouse/Lever/Ashby targets |
| `scrape_medium.yml` | Hourly (`:33`) | Enterprise + due slower ATS targets |
| `discord_push.yml` | Every 15 min (`:14,:29,:44,:59`) | Posts unposted jobs (dry-run/live) |
| `validate_targets.yml` | Every 6 hours (`:41`) | Live slug smoke validation + quarantine |
| `db_maintenance.yml` | Every 6 hours (`:08`) | Retention/compaction via `scripts/ops/db_maintenance.py` (avoids Neon quota blowups) |
| `expand_registry.yml` | Daily (`11:17`) | Registry expansion/discovery |
| `scrape_deep.yml` | Daily (`12:17`) | Everything + Brave + AI pipeline |
| `scrape_workday_sweep.yml` | Weekly (Sun `09:23`) | Long-tail Workday sweep, gated by `workday_sweep_guard.py`; manual `force` input bypasses guardrails |
| `twitter_push.yml` | **Paused** (manual only) | Twitter/X digest of new roles; dry-run unless `JOBCLAW_TWITTER_DRY_RUN=0` + `X_*` secrets |
| `check_web_wiring.yml` | Manual | Diagnose deployed web↔API wiring |
| `deploy.yml` | push/PR to `main` | CI: ruff lint/format + pytest + import smoke |

The **controller** is the canonical schedule safety net: GitHub cron can delay or drop individual scheduled workflows, so `scrape_controller.yml` wakes every 15 min, checks DB reachability (`scripts/ops/github_db_preflight.py`), then runs `scripts/ops/scrape_schedule_decider.py` to execute only the tiers whose last successful run is older than its SLO interval (hot 20 min, fast 75 min, medium 90 min, Discord 15 min). The individual tier workflows remain as manual/backup paths. All DB-backed scheduled workflows use the same preflight to skip cleanly (instead of failing noisily) when the production DB is down.

### Due-Target Scheduling (active queue mode)
The raw registry is seeded into the canonical `companies` table and deduped by `(ats_type, slug)`. With `JOBCLAW_QUEUE_MODE=active` (the production default in the workflows), runtime scrapers **claim** non-quarantined DB targets with short DB leases (`JOBCLAW_QUEUE_LEASE_SECONDS`), ordered by `priority_score` where `next_scrape_at` is due, then checkpoint target health after each scrape. Key throttles:
- `JOBCLAW_ATS_TARGET_LIMIT` — caps targets claimed per run before per-platform budgets defer the rest
- `JOBCLAW_MEDIUM_TARGET_LIMIT` (default 800) and `JOBCLAW_WORKDAY_SHARDS` (default 16) keep Workday-heavy medium runs small
- `JOBCLAW_PLATFORM_CLAIM_MULTIPLIER` (default 4) — claims per-platform first so one high-score ATS can't crowd out the batch

Shard arguments (`--shard`) are retained for manual compatibility but the production path is due-target claiming.

### Anti-Bot Stack
- **curl_cffi**: TLS fingerprint impersonation (Chrome/Safari/Edge) — bypasses Cloudflare/WAF
- **UA rotation**: 50+ user agents per request
- **Rate limiting**: Per-host bounded worker pools (Workday/Workable/Rippling: 1 worker, Greenhouse/Lever/Ashby: 4 workers)
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
| `config/company_registry.json` | Raw registry input with ATS platform + slug |
| `scripts/database/seed_companies.py` | Canonicalizes registry entries into `companies` |
| `scripts/ingestion/validate_targets.py` | Live slug smoke validation + quarantine |
| `config/hot_companies.json` | Fast-track companies (hot tier, every 15 min) |
| `api/main.py` | FastAPI server — REST endpoints + WebSocket `/ws/jobs` + application-tracker CRUD |
| `api/database.py` / `api/auth.py` / `api/models.py` | API DB access layer, API-key auth, Pydantic models |
| `scripts/worker/standalone_worker.py` | APScheduler in-process scheduler (Railway fallback, default off) |
| `scripts/ops/scrape_schedule_decider.py` | Controller brain — reads DB, decides which tiers are overdue |
| `scripts/ops/github_db_preflight.py` | Writes `db_ok` to `GITHUB_OUTPUT` so workflows skip cleanly when DB is down |
| `scripts/ops/db_maintenance.py` | Retention/compaction — trims descriptions, prunes stale rows and run records |
| `scripts/ops/workday_sweep_guard.py` | Gates the weekly Workday sweep on DB capacity + scraper health |
| `scripts/ops/check_web_wiring.py` | Diagnose deployed web↔API wiring; `scraper_control_report.py` health report |
| `scripts/twitter_push.py` | Twitter/X digest poster (paused; dry-run by default, own tweeted-hash dedup file) |

## Adding a New ATS Scraper
1. Add adapter to `scripts/ingestion/ats_adapters.py` returning list of `NormalizedJob`
2. Register companies in `config/company_registry.json` with `"ats": "<platform>"`
3. The orchestrator will pick them up automatically when their `next_scrape_at` is due

## Ruff Ignore Rules (defined in BOTH `ruff.toml` and `pyproject.toml` — keep in sync)
- `E402`: Module-level imports after `sys.path.insert()` — intentional project root setup pattern
- `SIM105`: `try/except/pass` — accepted pattern in scraper error handling
- `SIM117` / `SIM102`: nested `with` / nested `if` — kept when logically clearer than combining
- `UP045/UP006/UP007/UP035`: `Optional[X]`, `List[X]` etc. — Python 3.9 compatibility aliases kept for 3.10 target
- `per-file-ignores`: root `test_*.py` and `scripts/test_*.py` relax `E402/F401/I001` (ad-hoc scripts)
