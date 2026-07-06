"use client";
import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import TopNav from "@/components/TopNav";
import JobCard, { Job } from "@/components/JobCard";
import { fetchJobs, fetchMatchedJobs } from "@/lib/api";
import { SearchFilterBar, SortMode, MIN_RELEVANCE_QUERY_LENGTH } from "@/components/SearchFilterBar";
import ResumeMatchModal from "@/components/ResumeMatchModal";

interface SavedJobRef {
    internal_hash: string;
}

export default function JobFeedClient({
    initialSearch,
    initialSortMode = "recency",
}: {
    initialSearch: string;
    initialSortMode?: SortMode;
}) {
    const [jobs, setJobs] = useState<Job[]>([]);
    const [total, setTotal] = useState(0);
    const [search, setSearch] = useState(initialSearch);
    const [selectedCategories, setSelectedCategories] = useState<Set<string>>(new Set());
    const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set());
    const [page, setPage] = useState(1);
    const [loading, setLoading] = useState(true);
    const [savedJobs, setSavedJobs] = useState<Set<string>>(new Set());
    const [sortMode, setSortMode] = useState<SortMode>(initialSortMode);
    const [resumeModalOpen, setResumeModalOpen] = useState(false);
    const LIMIT = 12;
    const isRelevanceMode = sortMode === "relevance" && search.trim().length >= MIN_RELEVANCE_QUERY_LENGTH;

    // No relevance without a query — if the search box empties out (or shrinks
    // below the threshold) while "Best match" is active, fall back to recency
    // rather than silently keep stale ranked results on screen.
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
            } catch { }
        }
    }, []);

    const loadJobs = useCallback(async () => {
        setLoading(true);
        const category = selectedCategories.size === 1 ? Array.from(selectedCategories)[0] : undefined;
        const source = selectedSources.size === 1 ? Array.from(selectedSources)[0].toLowerCase() : undefined;

        // Relevance mode ranks against the free-text query semantically and
        // returns one top-K list (no pagination); recency mode is the normal
        // paginated /jobs browse. Both populate the same `jobs` state, so
        // everything downstream (category/source filtering, JobCard rendering)
        // works identically regardless of which one ran.
        const data = isRelevanceMode
            ? await fetchMatchedJobs(search, LIMIT * 2)
            : await fetchJobs({ search, page, limit: LIMIT, category, source });
        let filtered = data.jobs;

        if (selectedCategories.size > 1) {
            filtered = filtered.filter((j) => {
                try {
                    const kw = JSON.parse(j.keywords_matched || "[]");
                    return kw.some((k: string) => selectedCategories.has(k));
                } catch { return false; }
            });
        }
        if (selectedSources.size > 1) {
            const sourceMap: Record<string, string[]> = {
                greenhouse: ["greenhouse"],
                lever: ["lever"],
                workday: ["workday"],
                ashby: ["ashby"],
                smartrecruiters: ["smartrecruiters"],
                workable: ["workable"],
                rippling: ["rippling"],
                bamboohr: ["bamboohr"],
                github: ["github-swe-newgrad", "github-ai-newgrad", "github-internship", "github-new-grad"],
                enterprise: ["apple", "amazon", "microsoft", "google", "meta", "tiktok", "nvidia", "uber", "tesla", "cursor"],
                rss: ["rss"],
                linkedin: ["linkedin"],
                indeed: ["indeed"],
            };
            filtered = filtered.filter((j) => {
                return Array.from(selectedSources).some((s) => (sourceMap[s.toLowerCase()] || []).includes(j.source_ats));
            });
        }

        setJobs(filtered);
        setTotal(data.total);
        setLoading(false);
    }, [search, page, selectedCategories, selectedSources, isRelevanceMode]);

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

    return (
        <div className="min-h-screen">
            <TopNav />

            <div className="max-w-7xl mx-auto px-6 py-8">
                <div className="mb-8">
                    <SearchFilterBar
                        search={search}
                        onSearchChange={(value) => { setSearch(value); setPage(1); }}
                        selectedCategories={selectedCategories}
                        onToggleCategory={toggleCategory}
                        selectedSources={selectedSources}
                        onToggleSource={toggleSource}
                        onClear={() => { setSelectedCategories(new Set()); setSelectedSources(new Set()); }}
                        sortMode={sortMode}
                        onSortModeChange={setSortMode}
                        onOpenResumeMatch={() => setResumeModalOpen(true)}
                    />
                </div>

                <ResumeMatchModal
                    open={resumeModalOpen}
                    onClose={() => setResumeModalOpen(false)}
                    onSave={handleSave}
                    savedJobs={savedJobs}
                />

                <main>
                    <div className="flex items-center justify-between mb-6">
                        <p className="text-sm text-text-secondary">
                            {isRelevanceMode ? (
                                <>
                                    <span className="text-text-primary font-medium">{total}</span> best matches for &ldquo;{search}&rdquo;
                                </>
                            ) : (
                                <>
                                    Showing <span className="text-text-primary font-medium">{total}</span> jobs
                                </>
                            )}
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

                    {/* Relevance mode is a single ranked top-K list, not a paginated
                        browse — there's no "next page" to request. */}
                    {!isRelevanceMode && total > LIMIT && (
                        <div className="flex items-center justify-center gap-2 mt-10">
                            <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1} className="btn-outline disabled:opacity-30">Previous</button>
                            <span className="text-sm text-text-secondary px-4">Page {page}</span>
                            <button onClick={() => setPage(page + 1)} disabled={jobs.length < LIMIT} className="btn-outline disabled:opacity-30">Next</button>
                        </div>
                    )}
                </main>
            </div>
        </div>
    );
}
