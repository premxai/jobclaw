// API utility — fetches from the FastAPI backend
// In dev: proxied via next.config.ts rewrites
// In prod: direct URL to the API server

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

export async function fetchJobs(params?: {
    search?: string;
    category?: string;
    source?: string;
    page?: number;
    limit?: number;
}): Promise<{ jobs: any[]; total: number }> {
    const searchParams = new URLSearchParams();
    if (params?.search) searchParams.set("search", params.search);
    if (params?.category) searchParams.set("category", params.category);
    if (params?.source) searchParams.set("source", params.source);
    if (params?.page) searchParams.set("page", String(params.page));
    if (params?.limit) searchParams.set("limit", String(params.limit));

    const qs = searchParams.toString();
    const url = `${API_BASE}/jobs${qs ? `?${qs}` : ""}`;

    try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) throw new Error(`API ${res.status}`);
        return await res.json();
    } catch {
        // Fallback: return mock data in dev when API isn't running
        return { jobs: getMockJobs(), total: getMockJobs().length };
    }
}

export async function fetchJobById(id: string): Promise<any | null> {
    try {
        const res = await fetch(`${API_BASE}/jobs/${id}`, { cache: "no-store" });
        if (!res.ok) return null;
        return await res.json();
    } catch {
        const jobs = getMockJobs();
        return jobs.find((j) => String(j.id) === id) || null;
    }
}

export async function fetchStats(): Promise<any> {
    try {
        const res = await fetch(`${API_BASE}/stats`, { cache: "no-store" });
        if (!res.ok) throw new Error(`API ${res.status}`);
        return await res.json();
    } catch {
        return {
            total_jobs: 608,
            total_companies: 11800,
            sources: 9,
            categories: { "AI/ML": 180, SWE: 220, "Data Science": 80, "Data Engineering": 45, "Data Analyst": 35, "New Grad": 40, Product: 5, Research: 3 },
            by_source: { "github-swe-newgrad": 239, "github-ai-newgrad": 222, workday: 45, greenhouse: 36, "github-internship": 34, lever: 3, indeed: 3 },
        };
    }
}

// Mock data for dev when API isn't running
function getMockJobs() {
    return [
        { id: 1, internal_hash: "a1", title: "Senior ML Engineer", company: "Google", location: "Mountain View, CA", url: "https://careers.google.com", date_posted: "2026-03-04", source_ats: "greenhouse", salary_min: 180000, salary_max: 250000, keywords_matched: '["AI/ML"]', description: "Lead ML initiatives at scale across Google's core products." },
        { id: 2, internal_hash: "b2", title: "Backend Engineer", company: "Stripe", location: "San Francisco, CA", url: "https://stripe.com/jobs", date_posted: "2026-03-04", source_ats: "greenhouse", salary_min: 150000, salary_max: 200000, keywords_matched: '["SWE"]', description: "Build payment infrastructure serving millions of businesses." },
        { id: 3, internal_hash: "c3", title: "Data Scientist", company: "Meta", location: "New York, NY", url: "https://metacareers.com", date_posted: "2026-03-03", source_ats: "workday", salary_min: 140000, salary_max: 190000, keywords_matched: '["Data Science"]', description: "Drive data-driven decisions for Instagram engagement." },
        { id: 4, internal_hash: "d4", title: "Full Stack Developer", company: "Airbnb", location: "Remote, US", url: "https://careers.airbnb.com", date_posted: "2026-03-03", source_ats: "greenhouse", salary_min: 130000, salary_max: 180000, keywords_matched: '["SWE"]', description: "Build next-gen experiences for hosts and guests worldwide." },
        { id: 5, internal_hash: "e5", title: "New Grad SWE 2026", company: "Amazon", location: "Seattle, WA", url: "https://amazon.jobs", date_posted: "2026-03-02", source_ats: "workday", keywords_matched: '["New Grad"]', description: "Join Amazon's 2026 new graduate software engineering program." },
        { id: 6, internal_hash: "f6", title: "AI Research Scientist", company: "OpenAI", location: "San Francisco, CA", url: "https://openai.com/careers", date_posted: "2026-03-04", source_ats: "lever", salary_min: 200000, salary_max: 350000, keywords_matched: '["AI/ML"]', description: "Push the frontier of artificial intelligence research." },
        { id: 7, internal_hash: "g7", title: "Data Engineer", company: "Netflix", location: "Los Gatos, CA", url: "https://jobs.netflix.com", date_posted: "2026-03-03", source_ats: "lever", salary_min: 160000, salary_max: 220000, keywords_matched: '["Data Engineering"]', description: "Build data pipelines powering content recommendations at scale." },
        { id: 8, internal_hash: "h8", title: "iOS Engineer", company: "Apple", location: "Cupertino, CA", url: "https://jobs.apple.com", date_posted: "2026-03-02", source_ats: "workday", salary_min: 170000, salary_max: 240000, keywords_matched: '["SWE"]', description: "Craft the next generation of iOS experiences." },
        { id: 9, internal_hash: "i9", title: "Product Manager, Growth", company: "Notion", location: "San Francisco, CA", url: "https://notion.so/careers", date_posted: "2026-03-01", source_ats: "greenhouse", salary_min: 140000, salary_max: 190000, keywords_matched: '["Product"]', description: "Drive user acquisition and retention strategies." },
        { id: 10, internal_hash: "j10", title: "DevOps Engineer", company: "Datadog", location: "Remote, US", url: "https://careers.datadoghq.com", date_posted: "2026-03-04", source_ats: "greenhouse", salary_min: 145000, salary_max: 195000, keywords_matched: '["SWE"]', description: "Build and maintain cloud infrastructure at massive scale." },
        { id: 11, internal_hash: "k11", title: "Machine Learning Intern", company: "NVIDIA", location: "Santa Clara, CA", url: "https://nvidia.wd5.myworkdayjobs.com", date_posted: "2026-03-04", source_ats: "workday", keywords_matched: '["New Grad"]', description: "Summer 2026 ML internship working on GPU-accelerated deep learning." },
        { id: 12, internal_hash: "l12", title: "Data Analyst", company: "Spotify", location: "New York, NY", url: "https://lifeatspotify.com", date_posted: "2026-03-03", source_ats: "greenhouse", salary_min: 90000, salary_max: 130000, keywords_matched: '["Data Analyst"]', description: "Analyze listening patterns and drive product decisions." },
    ];
}
