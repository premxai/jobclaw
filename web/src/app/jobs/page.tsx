"use client";
import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import TopNav from "@/components/TopNav";
import JobCard, { Job } from "@/components/JobCard";
import { fetchJobs } from "@/lib/api";
import { Search, SlidersHorizontal, X } from "lucide-react";

const CATEGORIES = ["AI/ML", "SWE", "Data Science", "Data Engineering", "Data Analyst", "New Grad", "Product", "Research"];
const SOURCES = ["Greenhouse", "Lever", "Workday", "GitHub", "LinkedIn", "Indeed"];

export default function JobFeedPage() {
    const searchParams = useSearchParams();
    const initialSearch = searchParams.get("search") || "";

    const [jobs, setJobs] = useState<Job[]>([]);
    const [total, setTotal] = useState(0);
    const [search, setSearch] = useState(initialSearch);
    const [selectedCategories, setSelectedCategories] = useState<Set<string>>(new Set());
    const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set());
    const [page, setPage] = useState(1);
    const [loading, setLoading] = useState(true);
    const [showFilters, setShowFilters] = useState(true);
    const [savedJobs, setSavedJobs] = useState<Set<string>>(new Set());
    const LIMIT = 12;

    useEffect(() => {
        const saved = localStorage.getItem("jobclaw_saved");
        if (saved) {
            try {
                const parsed = JSON.parse(saved);
                setSavedJobs(new Set(parsed.map((j: any) => j.internal_hash)));
            } catch { }
        }
    }, []);

    const loadJobs = useCallback(async () => {
        setLoading(true);
        const data = await fetchJobs({ search, page, limit: LIMIT });
        let filtered = data.jobs;

        if (selectedCategories.size > 0) {
            filtered = filtered.filter((j) => {
                try {
                    const kw = JSON.parse(j.keywords_matched || "[]");
                    return kw.some((k: string) => selectedCategories.has(k));
                } catch { return false; }
            });
        }
        if (selectedSources.size > 0) {
            const sourceMap: Record<string, string[]> = {
                Greenhouse: ["greenhouse"],
                Lever: ["lever"],
                Workday: ["workday"],
                GitHub: ["github-swe-newgrad", "github-ai-newgrad", "github-internship", "github-new-grad"],
                LinkedIn: ["linkedin"],
                Indeed: ["indeed"],
            };
            filtered = filtered.filter((j) => {
                return Array.from(selectedSources).some((s) => (sourceMap[s] || []).includes(j.source_ats));
            });
        }

        setJobs(filtered);
        setTotal(data.total);
        setLoading(false);
    }, [search, page, selectedCategories, selectedSources]);

    useEffect(() => { loadJobs(); }, [loadJobs]);

    const toggleCategory = (cat: string) => {
        setSelectedCategories((prev) => {
            const next = new Set(prev);
            if (next.has(cat)) next.delete(cat); else next.add(cat);
            return next;
        });
        setPage(1);
    };

    const toggleSource = (src: string) => {
        setSelectedSources((prev) => {
            const next = new Set(prev);
            if (next.has(src)) next.delete(src); else next.add(src);
            return next;
        });
        setPage(1);
    };

    const handleSave = (job: Job) => {
        const saved = localStorage.getItem("jobclaw_saved");
        let arr: Job[] = [];
        try { arr = JSON.parse(saved || "[]"); } catch { }
        const exists = arr.find((j) => j.internal_hash === job.internal_hash);
        if (exists) {
            arr = arr.filter((j) => j.internal_hash !== job.internal_hash);
        } else {
            arr.push({ ...job, status: "saved" });
        }
        localStorage.setItem("jobclaw_saved", JSON.stringify(arr));
        setSavedJobs(new Set(arr.map((j) => j.internal_hash)));
    };

    const activeFilters = selectedCategories.size + selectedSources.size;

    return (
        <div className="min-h-screen">
            <TopNav />

            <div className="max-w-7xl mx-auto px-6 py-8">
                {/* Search header */}
                <div className="flex items-center gap-4 mb-8">
                    <div className="flex-1 flex items-center bg-white border border-border rounded-xl overflow-hidden focus-within:border-accent transition-colors shadow-sm">
                        <Search className="w-5 h-5 text-text-secondary ml-4 shrink-0" />
                        <input
                            type="text"
                            placeholder="Search jobs, companies, or keywords…"
                            className="flex-1 bg-transparent px-4 py-3 text-text-primary placeholder-text-secondary text-sm outline-none"
                            value={search}
                            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                        />
                        {search && (
                            <button onClick={() => setSearch("")} className="p-2 text-text-secondary hover:text-text-primary">
                                <X className="w-4 h-4" />
                            </button>
                        )}
                    </div>
                    <button
                        onClick={() => setShowFilters(!showFilters)}
                        className={`btn-outline flex items-center gap-2 ${showFilters ? "border-accent text-accent" : ""}`}
                    >
                        <SlidersHorizontal className="w-4 h-4" />
                        Filters
                        {activeFilters > 0 && (
                            <span className="w-5 h-5 rounded-full bg-accent text-white text-xs flex items-center justify-center">{activeFilters}</span>
                        )}
                    </button>
                </div>

                <div className="flex gap-8">
                    {/* Sidebar filters */}
                    {showFilters && (
                        <aside className="w-56 shrink-0 animate-slide-in">
                            <div className="sticky top-24 space-y-6">
                                <div>
                                    <h3 className="text-sm font-semibold text-text-primary mb-3">Category</h3>
                                    <div className="space-y-2">
                                        {CATEGORIES.map((cat) => (
                                            <label key={cat} className="flex items-center gap-2.5 cursor-pointer group">
                                                <input
                                                    type="checkbox"
                                                    checked={selectedCategories.has(cat)}
                                                    onChange={() => toggleCategory(cat)}
                                                    className="w-4 h-4 rounded border-border accent-accent"
                                                />
                                                <span className="text-sm text-text-secondary group-hover:text-text-primary transition-colors">{cat}</span>
                                            </label>
                                        ))}
                                    </div>
                                </div>

                                <div>
                                    <h3 className="text-sm font-semibold text-text-primary mb-3">Source</h3>
                                    <div className="space-y-2">
                                        {SOURCES.map((src) => (
                                            <label key={src} className="flex items-center gap-2.5 cursor-pointer group">
                                                <input
                                                    type="checkbox"
                                                    checked={selectedSources.has(src)}
                                                    onChange={() => toggleSource(src)}
                                                    className="w-4 h-4 rounded border-border accent-accent"
                                                />
                                                <span className="text-sm text-text-secondary group-hover:text-text-primary transition-colors">{src}</span>
                                            </label>
                                        ))}
                                    </div>
                                </div>

                                {activeFilters > 0 && (
                                    <button
                                        onClick={() => { setSelectedCategories(new Set()); setSelectedSources(new Set()); }}
                                        className="text-xs text-accent hover:underline"
                                    >
                                        Clear all filters
                                    </button>
                                )}
                            </div>
                        </aside>
                    )}

                    {/* Job grid */}
                    <main className="flex-1">
                        <div className="flex items-center justify-between mb-6">
                            <p className="text-sm text-text-secondary">
                                Showing <span className="text-text-primary font-medium">{total}</span> jobs
                            </p>
                        </div>

                        {loading ? (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                                {Array.from({ length: 6 }).map((_, i) => (
                                    <div key={i} className="bg-white rounded-xl border border-border h-56 animate-pulse" />
                                ))}
                            </div>
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                                {jobs.map((job, i) => (
                                    <div key={job.internal_hash || i} className="animate-fade-in" style={{ animationDelay: `${i * 30}ms` }}>
                                        <Link href={`/jobs/${job.id}`} className="block h-full">
                                            <JobCard job={job} onSave={handleSave} saved={savedJobs.has(job.internal_hash)} />
                                        </Link>
                                    </div>
                                ))}
                            </div>
                        )}

                        {!loading && jobs.length === 0 && (
                            <div className="text-center py-20">
                                <p className="text-xl font-bold text-text-primary mb-2">No jobs found</p>
                                <p className="text-text-secondary">Try adjusting your search or filters.</p>
                            </div>
                        )}

                        {total > LIMIT && (
                            <div className="flex items-center justify-center gap-2 mt-10">
                                <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1} className="btn-outline disabled:opacity-30">Previous</button>
                                <span className="text-sm text-text-secondary px-4">Page {page}</span>
                                <button onClick={() => setPage(page + 1)} disabled={jobs.length < LIMIT} className="btn-outline disabled:opacity-30">Next</button>
                            </div>
                        )}
                    </main>
                </div>
            </div>
        </div>
    );
}
