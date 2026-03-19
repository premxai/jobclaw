"use client";
import { useState, useEffect, useMemo } from "react";
import TopNav from "@/components/TopNav";
import CompanyLogo from "@/components/CompanyLogo";
import { Activity, Send, Target, Trophy, Briefcase, Calendar, MapPin, ExternalLink, Flame } from "lucide-react";
import Link from "next/link";

interface TrackedJob {
    internal_hash: string;
    title: string;
    company: string;
    location: string;
    url: string;
    date_posted: string;
    source_ats: string;
    status: string;
    addedAt?: string;
    keywords_matched?: string;
}

const STATUS_COLORS: Record<string, { bg: string, text: string, border: string }> = {
    saved: { bg: "bg-gray-100", text: "text-gray-600", border: "border-gray-200" },
    applied: { bg: "bg-blue-50", text: "text-blue-600", border: "border-blue-200" },
    interview: { bg: "bg-amber-50", text: "text-amber-600", border: "border-amber-200" },
    offer: { bg: "bg-green-50", text: "text-green-600", border: "border-green-200" },
};

export default function DashboardPage() {
    const [jobs, setJobs] = useState<TrackedJob[]>([]);

    useEffect(() => {
        const saved = localStorage.getItem("jobclaw_saved");
        if (saved) {
            try { setJobs(JSON.parse(saved)); } catch { }
        }
    }, []);

    // Derived stats
    const stats = useMemo(() => {
        const saved = jobs.filter((j) => j.status === "saved").length;
        const applied = jobs.filter((j) => j.status === "applied").length;
        const interview = jobs.filter((j) => j.status === "interview").length;
        const offer = jobs.filter((j) => j.status === "offer").length;
        const total = jobs.length;

        // Calculate this week's applications
        const now = new Date();
        const startOfWeek = new Date(now.setDate(now.getDate() - now.getDay()));
        startOfWeek.setHours(0, 0, 0, 0);

        const appliedThisWeek = jobs.filter(j => {
            if (j.status !== "applied" && j.status !== "interview" && j.status !== "offer") return false;
            const d = new Date(j.addedAt || new Date().toISOString());
            return d >= startOfWeek;
        }).length;

        return { saved, applied, interview, offer, total, appliedThisWeek };
    }, [jobs]);

    // Sort jobs by most recently added/updated for the table
    const sortedJobs = useMemo(() => {
        return [...jobs].sort((a, b) => {
            const dA = new Date(a.addedAt || a.date_posted || 0).getTime();
            const dB = new Date(b.addedAt || b.date_posted || 0).getTime();
            return dB - dA;
        });
    }, [jobs]);

    const statCards = [
        { icon: Briefcase, label: "Total Tracked", value: stats.total, color: "text-accent", bg: "bg-accent/10" },
        { icon: Send, label: "Applied", value: stats.applied, color: "text-blue-600", bg: "bg-blue-50" },
        { icon: Target, label: "Interviews", value: stats.interview, color: "text-amber-600", bg: "bg-amber-50" },
        { icon: Trophy, label: "Offers", value: stats.offer, color: "text-green-600", bg: "bg-green-50" },
    ];

    const weeklyGoal = 10;
    const progressPercent = Math.min((stats.appliedThisWeek / weeklyGoal) * 100, 100);

    return (
        <div className="min-h-screen bg-background">
            <TopNav />

            <div className="max-w-7xl mx-auto px-6 py-8">
                <div className="mb-8 flex items-center justify-between">
                    <div>
                        <h1 className="text-3xl font-bold tracking-tight mb-1 text-text-primary">Dashboard</h1>
                        <p className="text-text-secondary text-sm">
                            Manage and track your active job applications
                        </p>
                    </div>
                    <Link href="/tracker" className="btn-outline flex items-center gap-2">
                        <Activity className="w-4 h-4" />
                        Kanban View
                    </Link>
                </div>

                {jobs.length === 0 ? (
                    // Empty state (Simplify style)
                    <div className="bg-white rounded-xl border border-border p-12 text-center animate-fade-in shadow-sm mt-10">
                        <div className="w-20 h-20 bg-accent/10 rounded-full flex items-center justify-center mx-auto mb-6">
                            <Briefcase className="w-10 h-10 text-accent" />
                        </div>
                        <h2 className="text-2xl font-bold text-text-primary mb-2">No applications yet</h2>
                        <p className="text-text-secondary mb-8 max-w-md mx-auto">
                            Your tracker is empty! Start saving jobs from your feed to keep track of your job search progress.
                        </p>
                        <Link href="/jobs" className="btn-primary inline-flex">
                            Explore Jobs
                        </Link>
                    </div>
                ) : (
                    <>
                        {/* Top Stats Row */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-5 mb-8">
                            {statCards.map((stat, i) => (
                                <div key={i} className="bg-white rounded-xl border border-border p-5 flex items-center gap-4 animate-slide-up shadow-sm hover:shadow-md transition-shadow" style={{ animationDelay: `${i * 50}ms` }}>
                                    <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${stat.bg}`}>
                                        <stat.icon className={`w-6 h-6 ${stat.color}`} />
                                    </div>
                                    <div>
                                        <p className="text-2xl font-bold text-text-primary">{stat.value}</p>
                                        <p className="text-xs font-medium text-text-secondary uppercase tracking-wider">{stat.label}</p>
                                    </div>
                                </div>
                            ))}
                        </div>

                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
                            {/* Weekly Goal Widget */}
                            <div className="bg-white rounded-xl border border-border p-6 shadow-sm animate-fade-in lg:col-span-1">
                                <div className="flex items-center gap-2 mb-4">
                                    <Flame className="w-5 h-5 text-accent" />
                                    <h2 className="font-semibold text-text-primary">Weekly Goal</h2>
                                </div>
                                <div className="flex items-end justify-between mb-3">
                                    <div>
                                        <span className="text-3xl font-bold text-text-primary">{stats.appliedThisWeek}</span>
                                        <span className="text-text-secondary ml-1">/ {weeklyGoal} apps</span>
                                    </div>
                                    <span className="text-sm font-medium text-accent">
                                        {Math.round(progressPercent)}%
                                    </span>
                                </div>
                                <div className="w-full bg-gray-100 rounded-full h-2.5 mb-2 overflow-hidden">
                                    <div
                                        className="bg-accent h-2.5 rounded-full transition-all duration-1000 ease-out"
                                        style={{ width: `${progressPercent}%` }}
                                    ></div>
                                </div>
                                <p className="text-xs text-text-secondary mt-3">
                                    {stats.appliedThisWeek >= weeklyGoal
                                        ? "🎉 Goal reached! You're on fire this week."
                                        : `${weeklyGoal - stats.appliedThisWeek} more to reach your weekly goal.`}
                                </p>
                            </div>

                            {/* Info Banner */}
                            <div className="bg-accent/5 rounded-xl border border-accent/20 p-6 flex flex-col justify-center animate-fade-in lg:col-span-2">
                                <h3 className="font-semibold text-text-primary mb-2 text-lg">Keep up the momentum! 🚀</h3>
                                <p className="text-text-secondary text-sm mb-4">
                                    You're tracking {stats.total} jobs in your pipeline. Make sure to update statuses in your Kanban board when you hear back from recruiters.
                                </p>
                                <div>
                                    <Link href="/tracker" className="text-sm font-medium text-accent hover:underline flex items-center gap-1">
                                        Update statuses in Kanban <span aria-hidden="true">→</span>
                                    </Link>
                                </div>
                            </div>
                        </div>

                        {/* Recent Applications Table */}
                        <div className="bg-white rounded-xl border border-border overflow-hidden shadow-sm animate-slide-up" style={{ animationDelay: "200ms" }}>
                            <div className="px-6 py-5 border-b border-border bg-gray-50/50 flex justify-between items-center">
                                <h2 className="font-semibold text-text-primary">Recent Applications</h2>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-left border-collapse">
                                    <thead>
                                        <tr className="border-b border-border text-xs font-semibold text-text-secondary uppercase tracking-wider bg-gray-50/20">
                                            <th className="px-6 py-4">Company & Role</th>
                                            <th className="px-6 py-4">Status</th>
                                            <th className="px-6 py-4 hidden md:table-cell">Location</th>
                                            <th className="px-6 py-4 hidden sm:table-cell">Added</th>
                                            <th className="px-6 py-4 text-right">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-border">
                                        {sortedJobs.map((job) => {
                                            const statusStyle = STATUS_COLORS[job.status] || STATUS_COLORS.saved;
                                            const addedDate = new Date(job.addedAt || job.date_posted || Date.now());

                                            return (
                                                <tr key={job.internal_hash} className="hover:bg-gray-50/50 transition-colors group">
                                                    <td className="px-6 py-4">
                                                        <div className="flex items-center gap-3">
                                                            <div className="w-10 h-10 shrink-0">
                                                                <CompanyLogo company={job.company} size="sm" />
                                                            </div>
                                                            <div>
                                                                <p className="font-semibold text-text-primary group-hover:text-accent transition-colors line-clamp-1">
                                                                    {job.company}
                                                                </p>
                                                                <p className="text-sm text-text-secondary line-clamp-1">{job.title}</p>
                                                            </div>
                                                        </div>
                                                    </td>
                                                    <td className="px-6 py-4">
                                                        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium border ${statusStyle.bg} ${statusStyle.text} ${statusStyle.border} capitalize`}>
                                                            {job.status}
                                                        </span>
                                                    </td>
                                                    <td className="px-6 py-4 hidden md:table-cell">
                                                        <div className="flex items-center gap-1.5 text-sm text-text-secondary">
                                                            <MapPin className="w-3.5 h-3.5" />
                                                            <span className="line-clamp-1">{job.location || "Remote"}</span>
                                                        </div>
                                                    </td>
                                                    <td className="px-6 py-4 hidden sm:table-cell text-sm text-text-secondary">
                                                        <div className="flex items-center gap-1.5">
                                                            <Calendar className="w-3.5 h-3.5" />
                                                            {addedDate.toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                                                        </div>
                                                    </td>
                                                    <td className="px-6 py-4 text-right">
                                                        {job.url ? (
                                                            <a
                                                                href={job.url}
                                                                target="_blank"
                                                                rel="noopener noreferrer"
                                                                className="inline-flex items-center justify-center p-2 rounded-lg text-text-secondary hover:text-accent hover:bg-accent/10 transition-colors tooltip-trigger"
                                                                title="View original posting"
                                                            >
                                                                <ExternalLink className="w-4 h-4" />
                                                            </a>
                                                        ) : (
                                                            <span className="text-xs text-gray-400">No URL</span>
                                                        )}
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
