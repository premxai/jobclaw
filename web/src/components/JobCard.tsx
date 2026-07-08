import Link from "next/link";
import { ArrowRight, Bookmark, BookmarkCheck, CheckCircle2, Clock3, MapPin } from "lucide-react";
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

function compactLocation(location?: string | null): string {
    if (!location) return "San Francisco, CA · Remote";
    const normalized = location.replace(/\s+/g, " ").trim();
    if (normalized.length <= 30) return normalized;
    return `${normalized.slice(0, 30)}...`;
}

function workStyle(location?: string | null): string {
    const value = (location || "").toLowerCase();
    if (value.includes("hybrid")) return "Hybrid";
    if (value.includes("remote")) return "Remote";
    return "Remote";
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
    const detailHref = `/jobs/${encodeURIComponent(String(job.id || job.internal_hash))}`;
    const categoryLabel = category || (title.toLowerCase().includes("data") ? "Data" : title.toLowerCase().includes("engineer") ? "SWE" : "AI/ML");

    return (
        <article className="group relative min-h-[200px] rounded-lg border border-[#E7D7B7] bg-[#FFF7E5] p-5 shadow-[0_8px_18px_rgba(70,45,16,0.08)] transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_14px_28px_rgba(70,45,16,0.11)] [background-image:linear-gradient(rgba(255,247,229,0.78),rgba(255,247,229,0.78)),url('/nori-assets/paper-texture.png')] [background-size:cover]">
            <span className="absolute left-1/2 top-[-7px] h-[18px] w-[18px] -translate-x-1/2 rounded-full bg-[#C99635] shadow-[0_4px_8px_rgba(77,48,18,0.24),inset_0_1px_2px_rgba(255,255,255,0.55)]" />
            <div className="flex items-start justify-between gap-4">
                <CompanyLogo company={company} size="md" shape="rounded" />
                {onSave && (
                    <div className="flex items-center gap-3">
                        <button
                            onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                onSave(job);
                            }}
                            className="grid h-8 w-8 place-items-center rounded-lg text-[#263A22] transition hover:bg-[#EEF1DD] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#526736]"
                            aria-label="Save role"
                        >
                            {saved ? <BookmarkCheck className="h-5 w-5 fill-[#526736] text-[#526736]" /> : <Bookmark className="h-5 w-5" />}
                        </button>
                        <button
                            type="button"
                            className="inline-flex h-[30px] items-center gap-1.5 rounded-[9px] border border-[#8A946A] bg-[#F6F2E5] px-3 text-xs font-bold text-[#526736]"
                            aria-label="Mark as applied"
                        >
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            Applied
                        </button>
                    </div>
                )}
            </div>

            <div className="mt-4">
                <Link href={detailHref} className="block">
                    <h3 className="line-clamp-2 font-serif text-xl font-bold leading-[1.1] tracking-[-0.035em] text-[#1F281B] transition-colors group-hover:text-[#526736]">
                        {title}
                    </h3>
                </Link>
                <p className="mt-1 text-sm font-medium text-[#1F281B]">{company}</p>
            </div>

            <div className="mt-2 space-y-1.5 text-xs text-[#5F665C]">
                <p className="flex items-center gap-1.5">
                    <MapPin className="h-[13px] w-[13px]" />
                    {compactLocation(job.location)}
                </p>
                <p className="flex items-center gap-1.5">
                    <Clock3 className="h-[13px] w-[13px]" />
                    Found {time || "recently"}
                </p>
            </div>

            <div className="mt-3 flex flex-wrap gap-2 pr-8">
                <span className="inline-flex h-6 items-center rounded-full border border-[#E1D2AD] bg-[#F7EED7] px-2.5 text-[11px] font-semibold text-[#4A513C]">
                    {categoryLabel}
                </span>
                <span className="inline-flex h-6 items-center rounded-full border border-[#E1D2AD] bg-[#F7EED7] px-2.5 text-[11px] font-semibold text-[#4A513C]">
                    {workStyle(job.location)}
                </span>
            </div>

            <a
                href={job.url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="absolute bottom-[18px] right-[18px] text-[#526736] transition group-hover:translate-x-0.5 hover:text-[#263A22]"
                aria-label="Open application link"
            >
                <ArrowRight className="h-5 w-5" />
            </a>
        </article>
    );
}
