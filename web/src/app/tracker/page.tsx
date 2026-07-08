"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type React from "react";
import Link from "next/link";
import NoriAppSidebar from "@/components/NoriAppSidebar";
import CompanyLogo from "@/components/CompanyLogo";
import { Job } from "@/components/JobCard";
import { displayCompany, displayTitle } from "@/lib/job-display";
import {
    Archive,
    ArrowRight,
    Bookmark,
    CheckCircle2,
    ExternalLink,
    MoreHorizontal,
    Plus,
    Search,
    Send,
    Target,
    Trophy,
    X,
} from "lucide-react";

const MAIN_COLUMNS = [
    { id: "saved", label: "Saved", helper: "Ready to review", icon: Bookmark, pill: "bg-[#ECE6CF] text-[#6B6F45]" },
    { id: "applied", label: "Applied", helper: "Sent out", icon: Send, pill: "bg-[#E8ECD9] text-[#5D7440]" },
    { id: "oa", label: "OA", helper: "Assessment stage", icon: CheckCircle2, pill: "bg-[#F4E9BE] text-[#8B7437]" },
    { id: "interview", label: "Interview", helper: "In conversations", icon: Target, pill: "bg-[#F3E1B3] text-[#8A6830]" },
    { id: "offer", label: "Offer", helper: "Great news", icon: Trophy, pill: "bg-[#E0E9D1] text-[#58703B]" },
];

const CLOSED_COLUMNS = [
    { id: "rejected", label: "Rejected", helper: "Closed out", icon: X, pill: "bg-[#F1D8CF] text-[#9B5F4E]" },
    { id: "withdrawn", label: "Withdrawn", helper: "Archived", icon: Archive, pill: "bg-[#E8E3D8] text-[#6C675B]" },
];

const ALL_COLUMNS = [...MAIN_COLUMNS, ...CLOSED_COLUMNS];
const stageIds = ALL_COLUMNS.map((column) => column.id);

interface TrackedJob extends Job {
    status: string;
    addedAt?: string;
    updatedAt?: string;
    source?: string;
}

interface NewRoleForm {
    company: string;
    title: string;
    location: string;
    url: string;
    status: string;
    tags: string;
}

const initialForm: NewRoleForm = {
    company: "",
    title: "",
    location: "Remote",
    url: "",
    status: "saved",
    tags: "SWE, Remote",
};

function normalizeStatus(status?: string | null) {
    const value = (status || "saved").toLowerCase();
    return stageIds.includes(value) ? value : "saved";
}

function getCategory(job: TrackedJob) {
    try {
        const parsed = JSON.parse(job.keywords_matched || "[]");
        if (Array.isArray(parsed) && parsed.length > 0) return parsed.slice(0, 3);
    } catch {}
    return [];
}

