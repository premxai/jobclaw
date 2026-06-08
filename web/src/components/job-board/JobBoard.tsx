"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import CategoryTabs from "./CategoryTabs";
import JobRow from "./JobRow";
import { BOARD_REFRESH_INTERVAL_MS, fetchBoardJobs } from "@/lib/job-board";
import type { BoardCategory, BoardDataStatus, BoardJob } from "@/lib/job-board";

const JOBS_PER_PAGE = 12;

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
    <section className="mx-auto flex h-full w-full max-w-[880px] flex-col justify-center px-4 py-[clamp(0.5rem,1.2dvh,0.75rem)] sm:px-6">
      <div className="mb-2">
        <CategoryTabs jobs={jobs} activeCategory={activeCategory} onChange={setActiveCategory} />
      </div>

      <div className="overflow-hidden rounded-[24px] border border-[#e4c6a0] bg-[#fff8ec]/88 shadow-[0_18px_54px_rgba(80,51,19,0.17),inset_0_1px_0_rgba(255,255,255,0.72)] backdrop-blur-md">
        {loading ? (
          <div className="divide-y divide-[#ead7bd]/80">
            {Array.from({ length: JOBS_PER_PAGE }).map((_, index) => (
              <div
                key={index}
                className="grid h-[clamp(34px,4.7dvh,42px)] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-[clamp(0.25rem,0.55dvh,0.375rem)] sm:px-5"
              >
                <div className="space-y-2">
                  <div className="h-4 w-52 max-w-full animate-pulse rounded-full bg-[#ead7bd]/70" />
                  <div className="h-3 w-[min(260px,100%)] animate-pulse rounded-full bg-[#efdfc8]/70" />
                </div>
                <div className="flex gap-2">
                  <div className="h-6 w-16 animate-pulse rounded-full bg-[#efdfc8]/70" />
                  <div className="h-7 w-7 animate-pulse rounded-full bg-[#efdfc8]/70 sm:h-8 sm:w-8" />
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
            <p className="max-w-sm text-sm font-semibold leading-6 text-[#2f2921] sm:text-base">
              {dataStatus === "unavailable"
                ? "JobClaw is waiting for the backend API. Check the API URL or Railway deployment."
                : activeCategory === "All Roles"
                  ? "No US roles were posted in the last 48 hours."
                  : "No roles found in this category."}
            </p>
          </div>
        )}

        <div className="flex h-[clamp(34px,4.5dvh,40px)] items-center justify-between border-t border-[#ead7bd]/90 bg-[#fff2df]/45 px-4 sm:px-5">
          <p className="text-xs font-medium text-[#6f6457]">
            Page {filteredJobs.length ? page : 0} of {filteredJobs.length ? totalPages : 0}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page <= 1 || loading || !filteredJobs.length}
              className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-[#e2c5a0] bg-[#fff8ed]/80 text-[#3d352c] shadow-[0_2px_0_rgba(139,92,43,0.12)] transition hover:-translate-y-0.5 hover:bg-[#1b1a18] hover:text-[#fff8ee] disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:translate-y-0 disabled:hover:bg-[#fff8ed]/80 disabled:hover:text-[#3d352c] sm:h-8 sm:w-8"
              aria-label="Previous page"
            >
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            </button>
            <span className="min-w-12 text-center text-xs font-semibold text-[#6f6457]">
              {filteredJobs.length ? `${rangeStart}-${rangeEnd}` : "0"}
            </span>
            <button
              type="button"
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              disabled={page >= totalPages || loading || !filteredJobs.length}
              className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-[#e2c5a0] bg-[#fff8ed]/80 text-[#3d352c] shadow-[0_2px_0_rgba(139,92,43,0.12)] transition hover:-translate-y-0.5 hover:bg-[#1b1a18] hover:text-[#fff8ee] disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:translate-y-0 disabled:hover:bg-[#fff8ed]/80 disabled:hover:text-[#3d352c] sm:h-8 sm:w-8"
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
