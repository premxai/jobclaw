import type { Job } from "@/components/JobCard";

function cleanWhitespace(value?: string | null): string {
    return (value || "").replace(/\s+/g, " ").trim();
}

export function displayCompany(job: Pick<Job, "company" | "canonical_company">): string {
    const canonical = cleanWhitespace(job.canonical_company);
    const fallback = cleanWhitespace(job.company);
    return canonical || fallback || "Unknown company";
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
