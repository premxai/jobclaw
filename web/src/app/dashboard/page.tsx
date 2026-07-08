"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import TopNav from "@/components/TopNav";
import CompanyLogo from "@/components/CompanyLogo";
import StageChart from "@/components/dashboard/StageChart";
import { displayCompany, displayTitle } from "@/lib/job-display";
import { fetchStats } from "@/lib/api";
import { Activity, ArrowRight, BarChart3, Bookmark, Calendar, ExternalLink, MapPin, Send, Sparkles, Target, Trophy } from "lucide-react";

interface TrackedJob {
    internal_hash: string;
    title: string;
    company: string;
    canonical_company?: string | null;
    canonical_title?: string | null;
    location: string;
    url: string;
    date_posted: string;
    source_ats: string;
    status: string;
    addedAt?: string;
    keywords_matched?: string;
}

const STATUS_COLORS: Record<string, string> = {
    saved: "bg-surface-2 text-ink border-border",
    applied: "bg-blue-50 text-info border-blue-100",
    interview: "bg-amber-50 text-warning border-amber-100",
    offer: "bg-green-50 text-success border-green-100",
};

export default function DashboardPage() {
    const [jobs, setJobs] = useState<TrackedJob[]>([]);
    const [freshJobs, setFreshJobs] = useState<number | null>(null);
    const [companies, setCompanies] = useState<number | null>(null);

    useEffect(() => {
        const saved = localStorage.getItem("jobclaw_saved");
        if (saved) {
            try {
                setJobs(JSON.parse(saved));
            } catch { }
        }
        fetchStats().then((stats) => {
            setFreshJobs(stats.jobs_last_24h ?? null);
            setCompanies(stats.total_companies || null);
        });
    }, []);

    const stats = useMemo(() => {
        const saved = jobs.filter((j) => j.status === "saved").length;
        const applied = jobs.filter((j) => j.status === "applied").length;
        const interview = jobs.filter((j) => j.status === "interview").length;
        const offer = jobs.filter((j) => j.status === "offer").length;
        const total = jobs.length;

        const now = new Date();
        const startOfWeek = new Date(now);
        startOfWeek.setDate(now.getDate() - now.getDay());
        startOfWeek.setHours(0, 0, 0, 0);

        const appliedThisWeek = jobs.filter((job) => {
            if (!["applied", "interview", "offer"].includes(job.status)) return false;
            return new Date(job.addedAt || job.date_posted || Date.now()) >= startOfWeek;
        }).length;

        return { saved, applied, interview, offer, total, appliedThisWeek };
    }, [jobs]);

    const sortedJobs = useMemo(() => {
        return [...jobs].sort((a, b) => {
            const dA = new Date(a.addedAt || a.date_posted || 0).getTime();
            const dB = new Date(b.addedAt || b.date_posted || 0).getTime();
            return dB - dA;
        });
    }, [jobs]);

    const weeklyGoal = 10;
    const progressPercent = Math.min((stats.appliedThisWeek / weeklyGoal) * 100, 100);
    const statCards = [
        { icon: Bookmark, label: "Tracked", value: stats.total, tone: "bg-surface-2 text-ink" },
        { icon: Send, label: "Applied", value: stats.applied, tone: "bg-blue-50 text-info" },
        { icon: Target, label: "Interviews", value: stats.interview, tone: "bg-amber-50 text-warning" },
        { icon: Trophy, label: "Offers", value: stats.offer, tone: "bg-green-50 text-success" },
    ];

    return (
        <div className="page-shell">
            <TopNav />

            <main className="mx-auto max-w-7xl px-5 py-8 sm:px-6">
                <header className="mb-8 grid gap-5 rounded-[30px] bg-ink p-6 text-white sm:p-8 lg:grid-cols-[1fr_auto] lg:items-end">
                    <div>
                        <p className="mb-3 text-xs font-black uppercase tracking-[0.18em] text-white/55">command center</p>
                        <h1 className="text-4xl font-black tracking-[-0.06em] sm:text-5xl">Your job search dashboard</h1>
                        <p className="mt-3 max-w-2xl text-sm font-medium text-white/65">
                            See what Nori found, where your saved roles stand, and what needs your attention next.
                        </p>
                    </div>
                    <Link href="/tracker" className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-black text-ink transition hover:bg-surface-2">
                        Kanban tracker
                        <ArrowRight className="h-4 w-4" />
                    </Link>
                </header>

                {jobs.length === 0 ? (
                    <div className="nori-panel p-12 text-center">
                        <div className="mx-auto mb-6 grid h-20 w-20 place-items-center rounded-full bg-surface-2">
                            <Bookmark className="h-9 w-9 text-ink" />
                        </div>
                        <h2 className="text-2xl font-black tracking-[-0.04em] text-ink">No applications yet</h2>
                        <p className="mx-auto mt-2 max-w-md text-sm font-medium text-text-secondary">
                            Save jobs from the board and Nori will help you keep the search tidy here.
                        </p>
                        <Link href="/jobs" className="btn-primary mt-6">
                            Explore jobs
                        </Link>
                    </div>
                ) : (
                    <>
                        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
                            {statCards.map((stat) => (
                                <div key={stat.label} className="stat-card flex items-center gap-4">
                                    <span className={`grid h-12 w-12 place-items-center rounded-2xl ${stat.tone}`}>
                                        <stat.icon className="h-5 w-5" />
                                    </span>
                                    <div>
                                        <p className="text-3xl font-black tracking-tight text-ink">{stat.value}</p>
                                        <p className="text-xs font-black uppercase tracking-[0.16em] text-text-secondary">{stat.label}</p>
                                    </div>
                                </div>
                            ))}
                        </div>

                        <div className="mb-6 grid gap-6 lg:grid-cols-3">
                            <section className="nori-panel p-6">
                                <div className="mb-4 flex items-center gap-2">
                                    <Activity className="h-5 w-5 text-ink" />
                                    <h2 className="font-black text-ink">Weekly goal</h2>
                                </div>
                                <div className="mb-3 flex items-end justify-between">
                                    <p>
                                        <span className="text-4xl font-black text-ink">{stats.appliedThisWeek}</span>
                                        <span className="ml-1 font-bold text-text-secondary">/ {weeklyGoal} apps</span>
                                    </p>
                                    <span className="text-sm font-black text-ink">{Math.round(progressPercent)}%</span>
                                </div>
                                <div className="h-3 overflow-hidden rounded-full bg-surface-2">
                                    <div className="h-full rounded-full bg-ink transition-all duration-700" style={{ width: `${progressPercent}%` }} />
                                </div>
                                <p className="mt-4 text-sm font-medium text-text-secondary">
                                    {stats.appliedThisWeek >= weeklyGoal ? "Goal reached. Keep the momentum going." : `${weeklyGoal - stats.appliedThisWeek} more applications to hit this week's target.`}
                                </p>
                            </section>

                            <section className="nori-panel p-6 lg:col-span-2">
                                <div className="mb-4 flex items-center gap-2">
                                    <Sparkles className="h-5 w-5 text-ink" />
                                    <h2 className="font-black text-ink">Nori activity</h2>
                                </div>
                                <div className="grid gap-3 sm:grid-cols-3">
                                    <div className="rounded-2xl bg-surface-2 p-4">
                                        <p className="text-3xl font-black text-ink">{freshJobs !== null ? freshJobs.toLocaleString() : "-"}</p>
                                        <p className="text-xs font-black uppercase tracking-[0.14em] text-text-secondary">new in 24h</p>
                                    </div>
                                    <div className="rounded-2xl bg-surface-2 p-4">
                                        <p className="text-3xl font-black text-ink">{companies !== null ? companies.toLocaleString() : "-"}</p>
                                        <p className="text-xs font-black uppercase tracking-[0.14em] text-text-secondary">companies</p>
                                    </div>
                                    <div className="rounded-2xl bg-surface-2 p-4">
                                        <p className="text-3xl font-black text-ink">{stats.saved}</p>
                                        <p className="text-xs font-black uppercase tracking-[0.14em] text-text-secondary">waiting review</p>
                                    </div>
                                </div>
                            </section>
                        </div>

                        <section className="nori-panel mb-6 p-6">
                            <div className="mb-4 flex items-center gap-2">
                                <BarChart3 className="h-5 w-5 text-ink" />
                                <h2 className="font-black text-ink">Pipeline by stage</h2>
                            </div>
                            <StageChart saved={stats.saved} applied={stats.applied} interview={stats.interview} offer={stats.offer} />
                        </section>

                        <section className="nori-panel overflow-hidden">
                            <div className="border-b border-border px-6 py-5">
                                <h2 className="font-black text-ink">Recent notes</h2>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-left">
                                    <thead>
                                        <tr className="border-b border-border text-xs font-black uppercase tracking-[0.16em] text-text-secondary">
                                            <th className="px-6 py-4">Company and role</th>
                                            <th className="px-6 py-4">Status</th>
                                            <th className="hidden px-6 py-4 md:table-cell">Location</th>
                                            <th className="hidden px-6 py-4 sm:table-cell">Added</th>
                                            <th className="px-6 py-4 text-right">Open</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-border">
                                        {sortedJobs.map((job) => {
                                            const company = displayCompany(job);
                                            const addedDate = new Date(job.addedAt || job.date_posted || Date.now());
                                            return (
                                                <tr key={job.internal_hash} className="transition hover:bg-surface-2/70">
                                                    <td className="px-6 py-4">
                                                        <div className="flex items-center gap-3">
                                                            <CompanyLogo company={company} size="sm" />
                                                            <div>
                                                                <p className="line-clamp-1 font-black text-ink">{company}</p>
                                                                <p className="line-clamp-1 text-sm font-medium text-text-secondary">{displayTitle(job)}</p>
                                                            </div>
                                                        </div>
                                                    </td>
                                                    <td className="px-6 py-4">
                                                        <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-black capitalize ${STATUS_COLORS[job.status] || STATUS_COLORS.saved}`}>
                                                            {job.status || "saved"}
                                                        </span>
                                                    </td>
                                                    <td className="hidden px-6 py-4 md:table-cell">
                                                        <span className="inline-flex items-center gap-1.5 text-sm font-medium text-text-secondary">
                                                            <MapPin className="h-4 w-4" />
                                                            {job.location || "Remote"}
                                                        </span>
                                                    </td>
                                                    <td className="hidden px-6 py-4 text-sm font-medium text-text-secondary sm:table-cell">
                                                        <span className="inline-flex items-center gap-1.5">
                                                            <Calendar className="h-4 w-4" />
                                                            {addedDate.toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                                                        </span>
                                                    </td>
                                                    <td className="px-6 py-4 text-right">
                                                        <a href={job.url} target="_blank" rel="noopener noreferrer" className="inline-flex rounded-xl p-2 text-text-secondary transition hover:bg-white hover:text-ink">
                                                            <ExternalLink className="h-4 w-4" />
                                                        </a>
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        </section>
                    </>
                )}
            </main>
        </div>
    );
}
