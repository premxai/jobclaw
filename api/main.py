"""
JobClaw REST API — v1

FastAPI backend serving job data from the SQLite database.
Provides paginated job listings, company views, stats, and scraper health.

Run:  uvicorn api.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api.models import (
    JobResponse, JobListResponse, CompanyResponse,
    StatsOverview, ScraperRunResponse, HealthResponse,
)
from api.database import (
    get_jobs, get_job_by_hash, get_companies,
    get_stats, get_scraper_runs, get_db,
)


# ═══════════════════════════════════════════════════════════════════════
# APP LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hooks."""
    # Validate DB exists
    from api.database import DB_PATH
    if not DB_PATH.exists():
        print(f"⚠️  Database not found at {DB_PATH}")
        print("   Run the scraper first: python scripts/ingestion/run_all_scrapers.py")
    else:
        conn = get_db()
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        conn.close()
        print(f"✅ Database connected: {total} jobs in JobClaw")
    yield


app = FastAPI(
    title="JobClaw API",
    version="4.0.0",
    description="Real-time job board aggregation API — scrapes 10,500+ company career pages via 8 ATS platforms.",
    lifespan=lifespan,
)

# CORS — allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Key auth — disabled if JOBCLAW_API_KEY not set
from api.auth import APIKeyMiddleware
app.add_middleware(APIKeyMiddleware)


# ═══════════════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════════════

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """API health check with database status."""
    try:
        conn = get_db()
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        conn.close()
        return HealthResponse(status="ok", database="connected", total_jobs=total)
    except Exception as e:
        return HealthResponse(status="degraded", database=str(e), total_jobs=0)


# ═══════════════════════════════════════════════════════════════════════
# JOBS
# ═══════════════════════════════════════════════════════════════════════

@app.get("/jobs", response_model=JobListResponse, tags=["Jobs"])
async def list_jobs(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Results per page"),
    company: Optional[str] = Query(None, description="Filter by company name"),
    ats: Optional[str] = Query(None, description="Filter by ATS platform"),
    keyword: Optional[str] = Query(None, description="Filter by keyword category"),
    search: Optional[str] = Query(None, description="Full-text search in title/company/description"),
    active: bool = Query(True, description="Only active (non-filled) jobs"),
):
    """
    List jobs with pagination and filtering.
    
    Supports filtering by company, ATS platform, keyword category, and full-text search.
    Results are ordered by most recently discovered first.
    """
    jobs, total = get_jobs(
        page=page,
        per_page=per_page,
        company=company,
        ats=ats,
        keyword=keyword,
        active_only=active,
        search=search,
    )
    return JobListResponse(
        jobs=[JobResponse(**j) for j in jobs],
        total=total,
        page=page,
        per_page=per_page,
        has_more=(page * per_page < total),
    )


@app.get("/jobs/{internal_hash}", response_model=JobResponse, tags=["Jobs"])
async def get_job(internal_hash: str):
    """Get a single job by its internal hash ID."""
    job = get_job_by_hash(internal_hash)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**job)


@app.get("/jobs/search/{query}", response_model=JobListResponse, tags=["Jobs"])
async def search_jobs(
    query: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Search jobs by title, company, or description."""
    jobs, total = get_jobs(page=page, per_page=per_page, search=query)
    return JobListResponse(
        jobs=[JobResponse(**j) for j in jobs],
        total=total,
        page=page,
        per_page=per_page,
        has_more=(page * per_page < total),
    )


# ═══════════════════════════════════════════════════════════════════════
# COMPANIES
# ═══════════════════════════════════════════════════════════════════════

@app.get("/companies", response_model=list[CompanyResponse], tags=["Companies"])
async def list_companies(
    ats: Optional[str] = Query(None, description="Filter by ATS platform"),
):
    """
    List all companies with their active job counts.
    Grouped by company + ATS platform.
    """
    companies = get_companies(ats=ats)
    return [CompanyResponse(**c) for c in companies]


@app.get("/companies/{company_name}/jobs", response_model=JobListResponse, tags=["Companies"])
async def company_jobs(
    company_name: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Get all active jobs for a specific company."""
    jobs, total = get_jobs(page=page, per_page=per_page, company=company_name)
    return JobListResponse(
        jobs=[JobResponse(**j) for j in jobs],
        total=total,
        page=page,
        per_page=per_page,
        has_more=(page * per_page < total),
    )


# ═══════════════════════════════════════════════════════════════════════
# STATS
# ═══════════════════════════════════════════════════════════════════════

@app.get("/stats", response_model=StatsOverview, tags=["Stats"])
async def stats_overview():
    """System-wide statistics: job counts, platform breakdown, recent trends."""
    return StatsOverview(**get_stats())


@app.get("/stats/runs", response_model=list[ScraperRunResponse], tags=["Stats"])
async def scraper_runs(
    limit: int = Query(20, ge=1, le=100, description="Number of recent runs to show"),
):
    """Recent scraper run history with performance metrics."""
    runs = get_scraper_runs(limit=limit)
    return [ScraperRunResponse(**r) for r in runs]


# ═══════════════════════════════════════════════════════════════════════
# SCRAPER CONTROL
# ═══════════════════════════════════════════════════════════════════════

@app.post("/scraper/trigger", tags=["Scraper"])
async def trigger_scraper(
    tier: str = Query("fast", description="Tier: fast/medium/heavy/deep"),
):
    """
    Manually trigger a scraper run in the background.
    Returns immediately — check /stats/runs for results.
    """
    import subprocess
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "ingestion" / "run_all_scrapers.py"),
        "--tier", tier,
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"status": "started", "tier": tier, "pid": proc.pid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════
# WEBSOCKET — real-time job stream
# ═══════════════════════════════════════════════════════════════════════

# Connected WebSocket clients
_ws_clients: set[WebSocket] = set()


@app.websocket("/ws/jobs")
async def websocket_job_stream(websocket: WebSocket):
    """
    Real-time job stream. Clients receive new jobs as JSON as they're scraped.
    
    Message format: {"type": "new_job", "data": {...job fields...}}
    """
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        while True:
            # Keep connection alive — client can send pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)
    except Exception:
        _ws_clients.discard(websocket)


async def broadcast_job(job_dict: dict):
    """Broadcast a new job to all connected WebSocket clients."""
    if not _ws_clients:
        return
    message = json.dumps({"type": "new_job", "data": job_dict})
    disconnected = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.add(ws)
    _ws_clients -= disconnected


# ═══════════════════════════════════════════════════════════════════════
# SALARY ESTIMATOR
# ═══════════════════════════════════════════════════════════════════════

_salary_estimator = None

@app.get("/salary/estimate")
async def estimate_salary(title: str, location: str = ""):
    """Predict salary range for a job title + location."""
    global _salary_estimator
    if _salary_estimator is None:
        from scripts.ai.salary_estimator import SalaryEstimator
        _salary_estimator = SalaryEstimator()
        _salary_estimator.train()

    result = _salary_estimator.predict(title, location)
    if not result:
        return {"error": "Insufficient data for prediction", "title": title, "location": location}
    return {"title": title, "location": location, **result}


# ═══════════════════════════════════════════════════════════════════════
# STATIC FILES — serve web dashboard
# ═══════════════════════════════════════════════════════════════════════

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

WEB_DIR = PROJECT_ROOT / "web"

@app.get("/", include_in_schema=False)
async def root():
    """Serve the web dashboard."""
    return FileResponse(WEB_DIR / "index.html")

if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
