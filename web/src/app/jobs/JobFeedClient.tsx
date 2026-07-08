"use client";

import Image from "next/image";
import Link from "next/link";
import type React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarDays, ChevronDown, Clock3, Grid2X2, LayoutDashboard, LogOut, MapPin, Search, SlidersHorizontal, UserCircle } from "lucide-react";
import JobCard, { Job } from "@/components/JobCard";
import NoriAppSidebar from "@/components/NoriAppSidebar";
import NoriMark from "@/components/landing/NoriMark";
import { FILTER_CATEGORIES } from "@/components/SearchFilterBar";
import { fetchJobs, fetchMatchedJobs } from "@/lib/api";
import { displayCompany, displayTitle, companySlug } from "@/lib/job-display";
import { isUsLocation } from "@/lib/location-filters";

export type SortMode = "recency" | "relevance";
export const MIN_RELEVANCE_QUERY_LENGTH = 3;

interface SavedJobRef {
    internal_hash: string;
    status?: string | null;
}

const LIMIT = 12;
const WORKING_SET_LIMIT = 120;

function getPageNumbers(current: number, totalPages: number): (number | "...")[] {
    if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i + 1);
    const pages: (number | "...")[] = [1];
    if (current > 3) pages.push("...");
    for (let p = Math.max(2, current - 1); p <= Math.min(totalPages - 1, current + 1); p++) pages.push(p);
    if (current < totalPages - 2) pages.push("...");
    pages.push(totalPages);
    return pages;
}

function jobSearchText(job: Job): string {
    return `${displayTitle(job)} ${job.title} ${displayCompany(job)} ${job.company} ${job.location || ""} ${job.source_ats || ""} ${parseSkillTags(job).join(" ")} ${job.description || ""}`.toLowerCase();
}

