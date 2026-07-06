"use client";
import { useEffect, useRef, useState } from "react";
import { Search, ChevronDown, X, FileText } from "lucide-react";

export const FILTER_CATEGORIES = ["AI/ML", "SWE", "Data Science", "Data Engineering", "Data Analyst", "New Grad", "Product", "Research"];
export const FILTER_SOURCES = ["Greenhouse", "Lever", "Workday", "Ashby", "SmartRecruiters", "Workable", "Rippling", "BambooHR", "GitHub", "Enterprise", "RSS", "LinkedIn", "Indeed"];

export const RECENCY_OPTIONS: { label: string; hours: number | null }[] = [
    { label: "Any time", hours: null },
    { label: "Last hour", hours: 1 },
    { label: "Last 24h", hours: 24 },
    { label: "Last 48h", hours: 48 },
];

export type SortMode = "recency" | "relevance";

interface SearchFilterBarProps {
    search: string;
    onSearchChange: (value: string) => void;
    selectedCategories: Set<string>;
    onToggleCategory: (category: string) => void;
    selectedSources: Set<string>;
    onToggleSource: (source: string) => void;
    usOnly: boolean;
    onToggleUsOnly: () => void;
    remoteOnly: boolean;
    onToggleRemoteOnly: () => void;
    recentHours: number | null;
    onRecentHoursChange: (hours: number | null) => void;
    onClear: () => void;
    sortMode: SortMode;
    onSortModeChange: (mode: SortMode) => void;
    onOpenResumeMatch?: () => void;
}

