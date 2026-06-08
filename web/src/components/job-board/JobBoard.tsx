"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import CategoryTabs from "./CategoryTabs";
import JobRow from "./JobRow";
import { BOARD_REFRESH_INTERVAL_MS, fetchBoardJobs } from "@/lib/job-board";
import type { BoardCategory, BoardDataStatus, BoardJob } from "@/lib/job-board";

const JOBS_PER_PAGE = 8;

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
    <section className="mx-auto flex h-full w-full max-w-[900px] flex-col justify-center px-4 py-4 sm:px-6">
      <div className="mb-3">
        <CategoryTabs jobs={jobs} activeCategory={activeCategory} onChange={setActiveCategory} />
      </div>

      <div className="overflow-hidden rounded-[22px] border border-[#E8CFA8] bg-[#FFFEFB] shadow-[0_20px_60px_rgba(120,80,40,0.12)]">
        {loading ? (
          <div className="divide-y divide-[rgba(139,94,52,0.15)]">
            {Array.from({ length: JOBS_PER_PAGE }).map((_, index) => (
              <div
                key={index}
                className="grid h-16 grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-5 sm:h-[66px] sm:px-7"
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

        <div className="flex h-11 items-center justify-between border-t border-[rgba(139,94,52,0.15)] bg-[#FFFEFB] px-5 sm:px-7">
          <p className="text-sm font-medium text-[#6B6B6B]">
            Page {filteredJobs.length ? page : 0} of {filteredJobs.length ? totalPages : 0}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page <= 1 || loading || !filteredJobs.length}
              className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-[#E8CFA8] bg-[#FFFEFB] text-[#333333] transition hover:-translate-y-0.5 hover:bg-[#171717] hover:text-white disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:translate-y-0 disabled:hover:bg-[#FFFEFB] disabled:hover:text-[#333333]"
              aria-label="Previous page"
            >
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            </button>
            <span className="min-w-12 text-center text-sm font-semibold text-[#6B6B6B]">
              {filteredJobs.length ? `${rangeStart}-${rangeEnd}` : "0"}
            </span>
            <button
              type="button"
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              disabled={page >= totalPages || loading || !filteredJobs.length}
              className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-[#E8CFA8] bg-[#FFFEFB] text-[#333333] transition hover:-translate-y-0.5 hover:bg-[#171717] hover:text-white disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:translate-y-0 disabled:hover:bg-[#FFFEFB] disabled:hover:text-[#333333]"
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
