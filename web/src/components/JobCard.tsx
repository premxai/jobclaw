import { ArrowRight, Bookmark, BookmarkCheck, CheckCircle2, ChevronRight, MapPin } from "lucide-react";
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
        <article className="group relative flex h-[220px] flex-col rounded-lg border border-[#E7D7B7] bg-[#FFF7E5] p-4 shadow-[0_8px_18px_rgba(70,45,16,0.08)] transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_14px_28px_rgba(70,45,16,0.11)] [background-image:linear-gradient(rgba(255,247,229,0.78),rgba(255,247,229,0.78)),url('/nori-assets/paper-texture.png')] [background-size:cover] sm:h-[248px] sm:p-5 xl:h-[288px] xl:p-6">
            <span className="absolute left-1/2 top-[-7px] h-[18px] w-[18px] -translate-x-1/2 rounded-full bg-[#C99635] shadow-[0_4px_8px_rgba(77,48,18,0.24),inset_0_1px_2px_rgba(255,255,255,0.55)]" />
            <div className="flex items-start justify-between gap-3 sm:gap-4">
                <CompanyLogo company={company} size="md" shape="rounded" />
                {onSave && (
                    <div className="flex items-center gap-2">
                        <button
                            onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                onSave(job);
                            }}
                            className="grid h-7 w-7 place-items-center rounded-lg text-[#263A22] transition hover:bg-[#EEF1DD] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#526736] sm:h-8 sm:w-8"
                            aria-label="Save role"
                        >
                            {saved ? <BookmarkCheck className="h-4 w-4 fill-[#526736] text-[#526736] sm:h-5 sm:w-5" /> : <Bookmark className="h-4 w-4 sm:h-5 sm:w-5" />}
                        </button>
                    </div>
                )}
            </div>

            <div className="mt-3 sm:mt-4 xl:mt-5">
                <a href={job.url} target="_blank" rel="noopener noreferrer" className="block" aria-label="Open application link">
                    <h3 className="line-clamp-2 font-serif text-[17px] font-bold leading-[1.08] tracking-[-0.035em] text-[#1F281B] transition-colors group-hover:text-[#526736] sm:text-xl sm:leading-[1.1] xl:text-2xl xl:leading-[1.02]">
                        {title}
                    </h3>
                </a>
                <p className="mt-1 line-clamp-1 text-[12px] font-medium text-[#1F281B] sm:text-sm xl:text-base">{company}</p>
            </div>

            <div className="mt-2 text-[11px] text-[#5F665C] sm:text-xs xl:mt-3 xl:text-sm">
                <p className="flex items-center gap-1.5">
                    <MapPin className="h-[13px] w-[13px] xl:h-4 xl:w-4" />
                    {compactLocation(job.location)}
                </p>
            </div>

            <div className="mt-auto flex flex-wrap gap-1.5 pr-9 pt-3 sm:gap-2 sm:pr-10 sm:pt-4 xl:pr-12">
                {skillTags.map((tag) => (
                    <span key={tag} className="inline-flex h-5 items-center rounded-full border border-[#E1D2AD] bg-[#F7EED7] px-2 text-[10px] font-semibold text-[#4A513C] sm:h-6 sm:px-2.5 sm:text-[11px] xl:h-7 xl:px-3 xl:text-xs">
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
                    className="absolute right-[-10px] top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-full border border-[#D8C9A7] bg-[#FFF9EC] text-[#526736] shadow-[0_8px_18px_rgba(70,45,16,0.14)] transition hover:translate-x-0.5 hover:bg-[#F7EED7] sm:right-[-13px] sm:h-8 sm:w-8"
                    aria-label={`Show next ${company} role`}
                >
                    <ChevronRight className="h-4 w-4 sm:h-5 sm:w-5" />
                    <span className="sr-only">
                        {companyJobIndex + 1} of {companyJobCount}
                    </span>
                </button>
            )}

            <button
                type="button"
                onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onApply?.(job);
                }}
                className={`absolute bottom-3 right-3 grid h-8 w-8 place-items-center rounded-full transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#526736] sm:bottom-[18px] sm:right-[18px] sm:h-9 sm:w-9 xl:bottom-6 xl:right-6 ${
                    applied ? "bg-[#E8ECD9] text-[#526736]" : "text-[#526736] hover:translate-x-0.5 hover:bg-[#F7EED7] hover:text-[#263A22]"
                }`}
                aria-label="Apply to role"
            >
                {applied ? <CheckCircle2 className="h-5 w-5" /> : <ArrowRight className="h-5 w-5 sm:h-6 sm:w-6" />}
            </button>
        </article>
    );
}
