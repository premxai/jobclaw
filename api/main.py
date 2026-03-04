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

    # Validate Discord configuration
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    channel_id = os.getenv("DISCORD_CHANNEL_ID")
    if webhook_url:
        print("✅ Discord: webhook configured")
    elif bot_token and channel_id:
        print("✅ Discord: bot token + channel ID configured (fallback mode)")
    else:
        print("⚠️  Discord: NOT configured — set DISCORD_WEBHOOK_URL (or DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID) in .env")
        print("   See .env.example for setup instructions.")

    yield


app = FastAPI(
    title="JobClaw API",
    version="4.0.0",
    description="Real-time job board aggregation API — scrapes 10,500+ company career pages via 8 ATS platforms.",
    lifespan=lifespan,
)

# CORS — lock to frontend origins; wildcard + credentials=True is a spec violation
_allowed_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
)

# API Key auth — disabled if JOBCLAW_API_KEY not set
from api.auth import APIKeyMiddleware
app.add_middleware(APIKeyMiddleware)


# ═══════════════════════════════════════════════════════════════════════
# STATIC DASHBOARD ROUTE
# ═══════════════════════════════════════════════════════════════════════

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

WEB_DIR = PROJECT_ROOT / "web"

@app.get("/", include_in_schema=False)
async def root():
    """Serve the web dashboard index if it exists."""
    index = WEB_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"status": "ok", "message": "JobClaw API — see /docs"})

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
    VALID_TIERS = {"fast", "medium", "heavy", "deep"}
    if tier not in VALID_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier '{tier}'. Must be one of: {', '.join(VALID_TIERS)}"
        )
    import subprocess
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "ingestion" / "run_all_scrapers.py"),
        "--tier", tier,  # safe — tier validated against allowlist above
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

    Auth: If JOBCLAW_API_KEY is set, clients must supply it as a query param:
        ws://host/ws/jobs?token=<your-api-key>
    """
    # Optional token auth — mirrors the X-API-Key middleware logic
    required_key = os.getenv("JOBCLAW_API_KEY")
    if required_key:
        provided = websocket.query_params.get("token", "")
        if provided != required_key:
            await websocket.close(code=4401, reason="Unauthorized: invalid or missing token")
            return

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
# AI — SEMANTIC SEARCH & MATCHING
# ═══════════════════════════════════════════════════════════════════════

_job_embedder = None

@app.get("/jobs/similar")
async def similar_jobs(query: str, top_k: int = 10):
    """Find jobs semantically similar to a text query."""
    global _job_embedder
    if _job_embedder is None:
        from scripts.ai.embed_jobs import JobEmbedder
        _job_embedder = JobEmbedder()

    results = _job_embedder.find_similar(query, top_k=top_k)
    return {"query": query, "results": results, "count": len(results)}


@app.post("/resume/match")
async def resume_match(resume_text: str = "", top_k: int = 20):
    """Score jobs against a resume text."""
    if not resume_text:
        raise HTTPException(status_code=400, detail="resume_text is required")

    from scripts.ai.match_score import ResumeMatcher
    matcher = ResumeMatcher()
    matcher.load_resume(resume_text)
    matches = matcher.score_jobs(top_k=top_k)
    return {"matches": matches, "count": len(matches)}


@app.post("/admin/dedup")
async def run_dedup(threshold: float = 0.6, dry_run: bool = True):
    """Find and optionally merge duplicate job listings."""
    from scripts.ai.dedup import JobDeduplicator
    dedup = JobDeduplicator(threshold=threshold)
    clusters = dedup.find_duplicates()

    result = {
        "clusters_found": len(clusters),
        "total_duplicates": sum(len(c) - 1 for c in clusters),
        "clusters": clusters[:20],  # Preview first 20
    }

    if not dry_run:
        merged = dedup.merge_duplicates(clusters)
        result["merged"] = merged

    return result


# ═══════════════════════════════════════════════════════════════════════
# APPLICATION TRACKER — Kanban board API
# ═══════════════════════════════════════════════════════════════════════

VALID_STAGES = ["saved", "applied", "phone_screen", "onsite", "offer", "rejected", "withdrawn"]

def _ensure_applications_table():
    """Create applications table in SQLite if it doesn't exist."""
    conn = get_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_hash TEXT,
                user_id TEXT DEFAULT 'default',
                stage TEXT DEFAULT 'saved',
                notes TEXT,
                applied_at TEXT,
                updated_at TEXT,
                interview_date TEXT,
                contact_name TEXT,
                contact_email TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()

