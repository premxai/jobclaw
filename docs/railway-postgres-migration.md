# Migrating JobClaw's database to Railway Postgres

Why: Neon's free tier has a hard **data-transfer cap** (5 GB/mo) that suspends the
project when hit. Railway bills by **usage** (no flat transfer wall) and, crucially,
traffic between services on Railway's **private network is not metered as egress** —
so the API ↔ DB read path (the website polling `/jobs`) stops costing transfer.

No application code changes are needed — `db_utils.py` already speaks Postgres via
`DATABASE_URL`. This is a provisioning + env-var + re-seed task.

> Cost note: Railway has no perpetual free tier — a one-time ~$5 trial credit, then
> the Hobby plan ($5/mo incl. $5 usage). A small always-on Postgres is ~$3–7/mo of
> usage, so budget ~$5–10/mo for the whole stack.

## You do NOT need to rescue Neon's data
The company registry (`config/company_registry.json`) and Discord dedup
(`data/posted_hashes.json`) live in the repo, and job rows are disposable (the board
only shows the last 48h). So a clean re-seed fully restores the system; scrapers refill
jobs within ~an hour and `posted_hashes.json` prevents Discord re-posts. (Neon is
suspended anyway, so `pg_dump` from it isn't an option right now.)

## Steps

### 1. Provision Postgres on Railway
Railway project → **+ New → Database → PostgreSQL**. Wait for it to deploy.

### 2. Point the API/worker service at the INTERNAL URL
In the Postgres service's **Variables** tab you'll see connection strings. Railway
exposes both a private (internal) and a public URL — names vary, commonly:
- internal: `DATABASE_URL` (host ends in `.railway.internal`)
- public:   `DATABASE_PUBLIC_URL` (a `*.proxy.rlwy.net` TCP proxy host)

On your **API/`worker`** service → Variables, set:
```
DATABASE_URL = ${{Postgres.DATABASE_URL}}     # internal — free, not metered as egress
```
(Use the Railway variable-reference syntax so it tracks the DB service.)

### 3. Point GitHub Actions at the PUBLIC URL
The scrapers run outside Railway, so they need the public endpoint. Copy the value of
the Postgres service's **public** URL and set it as the repo secret:
```
GitHub repo → Settings → Secrets and variables → Actions → DATABASE_URL = <DATABASE_PUBLIC_URL value>
```

### 4. Initialize schema + seed companies
Run once against the new DB (locally, pointing at the public URL — quoting matters):
```bash
export DATABASE_URL='<DATABASE_PUBLIC_URL value>'
python scripts/database/init_db.py
python scripts/database/seed_companies.py     # also quarantines Gem
unset DATABASE_URL
```
(Or run them as a Railway one-off command on the API service, where `DATABASE_URL` is
already the internal URL.)

### 5. Verify
```bash
# API health (deep = checks the DB)
curl -s https://api.norinote.xyz/health/deep | python3 -m json.tool
# Should show the DB connected; /jobs will be sparse until scrapers run.
curl -s -o /dev/null -w "%{http_code}\n" https://api.norinote.xyz/jobs   # 200
```
Trigger a scraper to refill (either wait for the next cron, or the GitHub Actions
"workflow_dispatch" on Fast Tier), then confirm jobs appear on the site.

### 6. Decommission Neon
Once the site shows jobs from Railway Postgres, remove the Neon `DATABASE_URL` and (if
desired) delete the Neon project. Keep it until you've confirmed Railway is healthy.

## Keeping costs/egress low (already in the codebase)
- `JOBCLAW_READ_CACHE_TTL=300` — API caches `/jobs|/stats|/companies` reads for 5 min.
- The web board polls every 5 min (was 60s).
- These cut DB queries ~5–10×, which lowers Railway compute too. Leave them on.

## If Railway usage still climbs
Move scraping onto the Railway worker (`scripts/worker/standalone_worker.py`, set the
`JOBCLAW_RAILWAY_ENABLE_*` flags) so scraper↔DB is also internal — then *no* DB traffic
is metered at all. Trade-off: uses Railway compute and drops GitHub Actions' free
runners/logs. Only needed if egress remains a problem after the steps above.
