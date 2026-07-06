"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";

import CategoryTabs from "./CategoryTabs";
import JobRow from "./JobRow";
import { BOARD_REFRESH_INTERVAL_MS, fetchBoardJobs } from "@/lib/job-board";
import type { BoardCategory, BoardDataStatus, BoardJob } from "@/lib/job-board";

const JOBS_PER_PAGE = 9;

// A short, deliberately small set — this is a quick-launch strip, not the full
// filter taxonomy (see FILTER_CATEGORIES in SearchFilterBar.tsx). Kept to 4 so
// it fits as one line without disturbing the room-scene's tight vertical
// budget (job-board-shell's row-height clamp() assumes a fixed header size).
const QUICK_LAUNCH_CATEGORIES = ["AI/ML", "SWE", "Data Science", "New Grad"];

export default function JobBoard() {
  const [jobs, setJobs] = useState<BoardJob[]>([]);
  const [activeCategory, setActiveCategory] = useState<BoardCategory>("All Roles");
  const [page, setPage] = useState(1);
  const [dataStatus, setDataStatus] = useState<BoardDataStatus>("unavailable");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function loadBoard(options: { silent?: boolean } = {}) {
      if (!options.silent) setLoading(true);
      const jobResult = await fetchBoardJobs();

      if (!mounted) return;
      setJobs(jobResult.jobs);
      setDataStatus(jobResult.status);
      setLoading(false);
    }

    loadBoard();
    const interval = window.setInterval(() => loadBoard({ silent: true }), BOARD_REFRESH_INTERVAL_MS);
    const refreshOnFocus = () => loadBoard({ silent: true });
    const refreshOnVisible = () => {
      if (document.visibilityState === "visible") loadBoard({ silent: true });
    };

    window.addEventListener("focus", refreshOnFocus);
    document.addEventListener("visibilitychange", refreshOnVisible);

    return () => {
      mounted = false;
      window.clearInterval(interval);
      window.removeEventListener("focus", refreshOnFocus);
      document.removeEventListener("visibilitychange", refreshOnVisible);
    };
  }, []);

  useEffect(() => {
    setPage(1);
  }, [activeCategory]);

  const filteredJobs = useMemo(() => {
    if (activeCategory === "All Roles") return jobs;
    return jobs.filter((job) => job.category === activeCategory);
  }, [activeCategory, jobs]);

  const totalPages = Math.max(1, Math.ceil(filteredJobs.length / JOBS_PER_PAGE));
  const visibleJobs = filteredJobs.slice((page - 1) * JOBS_PER_PAGE, page * JOBS_PER_PAGE);
  const rangeStart = filteredJobs.length ? (page - 1) * JOBS_PER_PAGE + 1 : 0;
  const rangeEnd = Math.min(filteredJobs.length, page * JOBS_PER_PAGE);

  return (
    <section className="job-board-shell mx-auto flex min-h-full w-full max-w-[880px] flex-col justify-center px-3 py-[clamp(0.75rem,1.6dvh,2rem)] sm:px-5">
      <div className="mx-auto mb-[clamp(0.2rem,0.8dvh,0.75rem)] max-w-xl px-4 py-[clamp(0.15rem,0.6dvh,0.65rem)] text-center">
        <h1 className="text-[clamp(1.2rem,3vw,2.25rem)] font-bold leading-[0.96] tracking-tight text-[#171717]">
          Hey, I am Nori
        </h1>
        <p className="mt-1 text-[clamp(0.68rem,1.2vw,0.875rem)] font-semibold leading-[1.35] text-[#4f4a42]">
          Check my notes below for job postings from the last 48 hours.
        </p>
        <div className="mt-[clamp(0.2rem,0.6dvh,0.5rem)] flex flex-wrap items-center justify-center gap-1.5">
          {QUICK_LAUNCH_CATEGORIES.map((category) => (
            <Link
              key={category}
              href={`/jobs?search=${encodeURIComponent(category)}&mode=relevance`}
              className="rounded-full border border-[#E8CFA8] bg-[#FFFEFB] px-2.5 py-[clamp(0.1rem,0.3dvh,0.25rem)] text-[clamp(0.6rem,1vw,0.7rem)] font-semibold text-[#4f4a42] transition-colors hover:bg-[#171717] hover:text-white"
            >
              {category}
            </Link>
          ))}
        </div>
      </div>

      <div className="mb-[clamp(0.2rem,0.7dvh,0.5rem)] shrink-0">
        <CategoryTabs jobs={jobs} activeCategory={activeCategory} onChange={setActiveCategory} />
      </div>

      <div className="shrink-0 overflow-hidden rounded-[22px] border border-[#E8CFA8] bg-[#FFFEFB] shadow-popover">
        {loading ? (
          <div className="divide-y divide-[rgba(139,94,52,0.15)]">
            {Array.from({ length: JOBS_PER_PAGE }).map((_, index) => (
              <div
                key={index}
                className="grid h-[var(--job-board-row-height)] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-1 sm:px-5"
              >
                <div className="space-y-2">
                  <div className="h-4 w-56 max-w-full animate-pulse rounded-full bg-[#EFE5D6]" />
                  <div className="h-3 w-[min(280px,100%)] animate-pulse rounded-full bg-[#F4EBDC]" />
                </div>
                <div className="flex gap-2">
                  <div className="h-7 w-28 animate-pulse rounded-full bg-[#F4EBDC]" />
                  <div className="h-9 w-9 animate-pulse rounded-full bg-[#F4EBDC]" />
                </div>
              </div>
            ))}
          </div>
        ) : filteredJobs.length > 0 ? (
          <div>
            {visibleJobs.map((job) => (
              <JobRow key={job.id} job={job} />
            ))}
          </div>
        ) : (
          <div className="flex min-h-[132px] items-center justify-center px-6 text-center">
            <p className="max-w-sm text-sm font-semibold leading-6 text-[#171717] sm:text-base">
              {dataStatus === "unavailable"
                ? "JobClaw is waiting for the backend API. Check the API URL or Railway deployment."
                : activeCategory === "All Roles"
                  ? "No US roles were posted in the last 48 hours."
                  : "No roles found in this category."}
            </p>
          </div>
        )}

        <div className="flex h-[var(--job-board-footer-height)] items-center justify-between border-t border-[rgba(139,94,52,0.15)] bg-[#FFFEFB] px-4 sm:px-5">
          <p className="text-xs font-medium text-[#6B6B6B]">
            Page {filteredJobs.length ? page : 0} of {filteredJobs.length ? totalPages : 0}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page <= 1 || loading || !filteredJobs.length}
              className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-[#E8CFA8] bg-[#FFFEFB] text-[#333333] transition hover:-translate-y-0.5 hover:bg-[#171717] hover:text-white disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:translate-y-0 disabled:hover:bg-[#FFFEFB] disabled:hover:text-[#333333] sm:h-8 sm:w-8"
              aria-label="Previous page"
            >
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            </button>
            <span className="min-w-12 text-center text-xs font-semibold text-[#6B6B6B]">
              {filteredJobs.length ? `${rangeStart}-${rangeEnd}` : "0"}
            </span>
            <button
              type="button"
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              disabled={page >= totalPages || loading || !filteredJobs.length}
              className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-[#E8CFA8] bg-[#FFFEFB] text-[#333333] transition hover:-translate-y-0.5 hover:bg-[#171717] hover:text-white disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:translate-y-0 disabled:hover:bg-[#FFFEFB] disabled:hover:text-[#333333] sm:h-8 sm:w-8"
              aria-label="Next page"
            >
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
