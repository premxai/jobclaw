import Link from "next/link";
import { Bookmark, BookmarkCheck, ExternalLink, MapPin } from "lucide-react";
import CompanyLogo from "./CompanyLogo";
import { displayCompany, displayTitle } from "@/lib/job-display";

export interface Job {
    id: number | string;
    internal_hash: string;
    title: string;
    company: string;
    canonical_company?: string | null;
    canonical_title?: string | null;
    location: string;
    url: string;
    date_posted: string;
    source_ats: string;
    salary_min?: number | null;
    salary_max?: number | null;
    salary_currency?: string | null;
    keywords_matched?: string | null;
    description?: string | null;
    first_seen?: string | null;
    status?: string | null;
    freshness_minutes?: number | null;
    match_score?: number | null;
}

function timeAgo(dateStr: string): string {
    if (!dateStr) return "";
    const date = new Date(dateStr);
    if (Number.isNaN(date.getTime())) return "";
    const diffMs = Date.now() - date.getTime();
    const diffHrs = Math.floor(diffMs / (1000 * 60 * 60));
    if (diffHrs < 1) return "just now";
    if (diffHrs < 24) return `${diffHrs}h ago`;
    const diffDays = Math.floor(diffHrs / 24);
    if (diffDays === 1) return "1 day ago";
    if (diffDays < 30) return `${diffDays} days ago`;
    const diffMonths = Math.floor(diffDays / 30);
    return diffMonths === 1 ? "1 month ago" : `${diffMonths} months ago`;
}

function getCategory(keywords?: string | null): string | null {
    if (!keywords) return null;
    try {
        const parsed = JSON.parse(keywords);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed[0];
    } catch {
        return keywords;
    }
    return null;
}

export function sourceLabel(ats: string): string {
    const labels: Record<string, string> = {
        greenhouse: "Greenhouse",
        lever: "Lever",
        workday: "Workday",
        ashby: "Ashby",
        rippling: "Rippling",
        workable: "Workable",
        smartrecruiters: "SmartRecruiters",
        bamboohr: "BambooHR",
        oracle: "Oracle",
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
    return labels[ats] || ats || "Direct";
}

interface JobCardProps {
    job: Job;
    onSave?: (job: Job) => void;
    saved?: boolean;
}

export default function JobCard({ job, onSave, saved = false }: JobCardProps) {
    const company = displayCompany(job);
    const title = displayTitle(job);
    const category = getCategory(job.keywords_matched);
    const time = timeAgo(job.date_posted || job.first_seen || "");
    const matchPct = job.match_score != null ? Math.round(job.match_score * 100) : null;
    const detailHref = `/jobs/${encodeURIComponent(String(job.id || job.internal_hash))}`;

    return (
        <article className="job-card group">
            <div className="mb-6 flex items-start justify-between gap-4">
                <CompanyLogo company={company} size="md" />
                {onSave && (
                    <button
                        onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            onSave(job);
                        }}
                        className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-bold transition ${
                            saved
                                ? "border-transparent bg-surface-3 text-ink"
                                : "border-border bg-white text-text-secondary hover:border-ink hover:text-ink"
                        }`}
                    >
                        {saved ? "Saved" : "Save"}
                        {saved ? <BookmarkCheck className="h-4 w-4 fill-ink" /> : <Bookmark className="h-4 w-4" />}
                    </button>
                )}
            </div>

            <div className="mb-4">
                <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
                    <span className="font-black text-ink">{company}</span>
                    {time && <span className="font-medium text-text-secondary">{time}</span>}
                </div>
                <Link href={detailHref} className="block">
                    <h3 className="line-clamp-2 min-h-[3.6rem] text-[1.45rem] font-black leading-[1.12] tracking-[-0.04em] text-ink transition-colors group-hover:text-orange-900">
                        {title}
                    </h3>
                </Link>
            </div>

            <div className="mb-5 flex min-h-[2.25rem] flex-wrap gap-2">
                {category && <span className="pill pill-accent">{category}</span>}
                {job.location && <span className="pill pill-white">{job.location.length > 24 ? `${job.location.slice(0, 24)}...` : job.location}</span>}
                {matchPct !== null && <span className="pill pill-white">{matchPct}% match</span>}
            </div>

            <div className="mt-auto border-t border-border pt-4">
                <div className="flex items-end justify-between gap-4">
                    <div className="min-w-0">
                        <p className="flex items-center gap-1.5 truncate text-xs font-bold text-ink">
                            <MapPin className="h-3.5 w-3.5 shrink-0" />
                            {job.location || "Location not listed"}
                        </p>
                        <p className="mt-1 text-xs font-medium text-text-secondary">{sourceLabel(job.source_ats)}</p>
                    </div>
                    <a
                        href={job.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-ink px-4 py-2.5 text-xs font-bold text-white transition hover:bg-orange-950"
                    >
                        Apply now
                        <ExternalLink className="h-4 w-4" />
                    </a>
                </div>
            </div>
        </article>
    );
}
