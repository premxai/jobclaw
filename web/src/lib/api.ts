/**
 * API layer — fetches from the FastAPI backend.
 * Mock data is opt-in only via NEXT_PUBLIC_ENABLE_MOCK_JOBS=1.
 */

import type { Job } from "@/components/JobCard";

const API_BASE = "/api";
const ENABLE_MOCK_JOBS = process.env.NEXT_PUBLIC_ENABLE_MOCK_JOBS === "1";

// ─── Job types ──────────────────────────────────────────────────────
export interface ApiJob {
    internal_hash: string;
    job_id: string;
    title: string;
    company: string;
    location: string;
    url: string;
    date_posted: string;
    source_ats: string;
    first_seen: string | null;
    status: string;
    keywords_matched: string[] | string;
    description: string | null;
    salary_min: number | null;
    salary_max: number | null;
    salary_currency: string | null;
    is_active: boolean;
    canonical_company?: string | null;
    canonical_title?: string | null;
}

// /jobs/match returns the same raw `jobs` row shape as ApiJob, plus these two
// fields computed server-side (cosine similarity + minutes since first_seen).
interface ApiMatchedJob extends ApiJob {
    match_score: number | null;
    freshness_minutes: number | null;
}

interface JobsResponse {
    jobs: ApiJob[];
    total: number;
}

interface MatchResponse {
    results: ApiMatchedJob[];
    query: string;
    total: number;
}

// /resume/match (via our own /api/resume-match route) returns a narrower,
// differently-named shape than /jobs and /jobs/match — no job_id/date_posted/
// source_ats, and the score field is "score" + "match_tier", not "match_score".
interface ApiResumeMatch {
    internal_hash: string;
    title: string;
    company: string;
    location: string;
    url: string;
    salary_min: number | null;
    salary_max: number | null;
    keywords_matched: string[] | string;
    score: number;
    match_tier: "excellent" | "good" | "fair";
}

interface ResumeMatchResponse {
    enabled: boolean;
    matches?: ApiResumeMatch[];
    count?: number;
    error?: string;
}

interface StatsResponse {
    total_jobs: number;
    total_companies: number;
    sources: number;
    platforms?: Record<string, unknown>;
    jobs_last_24h?: number;
    jobs_last_7d?: number;
}

// Normalise backend response into something the frontend expects
function normaliseJob(j: ApiJob, index?: number): Job {
    let kw = j.keywords_matched;
    if (Array.isArray(kw)) kw = JSON.stringify(kw);
    return {
        ...j,
        id: index ?? j.internal_hash,  // numeric id for link URLs
        keywords_matched: kw,
    };
}

// Same shape as normaliseJob, but also carries through match_score/freshness_minutes
// so JobCard can render its match-percent + freshness pills (it already knows how).
function normaliseMatchedJob(j: ApiMatchedJob, index?: number): Job {
    return { ...normaliseJob(j, index), match_score: j.match_score, freshness_minutes: j.freshness_minutes };
}

// /resume/match's result shape is missing date_posted/source_ats (it's a
// narrower "scored jobs" query, not a full jobs row) — JobCard only requires
// those for display, so empty strings render as blank rather than breaking.
function normaliseResumeMatch(m: ApiResumeMatch, index: number): Job {
    let kw = m.keywords_matched;
    if (Array.isArray(kw)) kw = JSON.stringify(kw);
    return {
        id: index,
        internal_hash: m.internal_hash,
        title: m.title,
        company: m.company,
        location: m.location,
        url: m.url,
        date_posted: "",
        source_ats: "",
        salary_min: m.salary_min,
        salary_max: m.salary_max,
        keywords_matched: kw,
        match_score: m.score,
    };
}

