"use client";

import Image from "next/image";
import Link from "next/link";
import type React from "react";
import { useCallback, useEffect, useState } from "react";
import {
    ArrowRight,
    Bookmark,
    CalendarDays,
    ChevronDown,
    Clock3,
    Globe2,
    Grid2X2,
    LayoutDashboard,
    MapPin,
    Search,
    Settings,
    SlidersHorizontal,
    Star,
} from "lucide-react";
import JobCard, { Job } from "@/components/JobCard";
import NoriMark from "@/components/landing/NoriMark";
import { FILTER_CATEGORIES } from "@/components/SearchFilterBar";
import { fetchJobs, fetchMatchedJobs } from "@/lib/api";
import { isRemoteLocation, isUsLocation } from "@/lib/location-filters";

export type SortMode = "recency" | "relevance";
export const MIN_RELEVANCE_QUERY_LENGTH = 3;

interface SavedJobRef {
    internal_hash: string;
}

const LIMIT = 12;

function getPageNumbers(current: number, totalPages: number): (number | "...")[] {
    if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i + 1);
    const pages: (number | "...")[] = [1];
    if (current > 3) pages.push("...");
    for (let p = Math.max(2, current - 1); p <= Math.min(totalPages - 1, current + 1); p++) pages.push(p);
    if (current < totalPages - 2) pages.push("...");
    pages.push(totalPages);
    return pages;
}

const navItems = [
    { label: "Live Feed", href: "/jobs", icon: CalendarDays, active: true },
    { label: "Matches", href: "/jobs?mode=relevance", icon: Star },
    { label: "Saved Roles", href: "/tracker", icon: Bookmark },
    { label: "Sources", href: "/companies", icon: Globe2 },
];

const recencyOptions = [
    { label: "Any time", value: "all", hours: null as number | null },
    { label: "Last hour", value: "1", hours: 1 },
    { label: "Last 24h", value: "24", hours: 24 },
    { label: "Last 48h", value: "48", hours: 48 },
];

function DashboardSidebar() {
    return (
        <aside className="fixed inset-y-0 left-0 z-30 hidden w-[280px] border-r border-[#E7D7B7] bg-[#FFF8EA] px-[18px] py-7 lg:flex lg:flex-col">
            <Link href="/" className="mb-[46px] flex items-center gap-3" aria-label="Nori home">
                <NoriMark />
                <span className="font-serif text-[34px] font-bold leading-none tracking-[-0.04em] text-[#1F281B]">Nori</span>
            </Link>

            <nav className="space-y-2.5">
                {navItems.map(({ label, href, icon: Icon, active }) => (
                    <Link
                        key={label}
                        href={href}
                        className={`flex h-14 items-center gap-3.5 rounded-[14px] px-[18px] text-[17px] transition ${
                            active ? "bg-[#EEF1DD] font-bold text-[#526736]" : "font-medium text-[#1F281B] hover:bg-[#FFF9EC]"
                        }`}
                    >
                        <Icon className="h-6 w-6" />
                        {label}
                    </Link>
                ))}
            </nav>

            <div className="mx-2 my-7 border-t border-[#E7D7B7]" />

            <Link href="/profile" className="flex h-14 items-center gap-3.5 rounded-[14px] px-[18px] text-[17px] font-medium text-[#1F281B] transition hover:bg-[#FFF9EC]">
                <Settings className="h-6 w-6" />
                Settings
            </Link>

            <div className="mt-auto">
                <div className="mb-8 rounded-[18px] border border-[#E7D7B7] bg-[#FFF9EC]/80 p-[18px] shadow-[0_8px_18px_rgba(70,45,16,0.06)]">
                    <div className="flex items-start gap-3">
                        <NoriMark />
                        <p className="text-[15px] font-medium leading-6 text-[#1F281B]">Nori is quietly scouting the best roles for you.</p>
                    </div>
                    <Link href="/#how-it-works" className="mt-3 inline-flex items-center gap-2 text-[15px] font-semibold text-[#526736]">
                        How it works
                        <ArrowRight className="h-4 w-4" />
                    </Link>
                </div>

                <div className="relative -ml-12 h-80 overflow-hidden">
                    <div className="absolute bottom-0 left-0 h-64 w-48 -rotate-12 rounded-[20px] border border-[#526736]/35 bg-[#526736] shadow-[0_18px_34px_rgba(70,45,16,0.18)] [background-image:linear-gradient(rgba(82,103,54,0.42),rgba(82,103,54,0.42)),url('/nori-assets/notebook-texture.png')] [background-size:cover]" />
                    <span className="absolute bottom-12 left-28 h-48 w-40 rotate-12 opacity-80">
                        <Image src="/nori-assets/dried-flowers.png" alt="" aria-hidden="true" fill sizes="160px" className="object-contain" />
                    </span>
                </div>
            </div>
        </aside>
    );
}

