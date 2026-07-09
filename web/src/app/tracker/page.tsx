"use client";

import type React from "react";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, Plus, X } from "lucide-react";
import NoriAppSidebar from "@/components/NoriAppSidebar";
import { Job } from "@/components/JobCard";
import { displayCompany, displayTitle } from "@/lib/job-display";
import { useSavedJobsStorageKey } from "@/lib/use-saved-jobs-storage-key";

const COLUMNS = [
    { id: "saved", label: "Saved", tone: "bg-[#EEF1DD] text-[#526736]" },
    { id: "applied", label: "Applied", tone: "bg-[#E7ECD3] text-[#526736]" },
    { id: "interview", label: "Interview", tone: "bg-[#F4E9BE] text-[#7A6934]" },
    { id: "offer", label: "Offer", tone: "bg-[#DCE8C9] text-[#415329]" },
    { id: "rejected", label: "Rejected", tone: "bg-[#F1D8CF] text-[#914F40]" },
];

const columnIds = COLUMNS.map((column) => column.id);

interface TrackedJob extends Job {
    status?: string | null;
    addedAt?: string | null;
    updatedAt?: string | null;
}

interface NewRoleForm {
    company: string;
    title: string;
    location: string;
    url: string;
    status: string;
}

const initialForm: NewRoleForm = {
    company: "",
    title: "",
    location: "Remote",
    url: "",
    status: "saved",
};

function normalizeStatus(status?: string | null) {
    const value = (status || "saved").toLowerCase();
    if (value === "oa" || value === "phone_screen" || value === "onsite") return "interview";
    if (value === "withdrawn") return "rejected";
    return columnIds.includes(value) ? value : "saved";
}

