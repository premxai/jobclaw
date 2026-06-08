# Railway Web/API Setup

This is the deployment wiring for JobClaw's public job board.

## Mental Model

JobClaw has three separate moving parts:

1. **API service**: FastAPI app serving `/health`, `/jobs`, `/stats`, and `/stats/runs`.
2. **Database**: Postgres holding scraped companies, jobs, and run history.
3. **Web service**: Next.js app that reads jobs from the API and renders the board.

If the API cannot connect to Postgres, the website cannot show real jobs.
If the website does not know the API URL, it cannot show real jobs.
Mock jobs are disabled by default in production.

## API Service Variables

Set these on the Railway API/backend service:

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
CORS_ORIGINS=http://localhost:3000,http://localhost:3001,https://YOUR-WEB-DOMAIN.up.railway.app
JOBCLAW_API_KEY=
```

Use the real Railway Postgres variable reference or the real Neon connection string.
Do not use example values like `user:password@ep-xxx`.

The API start command is defined in `railway.toml`:

```sh
sh -c 'uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}'
```

## Web Service Variables

Set these on the Railway web/frontend service:

```env
NEXT_PUBLIC_API_URL=https://YOUR-API-DOMAIN.up.railway.app
JOBCLAW_API_INTERNAL_URL=https://YOUR-API-DOMAIN.up.railway.app
NEXT_PUBLIC_ENABLE_MOCK_JOBS=0
```

`NEXT_PUBLIC_ENABLE_MOCK_JOBS=0` prevents the board from silently showing placeholder jobs.

## Validation Order

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

## What Common Failures Mean

`Invalid value for '--port': '${PORT:-8000}'`:
The start command is not running through `sh -c`. Pull the latest commit and redeploy.

`password authentication failed for user 'user'`:
`DATABASE_URL` is still the fake example value. Replace it with the real Postgres URL.

Website says `Connecting to JobClaw API`:
The web service cannot reach the API. Check `NEXT_PUBLIC_API_URL`, `JOBCLAW_API_INTERNAL_URL`, and API deploy status.

Website says `No jobs were posted in the last 48 hours`:
The API is reachable, but the DB has no fresh jobs for the board. Run a scraper workflow and recheck `/jobs?recent_hours=48`.