function TopAppHeader({ search, onSearchChange }: { search: string; onSearchChange: (value: string) => void }) {
    return (
        <header className="sticky top-0 z-20 flex min-h-24 items-center gap-6 border-b border-[#E7D7B7] bg-[#FFF9EC]/82 px-5 backdrop-blur-md sm:px-8 lg:ml-[280px]">
            <div className="flex h-14 w-full max-w-[820px] items-center gap-4 rounded-[14px] border border-[#D8C9A7] bg-[#FFF9EC] px-[22px] shadow-[0_4px_12px_rgba(70,45,16,0.04)]">
                <Search className="h-[22px] w-[22px] shrink-0 text-[#0F2744]" />
                <input
                    value={search}
                    onChange={(e) => onSearchChange(e.target.value)}
                    placeholder="Search roles, companies, or skills..."
                    className="h-full min-w-0 flex-1 bg-transparent text-[15px] text-[#1F281B] placeholder:text-[#7B7F70] focus:outline-none"
                />
            </div>

            <div className="ml-auto hidden items-center gap-2.5 text-[15px] font-medium text-[#1F281B] xl:flex">
                <CalendarDays className="h-5 w-5" />
                May 15, 2025
                <span>·</span>
                10:24 AM
            </div>

            <div className="hidden h-11 w-px bg-[#E7D7B7] xl:block" />

            <Link href="/profile" className="hidden items-center gap-3 xl:flex">
                <span className="grid h-12 w-12 place-items-center rounded-full bg-[#D9B08C] text-sm font-black text-[#1F281B] shadow-sm">AC</span>
                <span className="leading-tight">
                    <span className="block text-[15px] font-bold text-[#1F281B]">Alex Chen</span>
                    <span className="block text-[13px] font-medium text-[#5F665C]">Premium Scout</span>
                </span>
                <ChevronDown className="h-4 w-4 text-[#526736]" />
            </Link>
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
                    <option value="all">All locations</option>
                    <option value="us">United States</option>
                    <option value="remote">Remote</option>
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
                <button type="button" className="inline-flex h-[46px] items-center gap-2.5 rounded-[10px] bg-[#526736] px-[22px] text-[15px] font-bold text-[#FFF9EC] shadow-[0_8px_18px_rgba(38,58,34,0.15)]" aria-label="Filter roles">
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
}: {
    initialSearch: string;
    initialSortMode?: SortMode;
    headerExtra?: React.ReactNode;
}) {
    const [jobs, setJobs] = useState<Job[]>([]);
    const [total, setTotal] = useState(0);
    const [search, setSearch] = useState(initialSearch);
    const [selectedCategories, setSelectedCategories] = useState<Set<string>>(new Set());
    const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set());
    const [usOnly, setUsOnly] = useState(false);
    const [remoteOnly, setRemoteOnly] = useState(false);
    const [recentHours, setRecentHours] = useState<number | null>(null);
    const [experienceLevel, setExperienceLevel] = useState("any");
    const [employmentType, setEmploymentType] = useState("all");
    const [page, setPage] = useState(1);
    const [loading, setLoading] = useState(true);
    const [savedJobs, setSavedJobs] = useState<Set<string>>(new Set());
    const [sortMode, setSortMode] = useState<SortMode>(initialSortMode);
    const isRelevanceMode = sortMode === "relevance" && search.trim().length >= MIN_RELEVANCE_QUERY_LENGTH;
    const categoryValue = selectedCategories.size === 1 ? Array.from(selectedCategories)[0] : "";
    const locationMode = remoteOnly ? "remote" : usOnly ? "us" : "all";

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
                setSavedJobs(new Set(parsed.map((j) => j.internal_hash)));
            } catch {}
        }
    }, []);

    const loadJobs = useCallback(async () => {
        setLoading(true);
        const category = selectedCategories.size === 1 ? Array.from(selectedCategories)[0] : undefined;
        const source = selectedSources.size === 1 ? Array.from(selectedSources)[0].toLowerCase() : undefined;
        const data = isRelevanceMode
            ? await fetchMatchedJobs(search, LIMIT * 2)
            : await fetchJobs({ search, page, limit: LIMIT, category, source, recentHours: recentHours ?? undefined });
        let filtered = data.jobs;

        if (isRelevanceMode && recentHours !== null) {
            filtered = filtered.filter((j) => j.freshness_minutes == null || j.freshness_minutes <= recentHours * 60);
        }

        if (usOnly) filtered = filtered.filter((j) => isUsLocation(j.location));
        if (remoteOnly) filtered = filtered.filter((j) => isRemoteLocation(j.location));
        if (selectedCategories.size > 1) {
            filtered = filtered.filter((j) => {
                try {
                    const keywords = JSON.parse(j.keywords_matched || "[]");
                    return keywords.some((keyword: string) => selectedCategories.has(keyword));
                } catch {
                    return false;
                }
            });
        }

        setJobs(filtered);
        setTotal(data.total);
        setLoading(false);
    }, [search, page, selectedCategories, selectedSources, usOnly, remoteOnly, recentHours, isRelevanceMode]);

    useEffect(() => {
        loadJobs();
    }, [loadJobs]);

    const handleSave = (job: Job) => {
        const saved = localStorage.getItem("jobclaw_saved");
        let arr: Job[] = [];
        try {
            arr = JSON.parse(saved || "[]");
        } catch {}
        const exists = arr.find((j) => j.internal_hash === job.internal_hash);
        arr = exists ? arr.filter((j) => j.internal_hash !== job.internal_hash) : [...arr, { ...job, status: "saved" }];
        localStorage.setItem("jobclaw_saved", JSON.stringify(arr));
        setSavedJobs(new Set(arr.map((j) => j.internal_hash)));
    };

    const handleCategoryChange = (value: string) => {
        setSelectedCategories(value ? new Set([value]) : new Set());
        setPage(1);
    };

    const handleLocationChange = (value: string) => {
        setUsOnly(value === "us");
        setRemoteOnly(value === "remote");
        setPage(1);
    };

    const clearFilters = () => {
        setSelectedCategories(new Set());
        setSelectedSources(new Set());
        setUsOnly(false);
        setRemoteOnly(false);
        setRecentHours(null);
        setExperienceLevel("any");
        setEmploymentType("all");
        setPage(1);
    };

    const totalPages = Math.max(1, Math.ceil(total / LIMIT));
    const start = total === 0 ? 0 : (page - 1) * LIMIT + 1;
    const end = Math.min(page * LIMIT, total);

    return (
        <div className="min-h-screen bg-[#FBF4E7] text-[#1F281B] [background-image:radial-gradient(circle_at_12%_22%,rgba(215,234,220,0.55),transparent_30%),radial-gradient(circle_at_88%_12%,rgba(246,218,158,0.45),transparent_28%),linear-gradient(135deg,#FBF4E7_0%,#F8ECD7_100%)]">
            <DashboardSidebar />
            <TopAppHeader
                search={search}
                onSearchChange={(value) => {
                    setSearch(value);
                    setPage(1);
                }}
            />

            <main className="px-5 py-6 sm:px-8 lg:ml-[280px] lg:p-8">
                <div className="space-y-6">
                    <JobsHeroBanner />
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
                        onExperienceLevelChange={setExperienceLevel}
                        employmentType={employmentType}
                        onEmploymentTypeChange={setEmploymentType}
                        onClear={clearFilters}
                    />

                    {loading ? (
                        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                            {Array.from({ length: LIMIT }).map((_, index) => (
                                <div key={index} className="h-[200px] animate-pulse rounded-lg border border-[#E7D7B7] bg-[#FFF9EC]" />
                            ))}
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                            {jobs.map((job, index) => (
                                <div key={job.internal_hash || index} className="animate-fade-in" style={{ animationDelay: `${index * 25}ms` }}>
                                    <JobCard job={job} onSave={handleSave} saved={savedJobs.has(job.internal_hash)} />
                                </div>
                            ))}
                        </div>
                    )}

                    {!loading && jobs.length === 0 && (
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
