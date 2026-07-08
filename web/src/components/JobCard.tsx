import { ArrowRight, Bookmark, BookmarkCheck, CheckCircle2, ChevronRight, MapPin, Send } from "lucide-react";
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
    addedAt?: string | null;
    updatedAt?: string | null;
    freshness_minutes?: number | null;
    match_score?: number | null;
}

function getSkillTags(keywords?: string | null, title = ""): string[] {
    let tags: string[] = [];
    if (keywords) {
        try {
            const parsed = JSON.parse(keywords);
            if (Array.isArray(parsed)) tags = parsed.map((tag) => String(tag));
        } catch {
            tags = keywords.split(",");
        }
    }

    const blocked = /\b(remote|hybrid|onsite|on-site|united states|usa|us|direct apply|full[- ]?time|contract|internship)\b/i;
    const clean = tags
        .map((tag) => tag.replace(/\s+/g, " ").trim())
        .filter(Boolean)
        .filter((tag) => !blocked.test(tag));

    if (clean.length > 0) return Array.from(new Set(clean)).slice(0, 3);

    const lowerTitle = title.toLowerCase();
    if (/\b(data|analytics|scientist)\b/.test(lowerTitle)) return ["Data"];
    if (/\b(product|pm)\b/.test(lowerTitle)) return ["Product"];
    if (/\b(design|ux|ui)\b/.test(lowerTitle)) return ["Design"];
    if (/\b(ai|ml|machine learning|research)\b/.test(lowerTitle)) return ["AI/ML"];
    return ["SWE"];
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
    if (!location) return "United States";
    const normalized = location.replace(/\s+/g, " ").trim();
    if (normalized.length <= 34) return normalized;
    return `${normalized.slice(0, 34)}...`;
}

interface JobCardProps {
    job: Job;
    onSave?: (job: Job) => void;
    onApply?: (job: Job) => void;
    onNextCompanyJob?: () => void;
    saved?: boolean;
    applied?: boolean;
    companyJobCount?: number;
    companyJobIndex?: number;
}

export default function JobCard({
    job,
    onSave,
    onApply,
    onNextCompanyJob,
    saved = false,
    applied = false,
    companyJobCount = 1,
    companyJobIndex = 0,
}: JobCardProps) {
    const company = displayCompany(job);
    const title = displayTitle(job);
    const skillTags = getSkillTags(job.keywords_matched, title);

    return (
        <article className="group relative flex h-[238px] flex-col rounded-lg border border-[#E7D7B7] bg-[#FFF7E5] p-5 shadow-[0_8px_18px_rgba(70,45,16,0.08)] transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_14px_28px_rgba(70,45,16,0.11)] [background-image:linear-gradient(rgba(255,247,229,0.78),rgba(255,247,229,0.78)),url('/nori-assets/paper-texture.png')] [background-size:cover]">
            <span className="absolute left-1/2 top-[-7px] h-[18px] w-[18px] -translate-x-1/2 rounded-full bg-[#C99635] shadow-[0_4px_8px_rgba(77,48,18,0.24),inset_0_1px_2px_rgba(255,255,255,0.55)]" />
            <div className="flex items-start justify-between gap-4">
                <CompanyLogo company={company} size="md" shape="rounded" />
                {onSave && (
                    <div className="flex items-center gap-2">
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
                            onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                onApply?.(job);
                            }}
                            className={`grid h-8 w-8 place-items-center rounded-lg transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#526736] ${
                                applied ? "bg-[#E8ECD9] text-[#526736]" : "text-[#263A22] hover:bg-[#EEF1DD]"
                            }`}
                            aria-label="Apply and add role to tracker"
                        >
                            {applied ? <CheckCircle2 className="h-5 w-5" /> : <Send className="h-[18px] w-[18px]" />}
                        </button>
                    </div>
                )}
            </div>

            <div className="mt-4">
                <a href={job.url} target="_blank" rel="noopener noreferrer" className="block" aria-label="Open application link">
                    <h3 className="line-clamp-2 font-serif text-xl font-bold leading-[1.1] tracking-[-0.035em] text-[#1F281B] transition-colors group-hover:text-[#526736]">
                        {title}
                    </h3>
                </a>
                <p className="mt-1 text-sm font-medium text-[#1F281B]">{company}</p>
            </div>

            <div className="mt-2 text-xs text-[#5F665C]">
                <p className="flex items-center gap-1.5">
                    <MapPin className="h-[13px] w-[13px]" />
                    {compactLocation(job.location)}
                </p>
            </div>

            <div className="mt-auto flex flex-wrap gap-2 pr-10 pt-4">
                {skillTags.map((tag) => (
                    <span key={tag} className="inline-flex h-6 items-center rounded-full border border-[#E1D2AD] bg-[#F7EED7] px-2.5 text-[11px] font-semibold text-[#4A513C]">
                        {tag}
                    </span>
                ))}
            </div>

            {companyJobCount > 1 && (
                <button
                    type="button"
                    onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        onNextCompanyJob?.();
                    }}
                    className="absolute right-[-13px] top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-full border border-[#D8C9A7] bg-[#FFF9EC] text-[#526736] shadow-[0_8px_18px_rgba(70,45,16,0.14)] transition hover:translate-x-0.5 hover:bg-[#F7EED7]"
                    aria-label={`Show next ${company} role`}
                >
                    <ChevronRight className="h-5 w-5" />
                    <span className="sr-only">
                        {companyJobIndex + 1} of {companyJobCount}
                    </span>
                </button>
            )}

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