function RolePill({
    job,
    onDragStart,
    onRemove,
}: {
    job: TrackedJob;
    onDragStart: (hash: string) => void;
    onRemove: (hash: string) => void;
}) {
    const title = displayTitle(job);
    const company = displayCompany(job);

    return (
        <article
            draggable
            onDragStart={(event) => {
                event.dataTransfer.setData("text/plain", job.internal_hash);
                onDragStart(job.internal_hash);
            }}
            className="rounded-2xl border border-[#D8C9A7] bg-[#FFF9EC] px-4 py-3 shadow-[0_6px_14px_rgba(70,45,16,0.06)] transition hover:-translate-y-0.5 hover:shadow-[0_12px_22px_rgba(70,45,16,0.10)]"
        >
            <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                    <h3 className="line-clamp-1 font-serif text-base font-bold leading-tight tracking-[-0.025em] text-[#1F281B]">{title}</h3>
                    <p className="mt-0.5 line-clamp-1 text-sm font-semibold text-[#526736]">{company}</p>
                </div>
                <button
                    type="button"
                    onClick={() => onRemove(job.internal_hash)}
                    className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-[#7B7F70] transition hover:bg-[#F7EED7] hover:text-red-600"
                    aria-label={`Remove ${title}`}
                >
                    <X className="h-3.5 w-3.5" />
                </button>
            </div>
        </article>
    );
}

function KanbanColumn({
    column,
    jobs,
    isOver,
    onDragStart,
    onDragOver,
    onDragLeave,
    onDrop,
    onRemove,
}: {
    column: (typeof COLUMNS)[number];
    jobs: TrackedJob[];
    isOver: boolean;
    onDragStart: (hash: string) => void;
    onDragOver: (event: React.DragEvent, columnId: string) => void;
    onDragLeave: () => void;
    onDrop: (columnId: string) => void;
    onRemove: (hash: string) => void;
}) {
    return (
        <section
            className={`min-h-[430px] rounded-[22px] border border-[#D8C9A7] bg-[#FFF9EC]/72 p-3.5 transition ${isOver ? "ring-2 ring-[#526736]" : ""}`}
            onDragOver={(event) => onDragOver(event, column.id)}
            onDragLeave={onDragLeave}
            onDrop={() => onDrop(column.id)}
        >
            <div className="mb-3 flex items-center justify-between gap-3">
                <span className={`inline-flex h-9 items-center rounded-full px-3 text-sm font-black ${column.tone}`}>{column.label}</span>
                <span className="grid h-8 min-w-8 place-items-center rounded-full bg-[#F7EED7] px-2 text-xs font-black text-[#526736]">{jobs.length}</span>
            </div>
            <div className="space-y-2.5">
                {jobs.length === 0 ? (
                    <div className="grid min-h-[90px] place-items-center rounded-2xl border border-dashed border-[#D8C9A7] bg-[#FFF9EC]/58 px-3 text-center text-xs font-bold text-[#7B7F70]">
                        Drop roles here
                    </div>
                ) : (
                    jobs.map((job) => <RolePill key={job.internal_hash} job={job} onDragStart={onDragStart} onRemove={onRemove} />)
                )}
            </div>
        </section>
    );
}

export default function TrackerPage() {
    const [jobs, setJobs] = useState<TrackedJob[]>([]);
    const [draggedJob, setDraggedJob] = useState<string | null>(null);
    const [dragOverColumn, setDragOverColumn] = useState<string | null>(null);
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState<NewRoleForm>(initialForm);
    const savedJobsStorageKey = useSavedJobsStorageKey();

    useEffect(() => {
        try {
            const parsed = JSON.parse(localStorage.getItem(savedJobsStorageKey) || "[]") as TrackedJob[];
            setJobs(
                Array.isArray(parsed)
                    ? parsed.map((job) => ({
                          ...job,
                          status: normalizeStatus(job.status),
                          addedAt: job.addedAt || job.first_seen || new Date().toISOString(),
                          updatedAt: job.updatedAt || job.addedAt || job.first_seen || new Date().toISOString(),
                      }))
                    : [],
            );
        } catch {
            setJobs([]);
        }
    }, [savedJobsStorageKey]);

    const persist = useCallback(
        (updatedJobs: TrackedJob[]) => {
            setJobs(updatedJobs);
            localStorage.setItem(savedJobsStorageKey, JSON.stringify(updatedJobs));
        },
        [savedJobsStorageKey],
    );

    const getColumnJobs = (columnId: string) => jobs.filter((job) => normalizeStatus(job.status) === columnId);
    const moveJob = (hash: string, status: string) => persist(jobs.map((job) => (job.internal_hash === hash ? { ...job, status, updatedAt: new Date().toISOString() } : job)));
    const removeJob = (hash: string) => persist(jobs.filter((job) => job.internal_hash !== hash));

    const handleDragOver = (event: React.DragEvent, columnId: string) => {
        event.preventDefault();
        const hash = event.dataTransfer.getData("text/plain");
        if (hash) setDraggedJob(hash);
        setDragOverColumn(columnId);
    };

    const handleDrop = (columnId: string) => {
        if (!draggedJob) return;
        moveJob(draggedJob, columnId);
        setDraggedJob(null);
        setDragOverColumn(null);
    };

    const addRole = (event: React.FormEvent) => {
        event.preventDefault();
        const now = new Date().toISOString();
        const role: TrackedJob = {
            id: `manual-${Date.now()}`,
            internal_hash: `manual-${Date.now()}`,
            company: form.company.trim() || "Manual role",
            title: form.title.trim() || "Untitled role",
            location: form.location.trim() || "Location not listed",
            url: form.url.trim() || "#",
            date_posted: now,
            first_seen: now,
            source_ats: "manual",
            keywords_matched: "[]",
            status: normalizeStatus(form.status),
            addedAt: now,
            updatedAt: now,
        };
        persist([role, ...jobs]);
        setForm(initialForm);
        setShowForm(false);
    };

    return (
        <div className="min-h-screen bg-[#F4EFE4] text-[#1F281B]">
            <NoriAppSidebar />

            <main className="px-5 py-7 sm:px-6 lg:ml-[280px]">
                <header className="flex min-h-[156px] flex-col gap-5 rounded-[28px] bg-[#526736] px-6 py-7 text-white shadow-[0_18px_42px_rgba(38,58,34,0.18)] sm:px-[34px] lg:flex-row lg:items-center lg:justify-between">
                    <div>
                        <p className="mb-3 text-sm font-bold uppercase tracking-[0.12em] text-white/70">Tracker</p>
                        <h1 className="font-serif text-[42px] font-bold leading-[0.98] tracking-[-0.055em] sm:text-[56px]">Application tracker</h1>
                        <p className="mt-4 max-w-[720px] text-[16px] leading-7 text-white/78">
                            Move roles through a simple saved, applied, interview, offer, and rejected workflow.
                        </p>
                    </div>
                    <div className="flex flex-wrap gap-3">
                        <button type="button" onClick={() => setShowForm(true)} className="inline-flex h-12 items-center gap-2 rounded-2xl bg-white px-[22px] text-base font-bold text-[#1F281B] transition hover:bg-[#F7EED7]">
                            <Plus className="h-4 w-4" />
                            Add role
                        </button>
                        <Link href="/saved-roles" className="inline-flex h-12 items-center gap-2 rounded-2xl border border-white/20 bg-white/15 px-[22px] text-base font-semibold text-white transition hover:bg-white/20">
                            Saved roles
                            <ArrowRight className="h-4 w-4" />
                        </Link>
                    </div>
                </header>

                {showForm && (
                    <form onSubmit={addRole} className="mt-5 rounded-[20px] border border-[#D8C9A7] bg-[#FFF9EC] p-5 shadow-[0_8px_18px_rgba(70,45,16,0.06)]">
                        <div className="mb-4 flex items-center justify-between gap-3">
                            <h2 className="font-serif text-2xl font-bold tracking-[-0.035em]">New application</h2>
                            <button type="button" onClick={() => setShowForm(false)} className="grid h-9 w-9 place-items-center rounded-xl border border-[#D8C9A7]" aria-label="Close new application form">
                                <X className="h-4 w-4" />
                            </button>
                        </div>
                        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                            <input value={form.company} onChange={(event) => setForm({ ...form, company: event.target.value })} placeholder="Company" className="h-11 rounded-xl border border-[#D8C9A7] bg-white px-3 text-sm" />
                            <input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder="Role title" className="h-11 rounded-xl border border-[#D8C9A7] bg-white px-3 text-sm" />
                            <input value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} placeholder="Location" className="h-11 rounded-xl border border-[#D8C9A7] bg-white px-3 text-sm" />
                            <input value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} placeholder="Job link" className="h-11 rounded-xl border border-[#D8C9A7] bg-white px-3 text-sm" />
                            <select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })} className="h-11 rounded-xl border border-[#D8C9A7] bg-white px-3 text-sm">
                                {COLUMNS.map((column) => (
                                    <option key={column.id} value={column.id}>
                                        {column.label}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <button type="submit" className="mt-3 h-11 rounded-xl bg-[#526736] px-5 text-sm font-bold text-white">Add to tracker</button>
                    </form>
                )}

                {jobs.length === 0 ? (
                    <section className="mt-5 rounded-[24px] border border-[#D8C9A7] bg-[#FFF9EC] py-20 text-center shadow-[0_8px_18px_rgba(70,45,16,0.06)]">
                        <CheckCircle2 className="mx-auto mb-5 h-12 w-12 text-[#526736]" />
                        <h2 className="font-serif text-3xl font-bold tracking-[-0.04em]">No tracked roles yet</h2>
                        <p className="mx-auto mt-2 max-w-md text-sm font-medium text-[#5F665C]">Save from the live feed or add a role manually to start your application pipeline.</p>
                    </section>
                ) : (
                    <div className="mt-5 overflow-x-auto pb-2">
                        <section className="grid min-w-[1180px] grid-cols-5 gap-4">
                            {COLUMNS.map((column) => (
                                <KanbanColumn
                                    key={column.id}
                                    column={column}
                                    jobs={getColumnJobs(column.id)}
                                    isOver={dragOverColumn === column.id}
                                    onDragStart={setDraggedJob}
                                    onDragOver={handleDragOver}
                                    onDragLeave={() => setDragOverColumn(null)}
                                    onDrop={handleDrop}
                                    onRemove={removeJob}
                                />
                            ))}
                        </section>
                    </div>
                )}
            </main>
        </div>
    );
}
