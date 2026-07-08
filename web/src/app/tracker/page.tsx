"use client";

import { useCallback, useEffect, useState } from "react";
import type React from "react";
import Link from "next/link";
import NoriAppSidebar from "@/components/NoriAppSidebar";
import CompanyLogo from "@/components/CompanyLogo";
import { Job } from "@/components/JobCard";
import { displayCompany, displayTitle } from "@/lib/job-display";
import { Bookmark, CheckCircle2, ExternalLink, GripVertical, Send, Target, Trash2, Trophy } from "lucide-react";

const COLUMNS = [
    { id: "saved", label: "Saved", icon: Bookmark, color: "bg-surface-2 text-ink" },
    { id: "applied", label: "Applied", icon: Send, color: "bg-blue-50 text-info" },
    { id: "oa", label: "OA", icon: CheckCircle2, color: "bg-lime-50 text-[#526736]" },
    { id: "interview", label: "Interview", icon: Target, color: "bg-amber-50 text-warning" },
    { id: "offer", label: "Offer", icon: Trophy, color: "bg-green-50 text-success" },
    { id: "rejected", label: "Rejected", icon: Trash2, color: "bg-red-50 text-red-600" },
    { id: "withdrawn", label: "Withdrawn", icon: ExternalLink, color: "bg-neutral-100 text-neutral-600" },
];

interface TrackedJob extends Job {
    status: string;
    addedAt?: string;
}

export default function TrackerPage() {
    const [jobs, setJobs] = useState<TrackedJob[]>([]);
    const [draggedJob, setDraggedJob] = useState<string | null>(null);
    const [dragOverColumn, setDragOverColumn] = useState<string | null>(null);

    useEffect(() => {
        const saved = localStorage.getItem("jobclaw_saved");
        if (saved) {
            try {
                const parsed: TrackedJob[] = JSON.parse(saved);
                setJobs(parsed.map((j) => ({ ...j, status: j.status || "saved", addedAt: j.addedAt || new Date().toISOString() })));
            } catch { }
        }
    }, []);

    const persist = useCallback((updatedJobs: TrackedJob[]) => {
        setJobs(updatedJobs);
        localStorage.setItem("jobclaw_saved", JSON.stringify(updatedJobs));
    }, []);

    const handleDragStart = (hash: string) => setDraggedJob(hash);
    const handleDragOver = (e: React.DragEvent, columnId: string) => {
        e.preventDefault();
        setDragOverColumn(columnId);
    };
    const handleDragLeave = () => setDragOverColumn(null);
    const handleDrop = (columnId: string) => {
        if (!draggedJob) return;
        persist(jobs.map((j) => (j.internal_hash === draggedJob ? { ...j, status: columnId } : j)));
        setDraggedJob(null);
        setDragOverColumn(null);
    };
    const removeJob = (hash: string) => persist(jobs.filter((j) => j.internal_hash !== hash));
    const getColumnJobs = (columnId: string) => jobs.filter((j) => j.status === columnId);

    return (
        <div className="page-shell">
            <NoriAppSidebar />

            <main className="px-5 py-8 sm:px-6 lg:ml-[280px]">
                <header className="mb-8 flex flex-col gap-4 rounded-[30px] bg-ink p-6 text-white sm:p-8 lg:flex-row lg:items-end lg:justify-between">
                    <div>
                        <p className="mb-3 text-xs font-black uppercase tracking-[0.18em] text-white/55">tracker</p>
                        <h1 className="text-4xl font-black tracking-[-0.06em] sm:text-5xl">Your job tracker</h1>
                        <p className="mt-3 max-w-2xl text-sm font-medium text-white/65">
                            Drag saved roles through your pipeline. These stages feed the profile chart.
                        </p>
                    </div>
                    <Link href="/jobs" className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-black text-ink transition hover:bg-surface-2">
                        Browse jobs
                        <ExternalLink className="h-4 w-4" />
                    </Link>
                </header>

                {jobs.length === 0 ? (
                    <div className="nori-panel py-20 text-center">
                        <div className="mx-auto mb-6 grid h-20 w-20 place-items-center rounded-full bg-surface-2">
                            <CheckCircle2 className="h-9 w-9 text-ink" />
                        </div>
                        <h2 className="text-2xl font-black tracking-[-0.04em] text-ink">No tracked jobs yet</h2>
                        <p className="mx-auto mt-2 max-w-md text-sm font-medium text-text-secondary">
                            Browse the job board and hit Save or Apply to start your tracker.
                        </p>
                        <Link href="/jobs" className="btn-primary mt-6">
                            Browse jobs
                        </Link>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-7">
                        {COLUMNS.map((column) => {
                            const columnJobs = getColumnJobs(column.id);
                            const isOver = dragOverColumn === column.id;
                            const Icon = column.icon;
                            return (
                                <section
                                    key={column.id}
                                    className={`kanban-column transition ${isOver ? "ring-2 ring-ink" : ""}`}
                                    onDragOver={(e) => handleDragOver(e, column.id)}
                                    onDragLeave={handleDragLeave}
                                    onDrop={() => handleDrop(column.id)}
                                >
                                    <div className="mb-4 flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <span className={`grid h-9 w-9 place-items-center rounded-xl ${column.color}`}>
                                                <Icon className="h-4 w-4" />
                                            </span>
                                            <div>
                                                <h2 className="text-sm font-black text-ink">{column.label}</h2>
                                                <p className="text-xs font-semibold text-text-secondary">{columnJobs.length} jobs</p>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="space-y-3">
                                        {columnJobs.map((job) => {
                                            const company = displayCompany(job);
                                            return (
                                                <article
                                                    key={job.internal_hash}
                                                    draggable
                                                    onDragStart={() => handleDragStart(job.internal_hash)}
                                                    className={`kanban-card ${draggedJob === job.internal_hash ? "scale-95 opacity-50" : ""}`}
                                                >
                                                    <div className="flex items-start gap-3">
                                                        <GripVertical className="mt-1 h-4 w-4 shrink-0 text-text-secondary opacity-40" />
                                                        <div className="min-w-0 flex-1">
                                                            <div className="mb-2 flex items-center gap-2">
                                                                <CompanyLogo company={company} size="sm" />
                                                                <span className="truncate text-xs font-black text-ink">{company}</span>
                                                            </div>
                                                            <p className="line-clamp-2 text-sm font-black leading-tight text-ink">{displayTitle(job)}</p>
                                                            <p className="mt-2 truncate text-xs font-semibold text-text-secondary">{job.location || "Location not listed"}</p>
                                                        </div>
                                                    </div>
                                                    <div className="mt-4 flex items-center gap-1 border-t border-border pt-3">
                                                        <a href={job.url} target="_blank" rel="noopener noreferrer" className="rounded-lg p-2 text-text-secondary transition hover:bg-white hover:text-ink" title="Open listing">
                                                            <ExternalLink className="h-4 w-4" />
                                                        </a>
                                                        <button onClick={() => removeJob(job.internal_hash)} className="ml-auto rounded-lg p-2 text-text-secondary transition hover:bg-white hover:text-red-500" title="Remove">
                                                            <Trash2 className="h-4 w-4" />
                                                        </button>
                                                    </div>
                                                </article>
                                            );
                                        })}

                                        {columnJobs.length === 0 && (
                                            <div className="rounded-2xl border border-dashed border-border bg-surface-2 py-8 text-center text-xs font-bold text-text-secondary">
                                                {column.id === "saved" ? "Save jobs from the board" : "Drag jobs here"}
                                            </div>
                                        )}
                                    </div>
                                </section>
                            );
                        })}
                    </div>
                )}
            </main>
        </div>
    );
}
