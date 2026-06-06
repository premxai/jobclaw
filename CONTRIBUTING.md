# Contributing to JobClaw

Welcome to JobClaw! We're excited to have you contribute. This document outlines the architecture, setup instructions, and guidelines for adding new features.

## Architecture

JobClaw is an autonomous job scraping and alerting system. It operates via decoupled, lightweight micro-scrapers coordinated by an OS-level Task Scheduler, pushing data concurrently to an SQLite (or PostgreSQL) database.

### Scraping Sharding
To handle 27,000+ companies safely across ephemeral runners (like GitHub Actions), the system shards the load.
- **Tiers**: Fast (RSS/Job Boards), Medium (Enterprise + 1 ATS Shard), Deep (All Shards + Search API).
- **Shard Rotation**: The database keeps track of which shard (0-3) was run last, and picks the next one automatically. This guarantees 100% coverage over multiple runs without hitting time limits.

### Anti-Bot Measures
- **curl_cffi**: We use `curl_cffi` for TLS fingerprint impersonation to bypass Cloudflare/WAF.
- **UA Rotation**: A pool of real browser User-Agents is injected into all requests.
- **Retry/Backoff**: `fetch_with_retry` automatically handles 429/500/502/503 errors.

## Adding a New ATS Scraper

1. **Add the Adapter**: Create a new class in `scripts/ingestion/ats_adapters.py`. It should:
   - Accept a `aiohttp.ClientSession` or `CffiAsyncSession`, a `slug`, `company`, and `rate_limiter`.
   - Call `fetch_with_retry` for the API endpoint.
   - Return a list of `NormalizedJob` dataclasses.
2. **Register the ATS**: Add your ATS name to the `company_registry.json` under `"ats": "<platform>"`.
3. **Automatic Orchestration**: The sharding system will automatically pick up the new companies and run your adapter.

## Local Development

We provide a complete Docker Compose setup for local development.

```bash
# Start PostgreSQL, Redis, API, Worker, and Next.js Frontend
docker compose up -d
```

- API Server: http://localhost:8000
- Frontend: http://localhost:3000

Alternatively, run locally with Python and Node:
```bash
# Setup Python
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python scripts/database/init_db.py

# Setup Frontend
cd web && npm install && npm run dev
```

## Testing

Tests are located in the `tests/` directory. Run them using pytest:
```bash
pytest
```
Note: Currently tests are ad-hoc scripts we are migrating into a formal suite. Contributions to tests are highly welcome!