// ─── Fetch jobs ─────────────────────────────────────────────────────
export async function fetchJobs(params?: {
    search?: string;
    category?: string;
    source?: string;
    company?: string;
    page?: number;
    limit?: number;
    recentHours?: number;
}): Promise<{ jobs: Job[]; total: number }> {
    const sp = new URLSearchParams();
    if (params?.search) sp.set("search", params.search);
    if (params?.category) sp.set("keyword", params.category);   // backend uses "keyword"
    if (params?.source) sp.set("ats", params.source);            // backend uses "ats"
    if (params?.company) sp.set("company", params.company);
    if (params?.page) sp.set("page", String(params.page));
    if (params?.limit) sp.set("per_page", String(params.limit)); // backend uses "per_page"
    if (params?.recentHours) sp.set("recent_hours", String(params.recentHours));

    const qs = sp.toString();
    const url = `${API_BASE}/jobs${qs ? `?${qs}` : ""}`;

    try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) throw new Error(`API ${res.status}`);
        const data: JobsResponse = await res.json();
        // Backend returns { jobs: [...], total, page, per_page, has_more }
        return {
            jobs: data.jobs.map((j: ApiJob, i: number) => normaliseJob(j, i + 1)),
            total: data.total,
        };
    } catch {
        if (!ENABLE_MOCK_JOBS) return { jobs: [], total: 0 };

        return { jobs: getMockJobs(), total: getMockJobs().length };
    }
}

// ─── Semantic "best match" search ──────────────────────────────────
// Hits /jobs/match — a single ranked top-K list, not paginated, so callers
// should hide pagination controls when using this instead of fetchJobs().
export async function fetchMatchedJobs(query: string, topK = 20): Promise<{ jobs: Job[]; total: number }> {
    const sp = new URLSearchParams({ q: query, top_k: String(topK) });
    try {
        const res = await fetch(`${API_BASE}/jobs/match?${sp.toString()}`, { cache: "no-store" });
        if (!res.ok) throw new Error(`API ${res.status}`);
        const data: MatchResponse = await res.json();
        return {
            jobs: data.results.map((j, i) => normaliseMatchedJob(j, i + 1)),
            total: data.total,
        };
    } catch {
        return { jobs: [], total: 0 };
    }
}

// ─── Resume-to-job scoring ──────────────────────────────────────────
// Calls our OWN same-origin Route Handler (web/src/app/api/resume-match/route.ts),
// never the FastAPI backend directly — that route is what holds the protected
// X-API-Key server-side. `enabled: false` means the deployment hasn't configured
// a key yet (today's actual production state); callers should show that as a
// distinct "not enabled" message rather than a generic error.
export async function matchResume(
    resumeText: string,
    topK = 20
): Promise<{ enabled: boolean; jobs: Job[]; error?: string }> {
    try {
        const res = await fetch("/api/resume-match", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ resume_text: resumeText, top_k: topK }),
        });
        const data: ResumeMatchResponse = await res.json();
        if (!data.enabled) return { enabled: false, jobs: [] };
        if (data.error || !data.matches) return { enabled: true, jobs: [], error: data.error || "No matches returned" };
        return { enabled: true, jobs: data.matches.map((m, i) => normaliseResumeMatch(m, i + 1)) };
    } catch (e) {
        return { enabled: true, jobs: [], error: e instanceof Error ? e.message : "Request failed" };
    }
}

// ─── Fetch single job ───────────────────────────────────────────────
export async function fetchJobById(id: string): Promise<Job | null> {
    // Use the dedicated /jobs/{hash} endpoint instead of fetching all jobs
    try {
        // Try direct hash lookup first (most common case)
        const res = await fetch(`${API_BASE}/jobs/${encodeURIComponent(id)}`, { cache: "no-store" });
        if (res.ok) {
            const job = await res.json();
            return normaliseJob(job);
        }
        // If not found by hash, it might be a numeric index — fetch that page
        const numId = parseInt(id);
        if (!isNaN(numId) && numId > 0) {
            const pageRes = await fetch(`${API_BASE}/jobs?page=1&per_page=${numId}`, { cache: "no-store" });
            if (pageRes.ok) {
                const data = await pageRes.json();
                if (data.jobs && data.jobs.length >= numId) {
                    return normaliseJob(data.jobs[numId - 1], numId);
                }
            }
        }
        return null;
    } catch {
        if (!ENABLE_MOCK_JOBS) return null;

        const jobs = getMockJobs();
        return jobs.find((j) => String(j.id) === id) || null;
    }
}