_ensure_applications_table()


@app.get("/applications")
async def list_applications(stage: str = None, user_id: str = "default"):
    """Get all tracked applications, optionally filtered by stage."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        if stage:
            cursor.execute("""
                SELECT a.*, j.title, j.company, j.location, j.url, j.salary_min, j.salary_max
                FROM applications a
                LEFT JOIN jobs j ON a.job_hash = j.internal_hash
                WHERE a.user_id = ? AND a.stage = ?
                ORDER BY a.updated_at DESC
            """, (user_id, stage))
        else:
            cursor.execute("""
                SELECT a.*, j.title, j.company, j.location, j.url, j.salary_min, j.salary_max
                FROM applications a
                LEFT JOIN jobs j ON a.job_hash = j.internal_hash
                WHERE a.user_id = ?
                ORDER BY a.updated_at DESC
            """, (user_id,))
        rows = cursor.fetchall()
        return {"applications": [dict(r) for r in rows], "count": len(rows)}
    finally:
        conn.close()


@app.post("/applications")
async def create_application(job_hash: str, stage: str = "saved", notes: str = "", user_id: str = "default"):
    """Save a job to the application tracker."""
    if stage not in VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage. Must be one of: {VALID_STAGES}")
    
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO applications (job_hash, user_id, stage, notes, updated_at, applied_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (job_hash, user_id, stage, notes, now, now if stage == "applied" else None))
        conn.commit()
        app_id = cursor.lastrowid
        return {"id": app_id, "job_hash": job_hash, "stage": stage, "created": True}
    finally:
        conn.close()


@app.put("/applications/{app_id}/stage")
async def update_application_stage(app_id: int, stage: str):
    """Move an application to a different Kanban stage."""
    if stage not in VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage. Must be one of: {VALID_STAGES}")
    
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE applications SET stage = ?, updated_at = ?,
                applied_at = CASE WHEN ? = 'applied' AND applied_at IS NULL THEN ? ELSE applied_at END
            WHERE id = ?
        """, (stage, now, stage, now, app_id))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Application not found")
        return {"id": app_id, "stage": stage, "updated": True}
    finally:
        conn.close()


@app.put("/applications/{app_id}")
async def update_application(app_id: int, notes: str = None, interview_date: str = None,
                              contact_name: str = None, contact_email: str = None):
    """Update application details (notes, interview date, contacts)."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    
    conn = get_db()
    try:
        updates = ["updated_at = ?"]
        params = [now]
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        if interview_date is not None:
            updates.append("interview_date = ?")
            params.append(interview_date)
        if contact_name is not None:
            updates.append("contact_name = ?")
            params.append(contact_name)
        if contact_email is not None:
            updates.append("contact_email = ?")
            params.append(contact_email)
        
        params.append(app_id)
        cursor = conn.cursor()
        cursor.execute(f"UPDATE applications SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Application not found")
        return {"id": app_id, "updated": True}
    finally:
        conn.close()


@app.delete("/applications/{app_id}")
async def delete_application(app_id: int):
    """Remove an application from the tracker."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM applications WHERE id = ?", (app_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Application not found")
        return {"id": app_id, "deleted": True}
    finally:
        conn.close()


@app.get("/applications/stats")
async def application_stats(user_id: str = "default"):
    """Get application funnel stats."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT stage, COUNT(*) as count
            FROM applications
            WHERE user_id = ?
            GROUP BY stage
        """, (user_id,))
        stages = {r[0]: r[1] for r in cursor.fetchall()}
        total = sum(stages.values())
        return {"stages": stages, "total": total}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# STATIC FILES — serve web dashboard
# ═══════════════════════════════════════════════════════════════════════

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
