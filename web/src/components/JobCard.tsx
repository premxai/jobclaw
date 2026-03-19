// Job Card — uniform height, warm theme
import CompanyLogo from "./CompanyLogo";

export interface Job {
    id: number;
    internal_hash: string;
    title: string;
    company: string;
    location: string;
    url: string;
    date_posted: string;
    source_ats: string;
    salary_min?: number | null;
    salary_max?: number | null;
    salary_currency?: string;
    keywords_matched?: string;
    description?: string;
    first_seen?: string;
    status?: string;
    freshness_minutes?: number | null;  // computed by /jobs/match
    match_score?: number | null;        // cosine similarity 0-1
}

function timeAgo(dateStr: string): string {
    if (!dateStr) return "";
    const now = new Date();
    const date = new Date(dateStr);
    const diffMs = now.getTime() - date.getTime();
    const diffHrs = Math.floor(diffMs / (1000 * 60 * 60));
    if (diffHrs < 1) return "just now";
    if (diffHrs < 24) return `${diffHrs}h ago`;
    const diffDays = Math.floor(diffHrs / 24);
    if (diffDays === 1) return "1 day ago";
    if (diffDays < 30) return `${diffDays} days ago`;
    return dateStr;
}

function getFreshnessLabel(minutes?: number | null): { emoji: string; color: string } | null {
    if (minutes === null || minutes === undefined) return null;
    if (minutes < 5)  return { emoji: "🔥🔥🔥", color: "text-red-500 font-bold" };
    if (minutes < 15) return { emoji: "🔥🔥",   color: "text-orange-500 font-bold" };
    if (minutes < 60) return { emoji: "🔥",     color: "text-orange-400 font-semibold" };
    if (minutes < 240) return { emoji: "⚡",    color: "text-yellow-500 font-medium" };
    return null;  // older than 4h — no badge needed
}

function formatSalary(min?: number | null, max?: number | null): string | null {
    if (!min && !max) return null;
    const fmt = (n: number) => {
        if (n >= 1000) return `$${Math.round(n / 1000)}k`;
        return `$${n}`;
    };
    if (min && max) return `${fmt(min)} – ${fmt(max)}`;
    if (min) return `${fmt(min)}+`;
    if (max) return `Up to ${fmt(max)}`;
    return null;
}

function getCategory(keywords?: string): string | null {
    if (!keywords) return null;
    try {
        const parsed = JSON.parse(keywords);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed[0];
    } catch {
        return keywords;
    }
    return null;
}

function sourceLabel(ats: string): string {
    const labels: Record<string, string> = {
        greenhouse: "Greenhouse",
        lever: "Lever",
        workday: "Workday",
        ashby: "Ashby",
        rippling: "Rippling",
        linkedin: "LinkedIn",
        indeed: "Indeed",
        glassdoor: "Glassdoor",
        wellfound: "Wellfound",
        brave_search: "Brave Search",
        "github-swe-newgrad": "GitHub",
        "github-ai-newgrad": "GitHub",
        "github-internship": "GitHub",
        "github-new-grad": "GitHub",
    };
    return labels[ats] || ats;
}

interface JobCardProps {
    job: Job;
    onSave?: (job: Job) => void;
    saved?: boolean;
}

export default function JobCard({ job, onSave, saved = false }: JobCardProps) {
    const salary = formatSalary(job.salary_min, job.salary_max);
    const category = getCategory(job.keywords_matched);
    const time = timeAgo(job.date_posted || job.first_seen || "");
    const freshness = getFreshnessLabel(job.freshness_minutes);
    const matchPct = job.match_score != null ? Math.round(job.match_score * 100) : null;

    return (
        <div className="job-card">
            {/* Header: logo + company + time + save */}
            <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                    <CompanyLogo company={job.company} size="md" />
                    <div>
                        <p className="text-sm font-medium text-text-primary">{job.company}</p>
                        {time && <p className="text-xs text-text-secondary">{time}</p>}
                    </div>
                </div>
                {onSave && (
                    <button
                        onClick={(e) => { e.preventDefault(); onSave(job); }}
                        className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${saved
                                ? "bg-accent text-white border-accent"
                                : "bg-white text-text-secondary border-border hover:border-accent"
                            }`}
                    >
                        {saved ? "Saved ✓" : "Save"}
                    </button>
                )}
            </div>

            {/* Title — fixed 2 lines */}
            <h3 className="text-base font-bold text-text-primary mb-3 leading-tight line-clamp-2 min-h-[2.5rem]">
                {job.title}
            </h3>

            {/* Tags — fixed height area */}
            <div className="flex flex-wrap gap-1.5 mb-4 min-h-[2rem]">
                {/* Freshness badge — highest priority, shown first */}
                {freshness && (
                    <span className={`pill ${freshness.color} bg-red-50 border-red-200 border text-xs`}>
                        {freshness.emoji} {job.freshness_minutes! < 60
                            ? `${job.freshness_minutes}m ago`
                            : `${Math.round(job.freshness_minutes! / 60)}h ago`
                        }
                    </span>
                )}
                {matchPct !== null && (
                    <span className="pill bg-accent/10 text-accent border border-accent/30 text-xs font-bold">
                        {matchPct}% match
                    </span>
                )}
                {category && <span className="pill pill-accent">{category}</span>}
                {job.location && (
                    <span className="pill pill-white">{job.location.length > 22 ? job.location.slice(0, 22) + "…" : job.location}</span>
                )}
                <span className="pill pill-white">{sourceLabel(job.source_ats)}</span>
            </div>

            {/* Spacer to push footer to bottom */}
            <div className="flex-1" />

            {/* Footer: salary + apply */}
            <div className="flex items-center justify-between pt-3 border-t border-border">
                <div>
                    {salary && <p className="text-sm font-bold text-text-primary">{salary}</p>}
                    {!salary && <p className="text-xs text-text-secondary">{job.location || "—"}</p>}
                </div>
                <a
                    href={job.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-dark text-xs px-4 py-2"
                >
                    Apply now
                </a>
            </div>
        </div>
    );
}
