import type { Job } from "@/components/JobCard";

function cleanWhitespace(value?: string | null): string {
    return (value || "")
        .replace(/\*\*/g, "")
        .replace(/__/g, "")
        .replace(/`/g, "")
        .replace(/\s+/g, " ")
        .trim();
}

const COMPANY_ALIASES: Record<string, string> = {
    cargurus: "CarGurus",
    clearstreet: "Clear Street",
    datasystemsanalystsinc: "Data Systems Analysts, Inc.",
    guidepointsecurity: "GuidePoint Security",
    parachutehealth: "Parachute Health",
    ttecdigital: "TTEC Digital",
};

function companyIdentity(value: string): string {
    return value.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function formatCompanyName(value: string): string {
    const cleaned = cleanWhitespace(value);
    if (!cleaned) return "Unknown company";

    const roleLikePrefix = /\b(analyst|engineer|manager|designer|developer|specialist|coordinator|director|intern|scientist|recruiter|associate)\b/i;
    const atParts = cleaned.split(/\s+@\s+/);
    const candidate = atParts.length === 2 && roleLikePrefix.test(atParts[0]) ? atParts[1] : cleaned;
    return COMPANY_ALIASES[companyIdentity(candidate)] || candidate.replace(/([a-z])([A-Z])/g, "$1 $2");
}

export function displayCompany(job: Pick<Job, "company" | "canonical_company">): string {
    const canonical = cleanWhitespace(job.canonical_company);
    const fallback = cleanWhitespace(job.company);
    return formatCompanyName(canonical || fallback);
}

export function displayTitle(job: Pick<Job, "title" | "canonical_title">): string {
    const canonical = cleanWhitespace(job.canonical_title);
    const fallback = cleanWhitespace(job.title);
    return canonical || fallback || "Untitled role";
}

export function companySlug(company: string): string {
    return cleanWhitespace(company)
        .toLowerCase()
        .replace(/&/g, "and")
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/(^-|-$)/g, "");
}

export function initialsFor(company: string): string {
    const words = cleanWhitespace(company)
        .split(" ")
        .filter(Boolean)
        .slice(0, 2);
    if (words.length === 0) return "N";
    return words.map((word) => word[0]?.toUpperCase()).join("");
}