function RecencyDropdown({ value, onChange }: { value: number | null; onChange: (hours: number | null) => void }) {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!open) return;
        const onClickOutside = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener("mousedown", onClickOutside);
        return () => document.removeEventListener("mousedown", onClickOutside);
    }, [open]);

    const current = RECENCY_OPTIONS.find((o) => o.hours === value) ?? RECENCY_OPTIONS[0];

    return (
        <div ref={ref} className="relative">
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${value !== null ? "border-accent bg-accent text-white" : "border-border bg-white text-text-secondary hover:text-text-primary"
                    }`}
            >
                {value !== null ? current.label : "Posted"}
                <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`} />
            </button>
            {open && (
                <div className="absolute left-0 top-[calc(100%+8px)] z-20 w-40 rounded-xl border border-border bg-white p-1.5 shadow-popover">
                    {RECENCY_OPTIONS.map((option) => (
                        <button
                            key={option.label}
                            onClick={() => { onChange(option.hours); setOpen(false); }}
                            className={`block w-full rounded-md px-2.5 py-1.5 text-left text-sm ${option.hours === value ? "bg-accent-light text-accent font-medium" : "text-text-secondary hover:bg-surface-2"
                                }`}
                        >
                            {option.label}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

// Below this length, semantic matching isn't worth the round trip — there's
// no meaningful "relevance" to a single word. Keep this in sync with the
// gating check in JobFeedClient.tsx.
export const MIN_RELEVANCE_QUERY_LENGTH = 3;

function FilterDropdown({
    label,
    options,
    selected,
    onToggle,
}: {
    label: string;
    options: string[];
    selected: Set<string>;
    onToggle: (value: string) => void;
}) {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!open) return;
        const onClickOutside = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener("mousedown", onClickOutside);
        return () => document.removeEventListener("mousedown", onClickOutside);
    }, [open]);

    const summary = selected.size === 0 ? `All ${label.toLowerCase()}` : selected.size === 1 ? Array.from(selected)[0] : `${selected.size} ${label.toLowerCase()}`;

    return (
        <div ref={ref} className="relative flex-1 min-w-[160px]">
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className={`flex w-full items-center justify-between gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors ${selected.size > 0 ? "text-accent" : "text-text-primary"
                    } hover:bg-surface-2`}
            >
                <span className="truncate">{summary}</span>
                <ChevronDown className={`h-4 w-4 shrink-0 text-text-secondary transition-transform ${open ? "rotate-180" : ""}`} />
            </button>
            {open && (
                <div className="absolute left-0 top-[calc(100%+8px)] z-20 w-64 rounded-xl border border-border bg-white p-3 shadow-popover">
                    <div className="max-h-64 space-y-1 overflow-y-auto">
                        {options.map((option) => (
                            <label key={option} className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 hover:bg-surface-2">
                                <input
                                    type="checkbox"
                                    checked={selected.has(option)}
                                    onChange={() => onToggle(option)}
                                    className="h-4 w-4 rounded border-border accent-accent"
                                />
                                <span className="text-sm text-text-secondary">{option}</span>
                            </label>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

export function SearchFilterBar({
    search,
    onSearchChange,
    selectedCategories,
    onToggleCategory,
    selectedSources,
    onToggleSource,
    usOnly,
    onToggleUsOnly,
    remoteOnly,
    onToggleRemoteOnly,
    recentHours,
    onRecentHoursChange,
    onClear,
    sortMode,
    onSortModeChange,
    onOpenResumeMatch,
}: SearchFilterBarProps) {
    const activeFilters =
        selectedCategories.size + selectedSources.size + (usOnly ? 1 : 0) + (remoteOnly ? 1 : 0) + (recentHours !== null ? 1 : 0);
    const canRankByRelevance = search.trim().length >= MIN_RELEVANCE_QUERY_LENGTH;

    return (
        <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-2 rounded-2xl border border-border bg-white p-2.5 shadow-card lg:flex-row lg:items-center">
                <div className="flex flex-1 items-center gap-2 border-b border-border px-4 py-2 lg:border-b-0 lg:border-r lg:py-0">
                    <Search className="h-4 w-4 shrink-0 text-text-secondary" />
                    <input
                        type="text"
                        value={search}
                        onChange={(e) => onSearchChange(e.target.value)}
                        placeholder="Job title, company, or keywords… (try describing your skills for best-match)"
                        className="w-full min-w-0 bg-transparent text-sm font-medium text-text-primary placeholder-text-secondary outline-none"
                    />
                    {search && (
                        <button onClick={() => onSearchChange("")} aria-label="Clear search" className="shrink-0 text-text-secondary hover:text-text-primary">
                            <X className="h-4 w-4" />
                        </button>
                    )}
                </div>

                <FilterDropdown label="Categories" options={FILTER_CATEGORIES} selected={selectedCategories} onToggle={onToggleCategory} />
                <FilterDropdown label="Sources" options={FILTER_SOURCES} selected={selectedSources} onToggle={onToggleSource} />

                {onOpenResumeMatch && (
                    <button
                        onClick={onOpenResumeMatch}
                        className="flex shrink-0 items-center gap-1.5 px-3 py-2 text-sm font-medium text-text-secondary hover:text-accent"
                    >
                        <FileText className="h-4 w-4" />
                        Match my resume
                    </button>
                )}

                {activeFilters > 0 && (
                    <button onClick={onClear} className="shrink-0 px-3 py-2 text-sm font-medium text-accent hover:underline">
                        Clear ({activeFilters})
                    </button>
                )}
            </div>

            <div className="flex flex-wrap items-center gap-2">
                <button
                    onClick={onToggleUsOnly}
                    className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${usOnly ? "border-accent bg-accent text-white" : "border-border bg-white text-text-secondary hover:text-text-primary"
                        }`}
                >
                    US only
                </button>
                <button
                    onClick={onToggleRemoteOnly}
                    className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${remoteOnly ? "border-accent bg-accent text-white" : "border-border bg-white text-text-secondary hover:text-text-primary"
                        }`}
                >
                    Remote only
                </button>
                <RecencyDropdown value={recentHours} onChange={onRecentHoursChange} />
            </div>

            {/* Only meaningful once there's a query to rank against — hidden
                otherwise so users never see a toggle with nothing to toggle. */}
            {canRankByRelevance && (
                <div className="flex items-center gap-1 self-start rounded-full border border-border bg-white p-1 shadow-card animate-fade-in">
                    <button
                        onClick={() => onSortModeChange("recency")}
                        className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${sortMode === "recency" ? "bg-accent text-white" : "text-text-secondary hover:text-text-primary"
                            }`}
                    >
                        Most recent
                    </button>
                    <button
                        onClick={() => onSortModeChange("relevance")}
                        className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${sortMode === "relevance" ? "bg-accent text-white" : "text-text-secondary hover:text-text-primary"
                            }`}
                    >
                        Best match
                    </button>
                </div>
            )}
        </div>
    );
}