function normalizeSearch(value: string): string {
    return value.toLowerCase().replace(/[^a-z0-9+#./-]+/g, " ").replace(/\s+/g, " ").trim();
}

function parseSkillTags(job: Job): string[] {
    let tags: string[] = [];
    try {
        const parsed = JSON.parse(job.keywords_matched || "[]");
        if (Array.isArray(parsed)) tags = parsed.map((tag) => String(tag));
    } catch {
        tags = (job.keywords_matched || "").split(",");
    }

    const blocked = /\b(remote|hybrid|onsite|on-site|united states|usa|us|direct apply|full[- ]?time|contract|internship)\b/i;
    return tags.map((tag) => tag.replace(/\s+/g, " ").trim()).filter(Boolean).filter((tag) => !blocked.test(tag));
}

function matchesSearchQuery(job: Job, query: string): boolean {
    const tokens = normalizeSearch(query).split(" ").filter(Boolean);
    if (tokens.length === 0) return true;
    const haystack = normalizeSearch(jobSearchText(job));
    return tokens.every((token) => haystack.includes(token));
}

function matchesCategory(job: Job, selected: Set<string>): boolean {
    if (selected.size === 0) return true;
    const tags = parseSkillTags(job).map((tag) => tag.toLowerCase());
    return Array.from(selected).some((category) => tags.includes(category.toLowerCase()));
}

interface CompanyJobGroup {
    key: string;
    company: string;
    jobs: Job[];
}

function sortByFreshness(a: Job, b: Job): number {
    const aTime = new Date(a.first_seen || a.date_posted || 0).getTime() || 0;
    const bTime = new Date(b.first_seen || b.date_posted || 0).getTime() || 0;
    return bTime - aTime;
}

function groupCompanyJobs(jobs: Job[]): CompanyJobGroup[] {
    const groups = new Map<string, CompanyJobGroup>();
    jobs.forEach((job) => {
        const company = displayCompany(job);
        const key = companySlug(company) || company.toLowerCase();
        const existing = groups.get(key);
        if (existing) existing.jobs.push(job);
        else groups.set(key, { key, company, jobs: [job] });
    });

    return Array.from(groups.values())
        .map((group) => ({ ...group, jobs: group.jobs.sort(sortByFreshness) }))
        .sort((a, b) => sortByFreshness(a.jobs[0], b.jobs[0]));
}

function matchesExperience(job: Job, level: string): boolean {
    if (level === "any") return true;
    const text = jobSearchText(job);
    if (level === "junior") return /\b(junior|jr\.?|entry|new grad|university|graduate|intern)\b/.test(text);
    if (level === "mid") return !/\b(senior|sr\.?|staff|principal|lead|manager|director|vp|junior|jr\.?|intern|new grad)\b/.test(text);
    if (level === "senior") return /\b(senior|sr\.?|staff|principal|lead)\b/.test(text);
    return true;
}

function matchesEmploymentType(job: Job, type: string): boolean {
    if (type === "all") return true;
    const text = jobSearchText(job);
    if (type === "full-time") return /\b(full[- ]?time|permanent)\b/.test(text) || !/\b(contract|intern|internship|temporary|part[- ]?time)\b/.test(text);
    if (type === "contract") return /\b(contract|contractor|temporary|freelance)\b/.test(text);
    if (type === "internship") return /\b(intern|internship|co-op|summer)\b/.test(text);
    return true;
}

const recencyOptions = [
    { label: "Any time", value: "all", hours: null as number | null },
    { label: "Last hour", value: "1", hours: 1 },
    { label: "Last 24h", value: "24", hours: 24 },
    { label: "Last 48h", value: "48", hours: 48 },
];

function LockPrompt({ onClose }: { onClose: () => void }) {
    return (
        <div className="fixed inset-0 z-50 grid place-items-center bg-[#1F281B]/35 px-5 backdrop-blur-sm">
            <section className="w-full max-w-md rounded-[24px] border border-[#E7D7B7] bg-[#FFF9EC] p-6 text-center shadow-[0_24px_60px_rgba(60,42,16,0.22)]">
                <p className="mb-2 font-serif text-3xl font-bold tracking-[-0.04em] text-[#1F281B]">Unlock Nori</p>
                <p className="text-sm font-medium leading-6 text-[#5F665C]">
                    Login or sign up to use filters, save roles, track applications, and browse beyond the first page.
                </p>
                <div className="mt-6 flex justify-center gap-3">
                    <Link href="/profile" className="inline-flex h-11 items-center rounded-xl bg-[#526736] px-5 text-sm font-bold text-white">
                        Login
                    </Link>
                    <Link href="/profile" className="inline-flex h-11 items-center rounded-xl border border-[#D8C9A7] px-5 text-sm font-bold text-[#1F281B]">
                        Sign up
                    </Link>
                    <button type="button" onClick={onClose} className="inline-flex h-11 items-center rounded-xl px-3 text-sm font-bold text-[#5F665C]">
                        Close
                    </button>
                </div>
            </section>
        </div>
    );
}

function LocalDateTime() {
    const [now, setNow] = useState<Date | null>(null);

    useEffect(() => {
        setNow(new Date());
        const timer = window.setInterval(() => setNow(new Date()), 30_000);
        return () => window.clearInterval(timer);
    }, []);

    if (!now) return null;

    return (
        <>
            <CalendarDays className="h-5 w-5" />
            {new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(now)}
            <span>·</span>
            {new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(now)}
        </>
    );
}

function ProfileMenu() {
    const [open, setOpen] = useState(false);

    return (
        <div className="relative order-2 block sm:order-3">
            <button type="button" onClick={() => setOpen((value) => !value)} className="flex items-center gap-3" aria-expanded={open} aria-haspopup="menu">
                <span className="grid h-12 w-12 place-items-center rounded-full bg-[#D9B08C] text-sm font-black text-[#1F281B] shadow-sm">AC</span>
                <span className="hidden leading-tight sm:block">
                    <span className="block text-[15px] font-bold text-[#1F281B]">Alex Chen</span>
                </span>
                <ChevronDown className={`h-4 w-4 text-[#526736] transition ${open ? "rotate-180" : ""}`} />
            </button>
            {open && (
                <div role="menu" className="absolute right-0 top-[calc(100%+14px)] w-48 rounded-2xl border border-[#E7D7B7] bg-[#FFF9EC] p-2 shadow-[0_18px_42px_rgba(70,45,16,0.16)]">
                    <Link href="/profile" role="menuitem" className="flex h-10 items-center gap-2 rounded-xl px-3 text-sm font-semibold text-[#1F281B] hover:bg-[#F7EED7]">
                        <UserCircle className="h-4 w-4 text-[#526736]" />
                        Profile
                    </Link>
                    <Link href="/profile" role="menuitem" className="flex h-10 items-center gap-2 rounded-xl px-3 text-sm font-semibold text-[#1F281B] hover:bg-[#F7EED7]">
                        <LogOut className="h-4 w-4 text-[#526736]" />
                        Logout
                    </Link>
                </div>
            )}
        </div>
    );
}

function TopAppHeader({ search, onSearchChange, locked, onLockedAction }: { search: string; onSearchChange: (value: string) => void; locked?: boolean; onLockedAction?: () => void }) {
    return (
        <header className="sticky top-0 z-20 flex min-h-24 flex-wrap items-center gap-4 border-b border-[#E7D7B7] bg-[#FFF9EC]/82 px-5 py-3 backdrop-blur-md sm:px-8 lg:ml-[280px]">
            <div className="order-1 flex h-14 min-w-[240px] flex-1 items-center gap-4 rounded-[14px] border border-[#D8C9A7] bg-[#FFF9EC] px-[22px] shadow-[0_4px_12px_rgba(70,45,16,0.04)] sm:max-w-[560px]">
                <Search className="h-[22px] w-[22px] shrink-0 text-[#0F2744]" />
                <input
                    value={search}
                    onFocus={() => locked && onLockedAction?.()}
                    onChange={(e) => {
                        if (locked) {
                            onLockedAction?.();
                            return;
                        }
                        onSearchChange(e.target.value);
                    }}
                    readOnly={locked}
                    placeholder="Search roles, companies, or skills..."
                    className="h-full min-w-0 flex-1 bg-transparent text-[15px] text-[#1F281B] placeholder:text-[#7B7F70] focus:outline-none"
                />
            </div>

            <div className="order-3 ml-auto flex w-full items-center justify-end gap-2.5 whitespace-nowrap text-xs font-medium text-[#1F281B] sm:order-2 sm:w-auto sm:text-sm">
                <LocalDateTime />
            </div>

            <div className="order-3 hidden h-11 w-px bg-[#E7D7B7] md:block" />

            <ProfileMenu />
        </header>
    );
}

function JobsHeroBanner() {
    return (
        <section className="relative min-h-[190px] overflow-hidden rounded-2xl border border-[#E7D7B7] bg-[#FFF9EC] px-6 py-9 shadow-[0_10px_24px_rgba(70,45,16,0.07)] [background-image:linear-gradient(rgba(255,249,236,0.80),rgba(255,249,236,0.80)),url('/nori-assets/paper-texture.png')] [background-size:cover] sm:px-12 sm:py-10">
            <div className="relative z-10 max-w-3xl">
                <h1 className="font-serif text-[34px] font-bold leading-[1.1] tracking-[-0.045em] text-[#12302A] sm:text-[42px]">
                    Fresh roles from Nori
                    <span className="ml-4 inline-block align-middle">
                        <NoriMark />
                    </span>
                </h1>
                <p className="mt-2.5 text-[17px] font-normal leading-[1.45] text-[#5F665C]">Live roles continuously found and posted by your agent.</p>
            </div>
            <span className="pointer-events-none absolute right-[330px] top-4 hidden h-36 w-36 rotate-12 opacity-95 drop-shadow-[0_14px_20px_rgba(70,45,16,0.16)] lg:block">
                <Image src="/nori-assets/coffee-cup.png" alt="" aria-hidden="true" fill sizes="144px" className="object-contain" />
            </span>
            <div className="pointer-events-none absolute right-20 top-5 hidden h-36 w-52 rotate-[-4deg] rounded-lg border border-[#E7D7B7] bg-[#FFF9EC] p-5 text-sm font-semibold leading-6 text-[#1F281B] shadow-[0_8px_18px_rgba(70,45,16,0.10)] [background-image:linear-gradient(rgba(255,249,236,0.82),rgba(255,249,236,0.82)),url('/nori-assets/paper-texture.png')] [background-size:cover] lg:block">
                Nori finds the signal. You focus on what&apos;s next.
            </div>
            <span className="pointer-events-none absolute right-8 top-2 hidden h-40 w-28 opacity-80 lg:block">
                <Image src="/nori-assets/dried-flowers.png" alt="" aria-hidden="true" fill sizes="112px" className="object-contain" />
            </span>
        </section>
    );
}

function FilterSelect({
    label,
    icon,
    value,
    onChange,
    children,
}: {
    label: string;
    icon: React.ReactNode;
    value: string;
    onChange: (value: string) => void;
    children: React.ReactNode;
}) {
    return (
        <label className="min-w-[170px] flex-1">
            <span className="mb-2 block text-[13px] font-semibold text-[#1F281B]">{label}</span>
            <span className="relative flex h-[42px] items-center rounded-[10px] border border-[#D8C9A7] bg-[#FFF9EC] text-sm font-medium text-[#1F281B]">
                <span className="pointer-events-none absolute left-3.5 text-[#526736]">{icon}</span>
                <select
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    className="h-full w-full appearance-none rounded-[10px] bg-transparent pl-10 pr-9 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-[#526736]"
                >
                    {children}
                </select>
                <ChevronDown className="pointer-events-none absolute right-3.5 h-4 w-4 text-[#1F281B]" />
            </span>
        </label>
    );
}

interface FilterBarProps {
    recentHours: number | null;
    onRecentHoursChange: (hours: number | null) => void;
    category: string;
    onCategoryChange: (value: string) => void;
    locationMode: string;
    onLocationChange: (value: string) => void;
    experienceLevel: string;
    onExperienceLevelChange: (value: string) => void;
    employmentType: string;
    onEmploymentTypeChange: (value: string) => void;
    onClear: () => void;
    onApply: () => void;
}

function JobsFilterBar({
    recentHours,
    onRecentHoursChange,
    category,
    onCategoryChange,
    locationMode,
    onLocationChange,
    experienceLevel,
    onExperienceLevelChange,
    employmentType,
    onEmploymentTypeChange,
    onClear,
    onApply,
}: FilterBarProps) {
    const recentValue = recencyOptions.find((option) => option.hours === recentHours)?.value ?? "all";

    return (
        <section className="flex min-h-[104px] flex-col gap-4 rounded-[14px] border border-[#E7D7B7] bg-[#FFF9EC]/90 px-[22px] py-[18px] shadow-[0_8px_18px_rgba(70,45,16,0.06)] xl:flex-row xl:items-center">
            <div className="grid flex-1 gap-[22px] md:grid-cols-2 xl:grid-cols-5">
                <FilterSelect label="Time posted" icon={<Clock3 className="h-[17px] w-[17px]" />} value={recentValue} onChange={(value) => onRecentHoursChange(recencyOptions.find((option) => option.value === value)?.hours ?? null)}>
                    {recencyOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                            {option.label}
                        </option>
                    ))}
                </FilterSelect>

                <FilterSelect label="Category" icon={<Grid2X2 className="h-[17px] w-[17px]" />} value={category} onChange={onCategoryChange}>
                    <option value="">All categories</option>
                    {FILTER_CATEGORIES.map((option) => (
                        <option key={option} value={option}>
                            {option}
                        </option>
                    ))}
                </FilterSelect>

                <FilterSelect label="Location" icon={<MapPin className="h-[17px] w-[17px]" />} value={locationMode} onChange={onLocationChange}>
                    <option value="us">United States</option>
                </FilterSelect>

                <FilterSelect label="Experience level" icon={<LayoutDashboard className="h-[17px] w-[17px]" />} value={experienceLevel} onChange={onExperienceLevelChange}>
                    <option value="any">Any level</option>
                    <option value="junior">Junior</option>
                    <option value="mid">Mid-level</option>
                    <option value="senior">Senior</option>
                </FilterSelect>

                <FilterSelect label="Employment type" icon={<CalendarDays className="h-[17px] w-[17px]" />} value={employmentType} onChange={onEmploymentTypeChange}>
                    <option value="all">All types</option>
                    <option value="full-time">Full-time</option>
                    <option value="contract">Contract</option>
                    <option value="internship">Internship</option>
                </FilterSelect>
            </div>

            <div className="flex shrink-0 items-end justify-end gap-5 xl:self-end">
                <button type="button" onClick={onClear} className="h-[46px] text-sm font-semibold text-[#526736] underline underline-offset-2">
                    Clear all
                </button>
                <button type="button" onClick={onApply} className="inline-flex h-[46px] items-center gap-2.5 rounded-[10px] bg-[#526736] px-[22px] text-[15px] font-bold text-[#FFF9EC] shadow-[0_8px_18px_rgba(38,58,34,0.15)]" aria-label="Filter roles">
                    <SlidersHorizontal className="h-4 w-4" />
                    Filters
                </button>
            </div>
        </section>
    );
}

