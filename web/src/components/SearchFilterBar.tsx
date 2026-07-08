"use client";

import Link from "next/link";
import type React from "react";
import { useEffect, useRef, useState } from "react";
import { Bookmark, BriefcaseBusiness, ChevronDown, Clock3, Layers3, MapPin, Search, SlidersHorizontal, X } from "lucide-react";

export const FILTER_CATEGORIES = ["AI/ML", "SWE", "Data Science", "Data Engineering", "Data Analyst", "New Grad", "Product", "Research"];
export const FILTER_SOURCES = ["Greenhouse", "Lever", "Workday", "Ashby", "SmartRecruiters", "Workable", "Rippling", "BambooHR", "GitHub", "Enterprise", "RSS", "LinkedIn", "Indeed"];

export const RECENCY_OPTIONS: { label: string; hours: number | null }[] = [
    { label: "Any time", hours: null },
    { label: "Last hour", hours: 1 },
    { label: "Last 24h", hours: 24 },
    { label: "Last 48h", hours: 48 },
];

export type SortMode = "recency" | "relevance";
export const MIN_RELEVANCE_QUERY_LENGTH = 3;

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
}

function useOutsideClose(open: boolean, setOpen: (open: boolean) => void) {
    const ref = useRef<HTMLDivElement>(null);
    useEffect(() => {
        if (!open) return;
        const onClickOutside = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener("mousedown", onClickOutside);
        return () => document.removeEventListener("mousedown", onClickOutside);
    }, [open, setOpen]);
    return ref;
}

