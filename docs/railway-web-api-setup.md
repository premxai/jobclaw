# Railway Web/API Setup

This is the deployment wiring for JobClaw's public job board.

## Mental Model

JobClaw has three separate moving parts:

1. **API service**: FastAPI app serving `/health`, `/jobs`, `/stats`, and `/stats/runs`.
2. **Database**: Postgres holding scraped companies, jobs, and run history.
3. **Web service**: Next.js app that reads jobs from the API and renders the board.

If Railway only shows **worker** and **web**, that is okay:

- Treat **worker** as the API/backend service. The name is old; the current
  `railway.toml` starts FastAPI with `uvicorn api.main:app`.
- Treat **web** as the Next.js frontend service.
- GitHub Actions own scheduled scraping. You do not need a separate Railway
  scraper service for the current setup.

If the API cannot connect to Postgres, the website cannot show real jobs.
If the website service does not know the API URL, it cannot proxy `/api` to real jobs.
Mock jobs are disabled by default in production.

The API must use the same `DATABASE_URL` that GitHub Actions uses in
`secrets.DATABASE_URL`. GitHub scrapers write jobs there; the API reads jobs
from there. If Railway points to a different Postgres database, the API may boot
but the website will still look empty.

## API Service Variables

Set these on the Railway API/backend service. If your Railway service is named
**worker**, put these variables on **worker**:

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
CORS_ORIGINS=http://localhost:3000,http://localhost:3001,https://YOUR-WEB-DOMAIN.up.railway.app
JOBCLAW_API_KEY=
```

Use the same real Railway Postgres variable reference or Neon connection string
that is configured as the GitHub Actions `DATABASE_URL` secret.
Do not use example values like `user:password@ep-xxx`.

The API start command is defined in `railway.toml`:

```sh
sh -c 'uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}'
```

If Postgres is misconfigured, the API starts in degraded mode so `/health`,
`/health/deep`, and the website `/status` page can explain the database error.

## Web Service Variables

Set these on the Railway web/frontend service. Put these variables on **web**:

```env
JOBCLAW_API_INTERNAL_URL=https://YOUR-API-DOMAIN.up.railway.app
NEXT_PUBLIC_ENABLE_MOCK_JOBS=0
```

The browser calls the web service at same-origin `/api`; Next.js proxies those
requests to `JOBCLAW_API_INTERNAL_URL`. This avoids most CORS confusion.

`NEXT_PUBLIC_ENABLE_MOCK_JOBS=0` prevents the board from silently showing placeholder jobs.

## Custom Domain: norinote.xyz

Use the domain like this:

```text
norinote.xyz      -> Railway web service
www.norinote.xyz  -> Railway web service
api.norinote.xyz  -> Railway worker/API service
```

In Railway:

1. Open **web** service.
2. Add custom domain `www.norinote.xyz`.
3. Add custom domain `norinote.xyz` if Railway gives you an apex/root record.
4. Open **worker** service.
5. Add custom domain `api.norinote.xyz`.

In Spaceship DNS, add the records Railway gives you. Usually this is:

```text
www  CNAME  <railway web target>
api  CNAME  <railway worker/api target>
```

For the root domain `norinote.xyz`, use the exact apex/root record Railway
shows. If Spaceship does not support Railway's required root record cleanly,
use `www.norinote.xyz` as the primary website domain and forward
`norinote.xyz` to `www.norinote.xyz`.

After the custom domains are active, set Railway variables to:

On **worker**:

```env
DATABASE_URL=<same Neon/Postgres URL used by GitHub Actions secrets.DATABASE_URL>
CORS_ORIGINS=https://norinote.xyz,https://www.norinote.xyz,http://localhost:3000,http://localhost:3001
```

On **web**:

```env
JOBCLAW_API_INTERNAL_URL=https://api.norinote.xyz
NEXT_PUBLIC_ENABLE_MOCK_JOBS=0
```

## Validation Order

You can run the full wiring check locally with:

```bash
python scripts/ops/check_web_wiring.py \
  --api-url https://YOUR-API-DOMAIN.up.railway.app \
  --web-url https://YOUR-WEB-DOMAIN.up.railway.app
```

Or run it from GitHub:

1. Open **Actions**.
2. Select **🧭 Web/API Wiring Check**.
3. Click **Run workflow**.
4. Paste the API URL and optional web URL.
5. Read the pass/fail report in the workflow logs.

Validate the API first:

```text
https://YOUR-API-DOMAIN.up.railway.app/health
```

Then validate fresh jobs:

```text
https://YOUR-API-DOMAIN.up.railway.app/jobs?per_page=10&recent_hours=48
```

Then validate the website:

```text
https://YOUR-WEB-DOMAIN.up.railway.app
```

Then validate the website's own proxy path:

```text
https://YOUR-WEB-DOMAIN.up.railway.app/status
```

## What Common Failures Mean

`Invalid value for '--port': '${PORT:-8000}'`:
The start command is not running through `sh -c`. Pull the latest commit and redeploy.

`password authentication failed for user 'user'`:
`DATABASE_URL` is still the fake example value. Replace it with the real Postgres URL.

API `/health` works but `/jobs?recent_hours=48` returns empty:
The API may be connected to the wrong Postgres database, or no scraper has found
fresh jobs in that database. Compare Railway API `DATABASE_URL` with GitHub
Actions `secrets.DATABASE_URL`.

Website says `Connecting to JobClaw API`:
The web service cannot reach the API. Check `JOBCLAW_API_INTERNAL_URL` and API deploy status.

Website `/status` shows a failed API or scraper row:
Use the failed row to decide whether the issue is API boot, database wiring,
fresh job output, or scraper run history.

Website says `No jobs were posted in the last 48 hours`:
The API is reachable, but the DB has no fresh jobs for the board. Run a scraper workflow and recheck `/jobs?recent_hours=48`.