export default function JobFeedClient({
    initialSearch,
    initialSortMode = "recency",
    previewLocked = false,
}: {
    initialSearch: string;
    initialSortMode?: SortMode;
    previewLocked?: boolean;
    headerExtra?: React.ReactNode;
}) {
    const [jobs, setJobs] = useState<Job[]>([]);
    const [total, setTotal] = useState(0);
    const [search, setSearch] = useState(initialSearch);
    const [selectedCategories, setSelectedCategories] = useState<Set<string>>(new Set());
    const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set());
    const [recentHours, setRecentHours] = useState<number | null>(null);
    const [experienceLevel, setExperienceLevel] = useState("any");
    const [employmentType, setEmploymentType] = useState("all");
    const [page, setPage] = useState(1);
    const [loading, setLoading] = useState(true);
    const [trackedStatuses, setTrackedStatuses] = useState<Record<string, string>>({});
    const [companyJobIndexes, setCompanyJobIndexes] = useState<Record<string, number>>({});
    const [sortMode, setSortMode] = useState<SortMode>(initialSortMode);
    const [showLockPrompt, setShowLockPrompt] = useState(false);
    const isRelevanceMode = sortMode === "relevance" && search.trim().length >= MIN_RELEVANCE_QUERY_LENGTH;
    const categoryValue = selectedCategories.size === 1 ? Array.from(selectedCategories)[0] : "";
    const locationMode = "us";
    const companyGroups = useMemo(() => groupCompanyJobs(jobs), [jobs]);
    const visibleCompanyGroups = useMemo(() => companyGroups.slice((page - 1) * LIMIT, page * LIMIT), [companyGroups, page]);

    useEffect(() => {
        if (sortMode === "relevance" && search.trim().length < MIN_RELEVANCE_QUERY_LENGTH) {
            setSortMode("recency");
        }
    }, [search, sortMode]);

    useEffect(() => {
        const saved = localStorage.getItem("jobclaw_saved");
        if (saved) {
            try {
                const parsed = JSON.parse(saved) as SavedJobRef[];
                setTrackedStatuses(
                    parsed.reduce<Record<string, string>>((acc, job) => {
                        acc[job.internal_hash] = (job.status || "saved").toLowerCase();
                        return acc;
                    }, {}),
                );
            } catch {}
        }
    }, []);

    const loadJobs = useCallback(async () => {
        setLoading(true);
        if (previewLocked) {
            const data = await fetchJobs({ page: 1, limit: WORKING_SET_LIMIT });
            const filtered = data.jobs.filter((job) => isUsLocation(job.location)).filter((job) => matchesSearchQuery(job, search));
            setJobs(filtered.slice(0, LIMIT));
            setTotal(groupCompanyJobs(filtered.slice(0, LIMIT)).length);
            setLoading(false);
            return;
        }
        const category = selectedCategories.size === 1 ? Array.from(selectedCategories)[0] : undefined;
        const source = selectedSources.size === 1 ? Array.from(selectedSources)[0].toLowerCase() : undefined;
        const data = isRelevanceMode
            ? await fetchMatchedJobs(search, WORKING_SET_LIMIT)
            : await fetchJobs({ search, page: 1, limit: WORKING_SET_LIMIT, category, source, recentHours: recentHours ?? undefined });
        let filtered = data.jobs;

        if (isRelevanceMode && recentHours !== null) {
            filtered = filtered.filter((j) => j.freshness_minutes == null || j.freshness_minutes <= recentHours * 60);
        }

        filtered = filtered.filter((j) => isUsLocation(j.location));
        filtered = filtered.filter((j) => matchesSearchQuery(j, search));
        if (experienceLevel !== "any") filtered = filtered.filter((j) => matchesExperience(j, experienceLevel));
        if (employmentType !== "all") filtered = filtered.filter((j) => matchesEmploymentType(j, employmentType));
        filtered = filtered.filter((j) => matchesCategory(j, selectedCategories));

        const groupedTotal = groupCompanyJobs(filtered).length;
        setJobs(filtered);
        setTotal(groupedTotal);
        if ((page - 1) * LIMIT >= groupedTotal) setPage(1);
        setLoading(false);
    }, [search, selectedCategories, selectedSources, recentHours, experienceLevel, employmentType, isRelevanceMode, previewLocked, page]);

    useEffect(() => {
        loadJobs();
    }, [loadJobs]);

    const handleSave = (job: Job) => {
        if (previewLocked) {
            setShowLockPrompt(true);
            return;
        }
        const saved = localStorage.getItem("jobclaw_saved");
        let arr: Job[] = [];
        try {
            arr = JSON.parse(saved || "[]");
        } catch {}
        const exists = arr.find((j) => j.internal_hash === job.internal_hash);
        arr = exists ? arr.filter((j) => j.internal_hash !== job.internal_hash) : [...arr, { ...job, status: "saved", updatedAt: new Date().toISOString() }];
        localStorage.setItem("jobclaw_saved", JSON.stringify(arr));
        setTrackedStatuses(
            arr.reduce<Record<string, string>>((acc, savedJob) => {
                acc[savedJob.internal_hash] = (savedJob.status || "saved").toLowerCase();
                return acc;
            }, {}),
        );
    };

    const handleApply = (job: Job) => {
        if (previewLocked) {
            setShowLockPrompt(true);
            return;
        }
        const saved = localStorage.getItem("jobclaw_saved");
        let arr: Job[] = [];
        try {
            arr = JSON.parse(saved || "[]");
        } catch {}
        const exists = arr.find((j) => j.internal_hash === job.internal_hash);
        arr = exists
            ? arr.map((j) => (j.internal_hash === job.internal_hash ? { ...j, status: "applied", updatedAt: new Date().toISOString() } : j))
            : [...arr, { ...job, status: "applied", addedAt: new Date().toISOString(), updatedAt: new Date().toISOString() }];
        localStorage.setItem("jobclaw_saved", JSON.stringify(arr));
        setTrackedStatuses(
            arr.reduce<Record<string, string>>((acc, savedJob) => {
                acc[savedJob.internal_hash] = (savedJob.status || "saved").toLowerCase();
                return acc;
            }, {}),
        );
        window.open(job.url, "_blank", "noopener,noreferrer");
    };

    const handleCategoryChange = (value: string) => {
        setSelectedCategories(value ? new Set([value]) : new Set());
        setPage(1);
    };

    const handleLocationChange = () => {
        setPage(1);
    };

    const clearFilters = () => {
        setSelectedCategories(new Set());
        setSelectedSources(new Set());
        setRecentHours(null);
        setExperienceLevel("any");
        setEmploymentType("all");
        setPage(1);
    };

    const handleNextCompanyJob = (group: CompanyJobGroup) => {
        setCompanyJobIndexes((current) => ({
            ...current,
            [group.key]: ((current[group.key] || 0) + 1) % group.jobs.length,
        }));
    };

    const totalPages = Math.max(1, Math.ceil(total / LIMIT));
    const start = total === 0 ? 0 : (page - 1) * LIMIT + 1;
    const end = Math.min(page * LIMIT, total);

    return (
        <div className="min-h-screen bg-[#FBF4E7] text-[#1F281B] [background-image:radial-gradient(circle_at_12%_22%,rgba(215,234,220,0.55),transparent_30%),radial-gradient(circle_at_88%_12%,rgba(246,218,158,0.45),transparent_28%),linear-gradient(135deg,#FBF4E7_0%,#F8ECD7_100%)]">
            {showLockPrompt && <LockPrompt onClose={() => setShowLockPrompt(false)} />}
            <NoriAppSidebar locked={previewLocked} onLockedAction={() => setShowLockPrompt(true)} />
            <TopAppHeader
                search={search}
                locked={previewLocked}
                onLockedAction={() => setShowLockPrompt(true)}
                onSearchChange={(value) => {
                    setSearch(value);
                    setPage(1);
                }}
            />

            <main className="px-5 py-6 sm:px-8 lg:ml-[280px] lg:p-8">
                <div className="space-y-6">
                    <JobsHeroBanner />
                    <div className={previewLocked ? "relative" : ""}>
                        {previewLocked && <button type="button" onClick={() => setShowLockPrompt(true)} aria-label="Unlock filters" className="absolute inset-0 z-10 rounded-[14px] cursor-not-allowed bg-transparent" />}
                        <div className={previewLocked ? "pointer-events-none opacity-55" : ""}>
                            <JobsFilterBar
                                recentHours={recentHours}
                                onRecentHoursChange={(hours) => {
                                    setRecentHours(hours);
                                    setPage(1);
                                }}
                                category={categoryValue}
                                onCategoryChange={handleCategoryChange}
                                locationMode={locationMode}
                                onLocationChange={handleLocationChange}
                                experienceLevel={experienceLevel}
                                onExperienceLevelChange={(value) => {
                                    setExperienceLevel(value);
                                    setPage(1);
                                }}
                                employmentType={employmentType}
                                onEmploymentTypeChange={(value) => {
                                    setEmploymentType(value);
                                    setPage(1);
                                }}
                                onClear={clearFilters}
                                onApply={loadJobs}
                            />
                        </div>
                    </div>

                    {loading ? (
                        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                            {Array.from({ length: LIMIT }).map((_, index) => (
                                <div key={index} className="h-[200px] animate-pulse rounded-lg border border-[#E7D7B7] bg-[#FFF9EC]" />
                            ))}
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                            {visibleCompanyGroups.map((group, index) => {
                                const groupJobIndex = companyJobIndexes[group.key] || 0;
                                const job = group.jobs[groupJobIndex] || group.jobs[0];
                                const status = trackedStatuses[job.internal_hash];
                                return (
                                    <div key={group.key} className="animate-fade-in" style={{ animationDelay: `${index * 25}ms` }}>
                                        <JobCard
                                            job={job}
                                            onSave={handleSave}
                                            onApply={handleApply}
                                            onNextCompanyJob={() => handleNextCompanyJob(group)}
                                            saved={Boolean(status)}
                                            applied={status === "applied"}
                                            companyJobCount={group.jobs.length}
                                            companyJobIndex={groupJobIndex}
                                        />
                                    </div>
                                );
                            })}
                        </div>
                    )}

                    {!loading && companyGroups.length === 0 && (
                        <div className="rounded-2xl border border-[#E7D7B7] bg-[#FFF9EC]/82 py-20 text-center shadow-[0_10px_24px_rgba(70,45,16,0.07)]">
                            <p className="mb-2 font-serif text-2xl font-bold text-[#1F281B]">No roles found</p>
                            <p className="text-[#5F665C]">Try adjusting your search or filters.</p>
                        </div>
                    )}

                    {!isRelevanceMode && total > LIMIT && (
                        <footer className="pt-1 text-center">
                            <div className="flex flex-wrap items-center justify-center gap-3.5">
                                <button
                                    onClick={() => setPage(Math.max(1, page - 1))}
                                    disabled={page === 1}
                                    className="inline-flex h-[42px] items-center gap-2 rounded-[9px] border border-[#E7D7B7] bg-[#FFF9EC] px-[18px] text-sm font-medium text-[#1F281B] disabled:opacity-45"
                                    aria-label="Previous page"
                                >
                                    <ChevronDown className="h-4 w-4 rotate-90" />
                                    Previous
                                </button>
                                {getPageNumbers(page, totalPages).map((pageNumber, index) =>
                                    pageNumber === "..." ? (
                                        <span key={`ellipsis-${index}`} className="grid h-[42px] w-[42px] place-items-center text-sm text-[#7B7F70]">
                                            ...
                                        </span>
                                    ) : (
                                        <button
                                            key={pageNumber}
                                            onClick={() => setPage(pageNumber)}
                                            aria-current={pageNumber === page ? "page" : undefined}
                                            className={`h-[42px] w-[42px] rounded-[9px] text-sm font-medium transition ${
                                                pageNumber === page ? "bg-[#526736] text-[#FFF9EC]" : "text-[#1F281B] hover:bg-[#FFF9EC]"
                                            }`}
                                        >
                                            {pageNumber}
                                        </button>
                                    ),
                                )}
                                <button
                                    onClick={() => setPage(page + 1)}
                                    disabled={page >= totalPages}
                                    className="inline-flex h-[42px] items-center gap-2 rounded-[9px] border border-[#E7D7B7] bg-[#FFF9EC] px-[18px] text-sm font-medium text-[#1F281B] disabled:opacity-45"
                                    aria-label="Next page"
                                >
                                    Next
                                    <ChevronDown className="h-4 w-4 -rotate-90" />
                                </button>
                            </div>
                            <p className="mt-3 text-sm text-[#7B7F70]">Showing {start}-{end} of {total} roles</p>
                        </footer>
                    )}
                </div>
            </main>
        </div>
    );
}