function formatDate(value?: string) {
    if (!value) return "Today";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Today";
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function nextStage(status: string) {
    const index = MAIN_COLUMNS.findIndex((column) => column.id === status);
    if (index === -1) return "saved";
    return MAIN_COLUMNS[Math.min(index + 1, MAIN_COLUMNS.length - 1)].id;
}

function StatCard({ title, value, helper }: { title: string; value: string | number; helper: string }) {
    return (
        <article className="min-h-[110px] rounded-[18px] border border-[#DDD1B8] bg-[#FBF7EE] px-[22px] py-5 shadow-[0_8px_18px_rgba(44,30,12,0.05)]">
            <p className="mb-2.5 text-[13px] font-semibold text-[#7B7B72]">{title}</p>
            <p className="font-serif text-[34px] font-bold leading-none tracking-[-0.04em] text-[#1F281B]">{value}</p>
            <p className="mt-1.5 text-[13px] font-medium text-[#5E6258]">{helper}</p>
        </article>
    );
}

function EmptyColumn({ label }: { label: string }) {
    return (
        <div className="grid min-h-[120px] place-items-center rounded-2xl border border-dashed border-[#DCCFB4] bg-[#FBF7EE]/70 px-5 py-8 text-center">
            <div>
                <Bookmark className="mx-auto mb-3 h-5 w-5 text-[#8A877A]" />
                <p className="text-[13px] font-bold text-[#8A877A]">No roles here yet</p>
                <p className="mt-1 text-xs font-medium text-[#8A877A]">Move a job here when it reaches {label.toLowerCase()}.</p>
            </div>
        </div>
    );
}

function TrackerCard({
    job,
    compact,
    onDragStart,
    onMove,
    onRemove,
}: {
    job: TrackedJob;
    compact: boolean;
    onDragStart: (hash: string) => void;
    onMove: (hash: string, status: string) => void;
    onRemove: (hash: string) => void;
}) {
    const company = displayCompany(job);
    const title = displayTitle(job);
    const stage = ALL_COLUMNS.find((column) => column.id === job.status) || MAIN_COLUMNS[0];
    const tags = getCategory(job);
    const StageIcon = stage.icon;

    return (
        <article
            draggable
            onDragStart={(event) => {
                event.dataTransfer.setData("text/plain", job.internal_hash);
                onDragStart(job.internal_hash);
            }}
            className={`rounded-[18px] border border-[#DDD1B8] bg-[#FFFDF8] p-4 shadow-[0_6px_14px_rgba(44,30,12,0.05)] transition hover:-translate-y-0.5 hover:shadow-[0_12px_22px_rgba(44,30,12,0.08)] ${compact ? "p-3" : ""}`}
            tabIndex={0}
        >
            <div className="flex items-start justify-between gap-3">
                <CompanyLogo company={company} size="md" shape="rounded" />
                <span className={`inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-[11px] font-bold ${stage.pill}`}>
                    <StageIcon className="h-3.5 w-3.5" />
                    {stage.label}
                </span>
            </div>

            <p className="mt-3 text-sm font-bold text-[#1F281B]">{company}</p>
            <h3 className="mt-1 line-clamp-2 font-serif text-xl font-bold leading-[1.15] tracking-[-0.035em] text-[#1F281B]">{title}</h3>
            <p className="mt-2 text-sm font-medium text-[#5E6258]">{job.location || "Location not listed"}</p>

            {!compact && (
                <>
                    <div className="mt-2 text-xs leading-5 text-[#7B7B72]">
                        <p>Saved {formatDate(job.addedAt || job.first_seen || job.date_posted || undefined)}</p>
                        <p>Updated {formatDate(job.updatedAt || job.addedAt || job.first_seen || undefined)}</p>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                        {(tags.length ? tags : ["Direct apply", job.location?.toLowerCase().includes("remote") ? "Remote" : "Tracked"]).map((tag) => (
                            <span key={tag} className="inline-flex h-6 items-center rounded-full border border-[#E5DCC5] bg-[#F3EEDC] px-2.5 text-[11px] font-semibold text-[#6B6F45]">
                                {tag}
                            </span>
                        ))}
                    </div>
                </>
            )}

            <div className="mt-4 flex items-center gap-2">
                <button
                    type="button"
                    onClick={() => onMove(job.internal_hash, nextStage(job.status))}
                    className="inline-flex h-[38px] items-center gap-1.5 rounded-xl bg-[#5D7440] px-3.5 text-sm font-bold text-white transition hover:bg-[#47602F]"
                    aria-label={`Move ${title} to next stage`}
                >
                    Move
                    <ArrowRight className="h-4 w-4" />
                </button>
                <a
                    href={job.url || "#"}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex h-[38px] items-center gap-1.5 rounded-xl border border-[#DDD1B8] px-3.5 text-sm font-semibold text-[#1F281B] transition hover:bg-[#FBF7EE]"
                >
                    Open
                    <ExternalLink className="h-4 w-4" />
                </a>
                <button
                    type="button"
                    onClick={() => onRemove(job.internal_hash)}
                    className="ml-auto grid h-9 w-9 place-items-center rounded-[10px] border border-[#E5DCC5] bg-[#FBF7EE] text-[#7B7B72] transition hover:text-red-600"
                    aria-label={`Remove ${title}`}
                >
                    <MoreHorizontal className="h-4 w-4" />
                </button>
            </div>
        </article>
    );
}

function TrackerColumn({
    column,
    jobs,
    compact,
    dragOverColumn,
    onDragOver,
    onDragLeave,
    onDrop,
    onCardDragStart,
    onMove,
    onRemove,
}: {
    column: (typeof ALL_COLUMNS)[number];
    jobs: TrackedJob[];
    compact: boolean;
    dragOverColumn: string | null;
    onDragOver: (event: React.DragEvent, columnId: string) => void;
    onDragLeave: () => void;
    onDrop: (columnId: string) => void;
    onCardDragStart: (hash: string) => void;
    onMove: (hash: string, status: string) => void;
    onRemove: (hash: string) => void;
}) {
    const Icon = column.icon;
    const isOver = dragOverColumn === column.id;

    return (
        <section
            className={`min-h-[540px] rounded-[20px] border border-[#E7DCC6] bg-[rgba(255,251,244,0.7)] p-4 transition ${isOver ? "ring-2 ring-[#5D7440]" : ""}`}
            onDragOver={(event) => onDragOver(event, column.id)}
            onDragLeave={onDragLeave}
            onDrop={() => onDrop(column.id)}
            aria-label={`${column.label} column`}
        >
            <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                    <div className="flex items-center gap-2.5">
                        <Icon className="h-[22px] w-[22px] text-[#5D7440]" />
                        <h2 className="font-serif text-2xl font-bold tracking-[-0.035em] text-[#1F281B]">{column.label}</h2>
                    </div>
                    <p className="mt-0.5 text-xs font-medium text-[#7B7B72]">{column.helper}</p>
                </div>
                <span className="inline-flex h-7 items-center rounded-full bg-[#ECE6CF] px-2.5 text-xs font-bold text-[#5D7440]">{jobs.length}</span>
            </div>

            <div className="space-y-3.5">
                {jobs.length === 0 ? (
                    <EmptyColumn label={column.label} />
                ) : (
                    jobs.map((job) => <TrackerCard key={job.internal_hash} job={job} compact={compact} onDragStart={onCardDragStart} onMove={onMove} onRemove={onRemove} />)
                )}
            </div>
        </section>
    );
}

export default function TrackerPage() {
    const [jobs, setJobs] = useState<TrackedJob[]>([]);
    const [draggedJob, setDraggedJob] = useState<string | null>(null);
    const [dragOverColumn, setDragOverColumn] = useState<string | null>(null);
    const [search, setSearch] = useState("");
    const [locationFilter, setLocationFilter] = useState("all");
    const [statusFilter, setStatusFilter] = useState("all");
    const [sortMode, setSortMode] = useState("recent");
    const [compact, setCompact] = useState(false);
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState<NewRoleForm>(initialForm);

    useEffect(() => {
        try {
            const parsed = JSON.parse(localStorage.getItem("jobclaw_saved") || "[]") as TrackedJob[];
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
    }, []);

    const persist = useCallback((updatedJobs: TrackedJob[]) => {
        setJobs(updatedJobs);
        localStorage.setItem("jobclaw_saved", JSON.stringify(updatedJobs));
    }, []);

    const counts = useMemo(
        () =>
            ALL_COLUMNS.reduce<Record<string, number>>((acc, column) => {
                acc[column.id] = jobs.filter((job) => normalizeStatus(job.status) === column.id).length;
                return acc;
            }, {}),
        [jobs],
    );

    const appliedCount = counts.applied + counts.oa + counts.interview + counts.offer + counts.rejected + counts.withdrawn;
    const responseRate = appliedCount === 0 ? 0 : Math.round(((counts.oa + counts.interview + counts.offer) / appliedCount) * 100);

    const filteredJobs = useMemo(() => {
        const query = search.trim().toLowerCase();
        return jobs
            .filter((job) => {
                const haystack = `${displayCompany(job)} ${displayTitle(job)} ${job.location || ""}`.toLowerCase();
                if (query && !haystack.includes(query)) return false;
                if (locationFilter === "remote" && !(job.location || "").toLowerCase().includes("remote")) return false;
                if (locationFilter === "onsite" && (job.location || "").toLowerCase().includes("remote")) return false;
                if (statusFilter !== "all" && normalizeStatus(job.status) !== statusFilter) return false;
                return true;
            })
            .sort((a, b) => {
                const aDate = new Date(sortMode === "updated" ? a.updatedAt || a.addedAt || "" : a.addedAt || a.first_seen || "").getTime();
                const bDate = new Date(sortMode === "updated" ? b.updatedAt || b.addedAt || "" : b.addedAt || b.first_seen || "").getTime();
                return (Number.isNaN(bDate) ? 0 : bDate) - (Number.isNaN(aDate) ? 0 : aDate);
            });
    }, [jobs, locationFilter, search, sortMode, statusFilter]);

    const getColumnJobs = (columnId: string) => filteredJobs.filter((job) => normalizeStatus(job.status) === columnId);
    const moveJob = (hash: string, status: string) => persist(jobs.map((job) => (job.internal_hash === hash ? { ...job, status, updatedAt: new Date().toISOString() } : job)));
    const removeJob = (hash: string) => persist(jobs.filter((job) => job.internal_hash !== hash));

    const handleDragStart = (hash: string) => setDraggedJob(hash);
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
            keywords_matched: JSON.stringify(form.tags.split(",").map((tag) => tag.trim()).filter(Boolean)),
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
                <header className="flex min-h-[170px] flex-col gap-5 rounded-[28px] bg-[#3E1705] px-6 py-7 text-white sm:px-[34px] lg:flex-row lg:items-center lg:justify-between">
                    <div>
                        <p className="mb-3 text-sm font-bold uppercase tracking-[0.12em] text-white/70">Tracker</p>
                        <h1 className="font-serif text-[44px] font-bold leading-[0.98] tracking-[-0.055em] sm:text-[60px]">Application tracker</h1>
                        <p className="mt-4 max-w-[760px] text-[17px] leading-7 text-white/75 sm:text-lg">
                            Move roles from saved to applied, interviews, and offers - all in one calm workflow.
                        </p>
                    </div>
                    <div className="flex flex-wrap gap-3">
                        <button type="button" onClick={() => setShowForm(true)} className="inline-flex h-12 items-center gap-2 rounded-2xl bg-white px-[22px] text-base font-bold text-[#1F281B] transition hover:bg-[#FBF7EE]">
                            <Plus className="h-4 w-4" />
                            Add role
                        </button>
                        <Link href="/saved-roles" className="inline-flex h-12 items-center gap-2 rounded-2xl border border-white/20 bg-white/15 px-[22px] text-base font-semibold text-white transition hover:bg-white/20">
                            View saved roles
                            <ArrowRight className="h-4 w-4" />
                        </Link>
                    </div>
                </header>

                <section className="mt-[22px] grid gap-[18px] md:grid-cols-2 xl:grid-cols-5">
                    <StatCard title="Total tracked" value={jobs.length} helper="roles in your pipeline" />
                    <StatCard title="Applied" value={appliedCount} helper="sent applications" />
                    <StatCard title="Interviews" value={counts.interview} helper="active conversations" />
                    <StatCard title="Offers" value={counts.offer} helper="wins in progress" />
                    <StatCard title="Response rate" value={`${responseRate}%`} helper="OA, interview, or offer" />
                </section>

                <section className="mt-5 mb-[22px] flex flex-wrap items-center gap-3.5">
                    <label className="relative block w-full sm:w-[340px]">
                        <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#7B7B72]" />
                        <input
                            value={search}
                            onChange={(event) => setSearch(event.target.value)}
                            placeholder="Search company or role"
                            className="h-[46px] w-full rounded-[14px] border border-[#DDD1B8] bg-[#FBF7EE] pl-11 pr-4 text-sm text-[#1F281B] placeholder:text-[#7B7B72] focus:outline-none focus:ring-2 focus:ring-[#5D7440]"
                        />
                    </label>
                    <select value={locationFilter} onChange={(event) => setLocationFilter(event.target.value)} className="h-[46px] min-w-[150px] rounded-[14px] border border-[#DDD1B8] bg-[#FBF7EE] px-3.5 text-sm text-[#1F281B]">
                        <option value="all">All locations</option>
                        <option value="remote">Remote</option>
                        <option value="onsite">On-site / hybrid</option>
                    </select>
                    <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} className="h-[46px] min-w-[150px] rounded-[14px] border border-[#DDD1B8] bg-[#FBF7EE] px-3.5 text-sm text-[#1F281B]">
                        <option value="all">All status</option>
                        {ALL_COLUMNS.map((column) => (
                            <option key={column.id} value={column.id}>
                                {column.label}
                            </option>
                        ))}
                    </select>
                    <select value={sortMode} onChange={(event) => setSortMode(event.target.value)} className="h-[46px] min-w-[150px] rounded-[14px] border border-[#DDD1B8] bg-[#FBF7EE] px-3.5 text-sm text-[#1F281B]">
                        <option value="recent">Sort by recent</option>
                        <option value="updated">Sort by updated</option>
                    </select>
                    <button type="button" onClick={() => setCompact((value) => !value)} className={`h-[46px] rounded-[14px] border border-[#DDD1B8] px-4 text-sm font-bold ${compact ? "bg-[#DCE3C8] text-[#5D7440]" : "bg-[#FBF7EE] text-[#1F281B]"}`}>
                        Compact view
                    </button>
                    <button type="button" onClick={() => setShowForm(true)} className="inline-flex h-[46px] items-center gap-2 rounded-[14px] bg-[#5D7440] px-5 text-sm font-bold text-white transition hover:bg-[#47602F]">
                        <Plus className="h-4 w-4" />
                        New application
                    </button>
                </section>

                {showForm && (
                    <form onSubmit={addRole} className="mb-6 rounded-[20px] border border-[#DDD1B8] bg-[#FBF7EE] p-5 shadow-[0_8px_18px_rgba(44,30,12,0.05)]">
                        <div className="mb-4 flex items-center justify-between gap-3">
                            <h2 className="font-serif text-2xl font-bold tracking-[-0.035em]">New application</h2>
                            <button type="button" onClick={() => setShowForm(false)} className="grid h-9 w-9 place-items-center rounded-xl border border-[#DDD1B8]" aria-label="Close new application form">
                                <X className="h-4 w-4" />
                            </button>
                        </div>
                        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                            <input value={form.company} onChange={(event) => setForm({ ...form, company: event.target.value })} placeholder="Company" className="h-11 rounded-xl border border-[#DDD1B8] bg-white px-3 text-sm" />
                            <input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder="Role title" className="h-11 rounded-xl border border-[#DDD1B8] bg-white px-3 text-sm" />
                            <input value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} placeholder="Location" className="h-11 rounded-xl border border-[#DDD1B8] bg-white px-3 text-sm" />
                            <input value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} placeholder="Job link" className="h-11 rounded-xl border border-[#DDD1B8] bg-white px-3 text-sm" />
                            <select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })} className="h-11 rounded-xl border border-[#DDD1B8] bg-white px-3 text-sm">
                                {MAIN_COLUMNS.map((column) => (
                                    <option key={column.id} value={column.id}>
                                        {column.label}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div className="mt-3 flex flex-col gap-3 sm:flex-row">
                            <input value={form.tags} onChange={(event) => setForm({ ...form, tags: event.target.value })} placeholder="Tags, comma separated" className="h-11 flex-1 rounded-xl border border-[#DDD1B8] bg-white px-3 text-sm" />
                            <button type="submit" className="h-11 rounded-xl bg-[#5D7440] px-5 text-sm font-bold text-white">Add to tracker</button>
                        </div>
                    </form>
                )}

                {jobs.length === 0 ? (
                    <section className="rounded-[24px] border border-[#DDD1B8] bg-[#FBF7EE] py-20 text-center shadow-[0_8px_18px_rgba(44,30,12,0.05)]">
                        <CheckCircle2 className="mx-auto mb-5 h-12 w-12 text-[#5D7440]" />
                        <h2 className="font-serif text-3xl font-bold tracking-[-0.04em]">No tracked roles yet</h2>
                        <p className="mx-auto mt-2 max-w-md text-sm font-medium text-[#5E6258]">Save from the live feed or add a role manually to start your calm application pipeline.</p>
                        <div className="mt-6 flex justify-center gap-3">
                            <button type="button" onClick={() => setShowForm(true)} className="btn-primary">Add role</button>
                            <Link href="/jobs" className="btn-outline">Browse jobs</Link>
                        </div>
                    </section>
                ) : (
                    <>
                        <div className="overflow-x-auto pb-2">
                            <section className="grid min-w-[1400px] grid-cols-5 gap-[18px]">
                                {MAIN_COLUMNS.map((column) => (
                                    <TrackerColumn
                                        key={column.id}
                                        column={column}
                                        jobs={getColumnJobs(column.id)}
                                        compact={compact}
                                        dragOverColumn={dragOverColumn}
                                        onDragOver={handleDragOver}
                                        onDragLeave={() => setDragOverColumn(null)}
                                        onDrop={handleDrop}
                                        onCardDragStart={handleDragStart}
                                        onMove={moveJob}
                                        onRemove={removeJob}
                                    />
                                ))}
                            </section>
                        </div>
                        <section className="mt-5 grid gap-[18px] xl:grid-cols-2">
                            {CLOSED_COLUMNS.map((column) => (
                                <TrackerColumn
                                    key={column.id}
                                    column={column}
                                    jobs={getColumnJobs(column.id)}
                                    compact={compact}
                                    dragOverColumn={dragOverColumn}
                                    onDragOver={handleDragOver}
                                    onDragLeave={() => setDragOverColumn(null)}
                                    onDrop={handleDrop}
                                    onCardDragStart={handleDragStart}
                                    onMove={moveJob}
                                    onRemove={removeJob}
                                />
                            ))}
                        </section>
                    </>
                )}
            </main>
        </div>
    );
}
