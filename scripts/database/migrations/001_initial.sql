-- =======================================================================
-- JobClaw PostgreSQL Schema — Initial Migration
-- =======================================================================
-- Migrate from SQLite to PostgreSQL with:
--   - Full-text search (tsvector + GIN index)
--   - pgvector embeddings column (requires: CREATE EXTENSION vector;)
--   - Proper indexes for time-series and lookup queries
--   - UPSERT support via ON CONFLICT
--
-- Usage:
--   psql $DATABASE_URL -f 001_initial.sql
-- =======================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- CREATE EXTENSION IF NOT EXISTS vector;  -- Uncomment when pgvector is installed

-- ── Jobs Table ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS jobs (
    id               SERIAL PRIMARY KEY,
    internal_hash    TEXT NOT NULL UNIQUE,
    job_id           TEXT DEFAULT '',
    title            TEXT NOT NULL DEFAULT '',
    company          TEXT NOT NULL DEFAULT '',
    location         TEXT DEFAULT '',
    url              TEXT DEFAULT '',
    date_posted      TEXT DEFAULT '',
    source_ats       TEXT DEFAULT '',
    first_seen       TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at     TIMESTAMPTZ DEFAULT NOW(),
    status           TEXT DEFAULT 'unposted' CHECK (status IN ('unposted', 'posted', 'archived')),
    keywords_matched TEXT DEFAULT '[]',
    description      TEXT,
    salary_min       NUMERIC,
    salary_max       NUMERIC,
    salary_currency  TEXT DEFAULT 'USD',
    experience_years INTEGER,
    is_active        BOOLEAN DEFAULT TRUE,

    -- Full-text search vector (auto-populated by trigger)
    search_vector    TSVECTOR

    -- Embedding vector (uncomment when pgvector is installed)
    -- , embedding       vector(1536)
);

-- ── Indexes ─────────────────────────────────────────────────────────

-- Primary lookup
CREATE INDEX IF NOT EXISTS idx_jobs_hash ON jobs (internal_hash);

-- Time-series queries (newest first)
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs (first_seen DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON jobs (last_seen_at DESC);

-- Filtering
CREATE INDEX IF NOT EXISTS idx_jobs_active ON jobs (is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);
CREATE INDEX IF NOT EXISTS idx_jobs_ats ON jobs (source_ats);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs (company);

-- Composite for common queries
CREATE INDEX IF NOT EXISTS idx_jobs_ats_company ON jobs (source_ats, company);
CREATE INDEX IF NOT EXISTS idx_jobs_active_unposted ON jobs (status, is_active) 
    WHERE status = 'unposted' AND is_active = TRUE;

-- Full-text search (GIN index for fast text search)
CREATE INDEX IF NOT EXISTS idx_jobs_search ON jobs USING GIN (search_vector);

-- Embedding similarity search (uncomment when pgvector is installed)
-- CREATE INDEX IF NOT EXISTS idx_jobs_embedding ON jobs USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);


-- ── Search Vector Trigger ───────────────────────────────────────────
-- Automatically populate search_vector on INSERT/UPDATE

CREATE OR REPLACE FUNCTION jobs_search_vector_update()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := 
        setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.company, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.location, '')), 'C') ||
        setweight(to_tsvector('english', COALESCE(NEW.description, '')), 'D');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_jobs_search_vector ON jobs;
CREATE TRIGGER trg_jobs_search_vector
    BEFORE INSERT OR UPDATE OF title, company, location, description
    ON jobs
    FOR EACH ROW
    EXECUTE FUNCTION jobs_search_vector_update();


-- ── Scraper Runs Table ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS runs (
    id                SERIAL PRIMARY KEY,
    script_name       TEXT NOT NULL,
    timestamp         TIMESTAMPTZ DEFAULT NOW(),
    companies_fetched INTEGER DEFAULT 0,
    new_jobs_found    INTEGER DEFAULT 0,
    duration_s        NUMERIC DEFAULT 0,
    errors            TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_timestamp ON runs (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_runs_script ON runs (script_name);


-- ── Applications Table (for future Kanban tracker) ──────────────────

CREATE TABLE IF NOT EXISTS applications (
    id               SERIAL PRIMARY KEY,
    job_hash         TEXT REFERENCES jobs(internal_hash),
    user_id          TEXT DEFAULT 'default',
    stage            TEXT DEFAULT 'saved' CHECK (stage IN ('saved', 'applied', 'phone_screen', 'onsite', 'offer', 'rejected', 'withdrawn')),
    notes            TEXT,
    applied_at       TIMESTAMPTZ,
    updated_at       TIMESTAMPTZ DEFAULT NOW(),
    interview_date   TIMESTAMPTZ,
    contact_name     TEXT,
    contact_email    TEXT
);

CREATE INDEX IF NOT EXISTS idx_app_user ON applications (user_id);
CREATE INDEX IF NOT EXISTS idx_app_stage ON applications (stage);


-- ── Views ───────────────────────────────────────────────────────────

-- Active jobs with full-text rank
CREATE OR REPLACE VIEW v_active_jobs AS
SELECT 
    id, internal_hash, title, company, location, url, 
    source_ats, first_seen, salary_min, salary_max, salary_currency,
    keywords_matched, is_active, status
FROM jobs
WHERE is_active = TRUE
ORDER BY first_seen DESC;

-- Company stats
CREATE OR REPLACE VIEW v_company_stats AS
SELECT 
    company,
    source_ats,
    COUNT(*) AS total_jobs,
    COUNT(*) FILTER (WHERE is_active = TRUE) AS active_jobs,
    MAX(first_seen) AS latest_job,
    AVG(salary_min) FILTER (WHERE salary_min > 10000) AS avg_salary_min,
    AVG(salary_max) FILTER (WHERE salary_max > 10000) AS avg_salary_max
FROM jobs
GROUP BY company, source_ats
ORDER BY active_jobs DESC;

-- Platform stats
CREATE OR REPLACE VIEW v_platform_stats AS
SELECT 
    source_ats AS platform,
    COUNT(*) AS total_jobs,
    COUNT(*) FILTER (WHERE is_active = TRUE) AS active_jobs,
    COUNT(*) FILTER (WHERE first_seen > NOW() - INTERVAL '24 hours') AS jobs_24h,
    COUNT(*) FILTER (WHERE first_seen > NOW() - INTERVAL '7 days') AS jobs_7d
FROM jobs
GROUP BY source_ats
ORDER BY active_jobs DESC;


-- Done!
-- To migrate from SQLite:
--   pgloader sqlite:///path/to/jobclaw.db postgresql://user:pass@host:5432/jobclaw
