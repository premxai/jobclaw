"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, CheckCircle2, CircleAlert, CircleX, Loader2 } from "lucide-react";

type CheckState = "checking" | "pass" | "warn" | "fail";

interface StatusCheck {
  key: string;
  label: string;
  detail: string;
  state: CheckState;
}

interface StatsResponse {
  total_jobs?: number;
  jobs_last_24h?: number;
}

interface JobsResponse {
  jobs?: unknown[];
  total?: number;
}

interface RunResponse {
  scraper?: string;
  run_at?: string;
  status?: string;
}

function stateStyles(state: CheckState): string {
  if (state === "pass") return "border-emerald-200 bg-emerald-50 text-emerald-800";
  if (state === "warn") return "border-amber-200 bg-amber-50 text-amber-800";
  if (state === "fail") return "border-red-200 bg-red-50 text-red-800";
  return "border-zinc-200 bg-zinc-50 text-zinc-600";
}

function StateIcon({ state }: { state: CheckState }) {
  if (state === "pass") return <CheckCircle2 className="h-4 w-4" aria-hidden="true" />;
  if (state === "warn") return <CircleAlert className="h-4 w-4" aria-hidden="true" />;
  if (state === "fail") return <CircleX className="h-4 w-4" aria-hidden="true" />;
  return <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />;
}

async function getJson<T>(path: string): Promise<{ ok: boolean; status: number; data: T | null; error?: string }> {
  try {
    const response = await fetch(path, { cache: "no-store" });
    const text = await response.text();
    let data: T | null = null;
    if (text) {
      try {
        data = JSON.parse(text) as T;
      } catch {
        return { ok: false, status: response.status, data: null, error: text.slice(0, 180) };
      }
    }
    return { ok: response.ok, status: response.status, data };
  } catch (error) {
    return {
      ok: false,
      status: 0,
      data: null,
      error: error instanceof Error ? error.message : "Unknown request error",
    };
  }
}

function formatRun(runs: RunResponse[] | null): string {
  const latest = runs?.[0];
  if (!latest) return "No scraper runs returned from /stats/runs.";
  return `${latest.scraper || "scraper"} ${latest.status || "run"} at ${latest.run_at || "unknown time"}`;
}

function checkingRows(): StatusCheck[] {
  return [
    { key: "api", label: "API health", detail: "Checking /api/health", state: "checking" },
    { key: "db", label: "Database jobs", detail: "Checking /api/stats", state: "checking" },
    { key: "fresh", label: "Fresh jobs", detail: "Checking jobs from the last 48 hours", state: "checking" },
    { key: "accepted", label: "Accepted jobs", detail: "Checking accepted quality jobs", state: "checking" },
    { key: "runs", label: "Scraper runs", detail: "Checking latest scraper run", state: "checking" },
  ];
}