function RecencyDropdown({ value, onChange }: { value: number | null; onChange: (hours: number | null) => void }) {
    const [open, setOpen] = useState(false);
    const ref = useOutsideClose(open, setOpen);
    const current = RECENCY_OPTIONS.find((o) => o.hours === value) ?? RECENCY_OPTIONS[0];

    return (
        <div ref={ref} className="relative">
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className={`inline-flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-bold transition ${
                    value !== null ? "border-ink bg-ink text-white" : "border-border bg-white text-text-secondary hover:text-ink"
                }`}
            >
                <Clock3 className="h-4 w-4" />
                {value !== null ? current.label : "Posted"}
                <ChevronDown className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} />
            </button>
            {open && (
                <div className="absolute left-0 top-[calc(100%+8px)] z-20 w-44 rounded-2xl border border-border bg-white p-2 shadow-popover">
                    {RECENCY_OPTIONS.map((option) => (
                        <button
                            key={option.label}
                            onClick={() => {
                                onChange(option.hours);
                                setOpen(false);
                            }}
                            className={`block w-full rounded-xl px-3 py-2 text-left text-sm font-bold ${
                                option.hours === value ? "bg-ink text-white" : "text-text-secondary hover:bg-surface-2 hover:text-ink"
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

function FilterDropdown({
    label,
    icon,
    options,
    selected,
    onToggle,
}: {
    label: string;
    icon: React.ReactNode;
    options: string[];
    selected: Set<string>;
    onToggle: (value: string) => void;
}) {
    const [open, setOpen] = useState(false);
    const ref = useOutsideClose(open, setOpen);
    const summary = selected.size === 0 ? `All ${label.toLowerCase()}` : selected.size === 1 ? Array.from(selected)[0] : `${selected.size} ${label.toLowerCase()}`;

    return (
        <div ref={ref} className="relative min-w-[180px] flex-1">
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className={`flex w-full items-center justify-between gap-3 rounded-xl border px-4 py-3 text-sm font-bold transition ${
                    selected.size > 0 ? "border-ink bg-ink text-white" : "border-border bg-white text-text-primary hover:bg-surface-2"
                }`}
            >
                <span className="flex min-w-0 items-center gap-2">
                    {icon}
                    <span className="truncate">{summary}</span>
                </span>
                <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
            </button>
            {open && (
                <div className="absolute left-0 top-[calc(100%+8px)] z-20 w-72 rounded-2xl border border-border bg-white p-3 shadow-popover">
                    <div className="max-h-64 space-y-1 overflow-y-auto">
                        {options.map((option) => (
                            <label key={option} className="flex cursor-pointer items-center gap-2.5 rounded-xl px-2.5 py-2 hover:bg-surface-2">
                                <input
                                    type="checkbox"
                                    checked={selected.has(option)}
                                    onChange={() => onToggle(option)}
                                    className="h-4 w-4 rounded border-border accent-ink"
                                />
                                <span className="text-sm font-semibold text-text-secondary">{option}</span>
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
}: SearchFilterBarProps) {
    const activeFilters = selectedCategories.size + selectedSources.size + (usOnly ? 1 : 0) + (remoteOnly ? 1 : 0) + (recentHours !== null ? 1 : 0);
    const canRankByRelevance = search.trim().length >= MIN_RELEVANCE_QUERY_LENGTH;

    return (
        <div className="space-y-3">
            <div className="nori-panel p-3">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
                    <div className="flex min-h-[3.25rem] flex-1 items-center gap-3 rounded-2xl bg-surface-2 px-4">
                        <Search className="h-5 w-5 shrink-0 text-text-secondary" />
                        <input
                            type="text"
                            value={search}
                            onChange={(e) => onSearchChange(e.target.value)}
                            placeholder="Search role, company, keyword, or location"
                            className="w-full min-w-0 bg-transparent text-base font-bold text-text-primary placeholder:text-text-secondary focus:outline-none"
                        />
                        {search && (
                            <button onClick={() => onSearchChange("")} aria-label="Clear search" className="shrink-0 rounded-full p-1 text-text-secondary hover:bg-white hover:text-ink">
                                <X className="h-4 w-4" />
                            </button>
                        )}
                    </div>

                    <FilterDropdown label="Categories" icon={<BriefcaseBusiness className="h-4 w-4" />} options={FILTER_CATEGORIES} selected={selectedCategories} onToggle={onToggleCategory} />
                    <FilterDropdown label="Sources" icon={<Layers3 className="h-4 w-4" />} options={FILTER_SOURCES} selected={selectedSources} onToggle={onToggleSource} />

                    <Link href="/tracker" className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-ink px-4 py-3 text-sm font-bold text-white transition hover:bg-neutral-800">
                        <Bookmark className="h-4 w-4" />
                        Saved jobs
                    </Link>
                </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
                <button
                    onClick={onToggleUsOnly}
                    className={`inline-flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-bold transition ${
                        usOnly ? "border-ink bg-ink text-white" : "border-border bg-white text-text-secondary hover:text-ink"
                    }`}
                >
                    <MapPin className="h-4 w-4" />
                    US only
                </button>
                <button
                    onClick={onToggleRemoteOnly}
                    className={`rounded-xl border px-4 py-2.5 text-sm font-bold transition ${
                        remoteOnly ? "border-ink bg-ink text-white" : "border-border bg-white text-text-secondary hover:text-ink"
                    }`}
                >
                    Remote only
                </button>
                <RecencyDropdown value={recentHours} onChange={onRecentHoursChange} />
                {activeFilters > 0 && (
                    <button onClick={onClear} className="inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-bold text-text-secondary hover:text-ink">
                        <SlidersHorizontal className="h-4 w-4" />
                        Clear ({activeFilters})
                    </button>
                )}
            </div>

            {canRankByRelevance && (
                <div className="inline-flex items-center gap-1 rounded-xl border border-border bg-white p-1 shadow-card animate-fade-in">
                    <button
                        onClick={() => onSortModeChange("recency")}
                        className={`rounded-lg px-3 py-2 text-xs font-bold transition ${sortMode === "recency" ? "bg-ink text-white" : "text-text-secondary hover:text-ink"}`}
                    >
                        Most recent
                    </button>
                    <button
                        onClick={() => onSortModeChange("relevance")}
                        className={`rounded-lg px-3 py-2 text-xs font-bold transition ${sortMode === "relevance" ? "bg-ink text-white" : "text-text-secondary hover:text-ink"}`}
                    >
                        Best match
                    </button>
                </div>
            )}
        </div>
    );
}