// ─── Fetch stats ────────────────────────────────────────────────────
export async function fetchStats(): Promise<StatsResponse> {
    try {
        const res = await fetch(`${API_BASE}/stats`, { cache: "no-store" });
        if (!res.ok) throw new Error(`API ${res.status}`);
        const data: StatsResponse = await res.json();
        return {
            total_jobs: data.total_jobs || 0,
            total_companies: data.total_companies || 0,
            sources: Object.keys(data.platforms || {}).length,
            platforms: data.platforms || {},
            jobs_last_24h: data.jobs_last_24h || 0,
            jobs_last_7d: data.jobs_last_7d || 0,
        };
    } catch {
        return {
            total_jobs: 608,
            total_companies: 11800,
            sources: 9,
        };
    }
}

// ─── Fetch companies ────────────────────────────────────────────────
export interface Company {
    company: string;
    source_ats: string;
    job_count: number;
    latest_job: string | null;
}

export async function fetchCompanies(ats?: string): Promise<Company[]> {
    const sp = new URLSearchParams();
    if (ats) sp.set("ats", ats);
    const qs = sp.toString();
    try {
        const res = await fetch(`${API_BASE}/companies${qs ? `?${qs}` : ""}`, { cache: "no-store" });
        if (!res.ok) throw new Error(`API ${res.status}`);
        return (await res.json()) as Company[];
    } catch {
        return [];
    }
}

// ─── Mock data fallback ─────────────────────────────────────────────
function getMockJobs(): Job[] {
    return [
        { id: 1, internal_hash: "a1", title: "Senior ML Engineer", company: "Google", location: "Mountain View, CA", url: "https://careers.google.com", date_posted: "2026-03-04", source_ats: "greenhouse", salary_min: 180000, salary_max: 250000, keywords_matched: '["AI/ML"]', description: "Lead ML initiatives at scale." },
        { id: 2, internal_hash: "b2", title: "Backend Engineer", company: "Stripe", location: "San Francisco, CA", url: "https://stripe.com/jobs", date_posted: "2026-03-04", source_ats: "greenhouse", salary_min: 150000, salary_max: 200000, keywords_matched: '["SWE"]', description: "Build payment infrastructure." },
        { id: 3, internal_hash: "c3", title: "Data Scientist", company: "Meta", location: "New York, NY", url: "https://metacareers.com", date_posted: "2026-03-03", source_ats: "workday", salary_min: 140000, salary_max: 190000, keywords_matched: '["Data Science"]', description: "Drive data-driven decisions." },
        { id: 4, internal_hash: "d4", title: "Full Stack Developer", company: "Airbnb", location: "Remote, US", url: "https://careers.airbnb.com", date_posted: "2026-03-03", source_ats: "greenhouse", salary_min: 130000, salary_max: 180000, keywords_matched: '["SWE"]', description: "Build next-gen experiences." },
        { id: 5, internal_hash: "e5", title: "New Grad SWE 2026", company: "Amazon", location: "Seattle, WA", url: "https://amazon.jobs", date_posted: "2026-03-02", source_ats: "workday", keywords_matched: '["New Grad"]', description: "Join Amazon's new grad program." },
        { id: 6, internal_hash: "f6", title: "AI Research Scientist", company: "OpenAI", location: "San Francisco, CA", url: "https://openai.com/careers", date_posted: "2026-03-04", source_ats: "lever", salary_min: 200000, salary_max: 350000, keywords_matched: '["AI/ML"]', description: "Push the frontier of AI." },
    ];
}
