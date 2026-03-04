/**
 * API layer — fetches from the FastAPI backend (port 8000)
 * Falls back to mock data if the API isn't running.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
}

// Normalise backend response into something the frontend expects
function normaliseJob(j: ApiJob, index?: number): any {
    let kw = j.keywords_matched;
    if (Array.isArray(kw)) kw = JSON.stringify(kw);
    return {
        ...j,
        id: index ?? j.internal_hash,  // numeric id for link URLs
        keywords_matched: kw,
    };
}

// ─── Fetch jobs ─────────────────────────────────────────────────────
export async function fetchJobs(params?: {
    search?: string;
    category?: string;
    source?: string;
    page?: number;
    limit?: number;
}): Promise<{ jobs: any[]; total: number }> {
    const sp = new URLSearchParams();
    if (params?.search) sp.set("search", params.search);
    if (params?.category) sp.set("keyword", params.category);   // backend uses "keyword"
    if (params?.source) sp.set("ats", params.source);            // backend uses "ats"
    if (params?.page) sp.set("page", String(params.page));
    if (params?.limit) sp.set("per_page", String(params.limit)); // backend uses "per_page"

    const qs = sp.toString();
    const url = `${API_BASE}/jobs${qs ? `?${qs}` : ""}`;

    try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) throw new Error(`API ${res.status}`);
        const data = await res.json();
        // Backend returns { jobs: [...], total, page, per_page, has_more }
        return {
            jobs: data.jobs.map((j: ApiJob, i: number) => normaliseJob(j, i + 1)),
            total: data.total,
        };
    } catch {
        return { jobs: getMockJobs(), total: getMockJobs().length };
    }
}

// ─── Fetch single job ───────────────────────────────────────────────
export async function fetchJobById(id: string): Promise<any | null> {
    // The backend uses internal_hash as the ID in the URL
    // But we may receive either a numeric index or a hash — try both
    try {
        // First try: fetch all jobs and find by index
        const allRes = await fetch(`${API_BASE}/jobs?per_page=200`, { cache: "no-store" });
        if (!allRes.ok) throw new Error("API error");
        const allData = await allRes.json();
        const numId = parseInt(id);
        if (!isNaN(numId) && numId > 0 && numId <= allData.jobs.length) {
            return normaliseJob(allData.jobs[numId - 1], numId);
        }
        // If not numeric, try by hash
        const res = await fetch(`${API_BASE}/jobs/${id}`, { cache: "no-store" });
        if (!res.ok) return null;
        const job = await res.json();
        return normaliseJob(job);
    } catch {
        const jobs = getMockJobs();
        return jobs.find((j) => String(j.id) === id) || null;
    }
}

// ─── Fetch stats ────────────────────────────────────────────────────
export async function fetchStats(): Promise<any> {
    try {
        const res = await fetch(`${API_BASE}/stats`, { cache: "no-store" });
        if (!res.ok) throw new Error(`API ${res.status}`);
        const data = await res.json();
        return {
            total_jobs: data.total_jobs || 0,
            total_companies: data.companies || 0,
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

// ─── Mock data fallback ─────────────────────────────────────────────
function getMockJobs() {
    return [
        { id: 1, internal_hash: "a1", title: "Senior ML Engineer", company: "Google", location: "Mountain View, CA", url: "https://careers.google.com", date_posted: "2026-03-04", source_ats: "greenhouse", salary_min: 180000, salary_max: 250000, keywords_matched: '["AI/ML"]', description: "Lead ML initiatives at scale." },
        { id: 2, internal_hash: "b2", title: "Backend Engineer", company: "Stripe", location: "San Francisco, CA", url: "https://stripe.com/jobs", date_posted: "2026-03-04", source_ats: "greenhouse", salary_min: 150000, salary_max: 200000, keywords_matched: '["SWE"]', description: "Build payment infrastructure." },
        { id: 3, internal_hash: "c3", title: "Data Scientist", company: "Meta", location: "New York, NY", url: "https://metacareers.com", date_posted: "2026-03-03", source_ats: "workday", salary_min: 140000, salary_max: 190000, keywords_matched: '["Data Science"]', description: "Drive data-driven decisions." },
        { id: 4, internal_hash: "d4", title: "Full Stack Developer", company: "Airbnb", location: "Remote, US", url: "https://careers.airbnb.com", date_posted: "2026-03-03", source_ats: "greenhouse", salary_min: 130000, salary_max: 180000, keywords_matched: '["SWE"]', description: "Build next-gen experiences." },
        { id: 5, internal_hash: "e5", title: "New Grad SWE 2026", company: "Amazon", location: "Seattle, WA", url: "https://amazon.jobs", date_posted: "2026-03-02", source_ats: "workday", keywords_matched: '["New Grad"]', description: "Join Amazon's new grad program." },
        { id: 6, internal_hash: "f6", title: "AI Research Scientist", company: "OpenAI", location: "San Francisco, CA", url: "https://openai.com/careers", date_posted: "2026-03-04", source_ats: "lever", salary_min: 200000, salary_max: 350000, keywords_matched: '["AI/ML"]', description: "Push the frontier of AI." },
    ];
}