export default function StatusPage() {
  const [checks, setChecks] = useState<StatusCheck[]>(checkingRows);
  const [lastCheckedAt, setLastCheckedAt] = useState<string | null>(null);

  async function runChecks() {
    setChecks(checkingRows());

    const [health, stats, freshJobs, acceptedJobs, runs] = await Promise.all([
      getJson<Record<string, unknown>>("/api/health"),
      getJson<StatsResponse>("/api/stats"),
      getJson<JobsResponse>("/api/jobs?per_page=10&recent_hours=48"),
      getJson<JobsResponse>("/api/jobs?per_page=10&recent_hours=48&quality=accepted"),
      getJson<RunResponse[]>("/api/stats/runs?limit=1"),
    ]);

    const totalJobs = stats.data?.total_jobs || 0;
    const jobsLast24h = stats.data?.jobs_last_24h || 0;
    const freshCount = freshJobs.data?.jobs?.length || 0;
    const acceptedCount = acceptedJobs.data?.jobs?.length || 0;
    const apiStatus = typeof health.data?.status === "string" ? health.data.status : "unknown";
    const databaseStatus = typeof health.data?.database === "string" ? health.data.database : "unknown";

    setChecks([
      {
        key: "api",
        label: "API health",
        state: health.ok ? (apiStatus === "ok" ? "pass" : "warn") : "fail",
        detail: health.ok
          ? `The website can reach /api/health. API status: ${apiStatus}; database: ${databaseStatus}.`
          : `API health failed: ${health.error || health.status}`,
      },
      {
        key: "db",
        label: "Database jobs",
        state: stats.ok && totalJobs > 0 ? "pass" : "fail",
        detail: stats.ok
          ? `${totalJobs.toLocaleString()} total jobs, ${jobsLast24h.toLocaleString()} seen in the last 24 hours.`
          : `Stats failed: ${stats.error || stats.status}`,
      },
      {
        key: "fresh",
        label: "Fresh jobs",
        state: freshJobs.ok && freshCount > 0 ? "pass" : "warn",
        detail: freshJobs.ok
          ? `${freshCount} jobs returned for the last 48 hours.`
          : `Fresh job query failed: ${freshJobs.error || freshJobs.status}`,
      },
      {
        key: "accepted",
        label: "Accepted jobs",
        state: acceptedJobs.ok && acceptedCount > 0 ? "pass" : "warn",
        detail: acceptedJobs.ok
          ? `${acceptedCount} accepted jobs returned. The board can still show real fresh jobs if this is 0.`
          : `Accepted job query failed: ${acceptedJobs.error || acceptedJobs.status}`,
      },
      {
        key: "runs",
        label: "Scraper runs",
        state: runs.ok && Array.isArray(runs.data) && runs.data.length > 0 ? "pass" : "fail",
        detail: runs.ok ? formatRun(runs.data) : `Run history failed: ${runs.error || runs.status}`,
      },
    ]);
    setLastCheckedAt(new Date().toISOString());
  }

  useEffect(() => {
    runChecks();
  }, []);

  const summary = useMemo(() => {
    if (checks.some((check) => check.state === "checking")) return "Checking JobClaw wiring...";
    if (checks.some((check) => check.state === "fail")) return "A required service is not wired yet.";
    if (checks.some((check) => check.state === "warn")) return "The app is connected, but fresh job output needs attention.";
    return "The website, API, database, and scraper history are connected.";
  }, [checks]);

  return (
    <main className="min-h-screen bg-[#f6e8cc] px-4 py-8 text-zinc-950 sm:px-6">
      <section className="mx-auto max-w-3xl rounded-3xl border border-black/10 bg-white/90 p-5 shadow-[0_18px_70px_rgba(41,29,12,0.14)] backdrop-blur-md sm:p-7">
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <Link
              href="/"
              className="mb-4 inline-flex items-center gap-2 text-sm font-semibold text-zinc-500 transition hover:text-black"
            >
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              Job board
            </Link>
            <h1 className="text-3xl font-bold tracking-[-0.03em] text-black sm:text-4xl">JobClaw status</h1>
            <p className="mt-2 max-w-xl text-sm leading-6 text-zinc-600 sm:text-base">{summary}</p>
          </div>
          <button
            type="button"
            onClick={runChecks}
            className="inline-flex h-10 items-center justify-center rounded-full bg-black px-5 text-sm font-semibold text-white transition hover:-translate-y-0.5 hover:bg-zinc-800"
          >
            Refresh
          </button>
        </div>

        <div className="divide-y divide-zinc-200 overflow-hidden rounded-2xl border border-zinc-200 bg-white">
          {checks.map((check) => (
            <div key={check.key} className="grid gap-3 px-4 py-4 sm:grid-cols-[180px_1fr] sm:items-center sm:px-5">
              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex h-7 w-7 items-center justify-center rounded-full border ${stateStyles(
                    check.state,
                  )}`}
                >
                  <StateIcon state={check.state} />
                </span>
                <span className="text-sm font-bold text-zinc-950">{check.label}</span>
              </div>
              <p className="text-sm leading-6 text-zinc-600">{check.detail}</p>
            </div>
          ))}
        </div>

        <p className="mt-4 text-xs font-medium text-zinc-500">
          Last checked:{" "}
          {lastCheckedAt
            ? new Intl.DateTimeFormat(undefined, {
                month: "short",
                day: "numeric",
                hour: "numeric",
                minute: "2-digit",
              }).format(new Date(lastCheckedAt))
            : "Checking..."}
        </p>
      </section>
    </main>
  );
}
