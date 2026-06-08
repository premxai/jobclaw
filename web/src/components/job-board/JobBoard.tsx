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

    return () => {
      mounted = false;
      window.clearInterval(interval);
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
    <section className="mx-auto flex h-full w-full max-w-[880px] flex-col justify-center px-4 py-3 sm:px-6">
      <div className="mb-2">
        <CategoryTabs jobs={jobs} activeCategory={activeCategory} onChange={setActiveCategory} />
      </div>

      <div className="overflow-hidden rounded-2xl border border-white/45 bg-white/68 shadow-[0_18px_70px_rgba(41,29,12,0.16)] backdrop-blur-2xl">
        {loading ? (
          <div className="divide-y divide-black/10">
            {Array.from({ length: JOBS_PER_PAGE }).map((_, index) => (
              <div key={index} className="grid h-[42px] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-1.5 sm:px-5">
                <div className="space-y-2">
                  <div className="h-4 w-52 max-w-full animate-pulse rounded-full bg-white/60" />
                  <div className="h-3 w-[min(260px,100%)] animate-pulse rounded-full bg-white/50" />
                </div>
                <div className="flex gap-2">
                  <div className="h-6 w-16 animate-pulse rounded-full bg-white/55" />
                  <div className="hidden h-6 w-20 animate-pulse rounded-full bg-white/55 sm:block" />
                  <div className="h-8 w-8 animate-pulse rounded-full bg-white/55" />
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
            <p className="max-w-sm text-sm font-semibold leading-6 text-zinc-800 sm:text-base">
              {dataStatus === "unavailable"
                ? "JobClaw is waiting for the backend API. Check the API URL or Railway deployment."
                : activeCategory === "All Roles"
                  ? "No US roles were posted in the last 48 hours."
                  : "No roles found in this category."}
            </p>
          </div>
        )}

        <div className="flex h-10 items-center justify-between border-t border-black/10 bg-white/18 px-4 sm:px-5">
          <p className="text-xs font-medium text-zinc-500">
            Page {filteredJobs.length ? page : 0} of {filteredJobs.length ? totalPages : 0}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page <= 1 || loading || !filteredJobs.length}
              className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-zinc-100 text-zinc-700 transition hover:bg-black hover:text-white disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:bg-zinc-100 disabled:hover:text-zinc-700"
              aria-label="Previous page"
            >
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            </button>
            <span className="min-w-12 text-center text-xs font-semibold text-zinc-500">
              {filteredJobs.length ? `${rangeStart}-${rangeEnd}` : "0"}
            </span>
            <button
              type="button"
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              disabled={page >= totalPages || loading || !filteredJobs.length}
              className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-zinc-100 text-zinc-700 transition hover:bg-black hover:text-white disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:bg-zinc-100 disabled:hover:text-zinc-700"
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
