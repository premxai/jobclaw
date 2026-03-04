"use client";
import { useState, useEffect, useCallback } from "react";
import TopNav from "@/components/TopNav";
import CompanyLogo from "@/components/CompanyLogo";
import { Job } from "@/components/JobCard";
import { GripVertical, Plus, Trash2, ExternalLink } from "lucide-react";

// Kanban columns
const COLUMNS = [
    { id: "saved", label: "Saved", icon: "📌", color: "#8B949E" },
    { id: "applied", label: "Applied", icon: "📤", color: "#58A6FF" },
    { id: "interview", label: "Interview", icon: "🎯", color: "#D29922" },
    { id: "offer", label: "Offer", icon: "🎉", color: "#3FB950" },
];

interface TrackedJob extends Job {
    status: string;
    addedAt?: string;
    notes?: string;
}

export default function TrackerPage() {
    const [jobs, setJobs] = useState<TrackedJob[]>([]);
    const [draggedJob, setDraggedJob] = useState<string | null>(null);
    const [dragOverColumn, setDragOverColumn] = useState<string | null>(null);

    // Load from localStorage
    useEffect(() => {
        const saved = localStorage.getItem("jobclaw_saved");
        if (saved) {
            try {
                const parsed: TrackedJob[] = JSON.parse(saved);
                // Ensure all have a status
                const withStatus = parsed.map((j) => ({
                    ...j,
                    status: j.status || "saved",
                    addedAt: j.addedAt || new Date().toISOString(),
                }));
                setJobs(withStatus);
            } catch { }
        }
    }, []);

    // Persist to localStorage
    const persist = useCallback((updatedJobs: TrackedJob[]) => {
        setJobs(updatedJobs);
        localStorage.setItem("jobclaw_saved", JSON.stringify(updatedJobs));
    }, []);

    // Drag handlers
    const handleDragStart = (hash: string) => {
        setDraggedJob(hash);
    };

    const handleDragOver = (e: React.DragEvent, columnId: string) => {
        e.preventDefault();
        setDragOverColumn(columnId);
    };

    const handleDragLeave = () => {
        setDragOverColumn(null);
    };

    const handleDrop = (columnId: string) => {
        if (!draggedJob) return;
        const updated = jobs.map((j) =>
            j.internal_hash === draggedJob ? { ...j, status: columnId } : j
        );
        persist(updated);
        setDraggedJob(null);
        setDragOverColumn(null);
    };

    const removeJob = (hash: string) => {
        persist(jobs.filter((j) => j.internal_hash !== hash));
    };

    const getColumnJobs = (columnId: string) =>
        jobs.filter((j) => j.status === columnId);

    return (
        <div className="min-h-screen">
            <TopNav />

            <div className="max-w-7xl mx-auto px-6 py-8">
                <div className="mb-8">
                    <h1 className="text-3xl font-bold tracking-tight mb-2">Job Tracker</h1>
                    <p className="text-text-secondary text-sm">
                        Drag jobs between columns to track your application progress. Save jobs from the{" "}
                        <a href="/jobs" className="text-accent hover:underline">Job Feed</a> to get started.
                    </p>
                </div>

                {/* Kanban board */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
                    {COLUMNS.map((column) => {
                        const columnJobs = getColumnJobs(column.id);
                        const isOver = dragOverColumn === column.id;

                        return (
                            <div
                                key={column.id}
                                className={`kanban-column transition-colors ${isOver ? "border-accent/50 bg-accent/5" : ""
                                    }`}
                                onDragOver={(e) => handleDragOver(e, column.id)}
                                onDragLeave={handleDragLeave}
                                onDrop={() => handleDrop(column.id)}
                            >
                                {/* Column header */}
                                <div className="flex items-center justify-between mb-4">
                                    <div className="flex items-center gap-2">
                                        <span className="text-lg">{column.icon}</span>
                                        <h2 className="font-semibold text-sm">{column.label}</h2>
                                        <span
                                            className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
                                            style={{ backgroundColor: column.color + "20", color: column.color }}
                                        >
                                            {columnJobs.length}
                                        </span>
                                    </div>
                                </div>

                                {/* Cards */}
                                <div className="space-y-3">
                                    {columnJobs.map((job) => (
                                        <div
                                            key={job.internal_hash}
                                            draggable
                                            onDragStart={() => handleDragStart(job.internal_hash)}
                                            className={`kanban-card ${draggedJob === job.internal_hash ? "opacity-50 scale-95" : ""
                                                }`}
                                        >
                                            <div className="flex items-start gap-3">
                                                <GripVertical className="w-4 h-4 text-text-secondary mt-0.5 shrink-0 opacity-50" />
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <CompanyLogo company={job.company} size="sm" />
                                                        <span className="text-xs text-text-secondary truncate">{job.company}</span>
                                                    </div>
                                                    <p className="font-semibold text-sm text-text-primary leading-tight mb-2 line-clamp-2">
                                                        {job.title}
                                                    </p>
                                                    <p className="text-xs text-text-secondary">
                                                        {job.date_posted || "No date"}
                                                    </p>
                                                </div>
                                            </div>
                                            {/* Actions */}
                                            <div className="flex items-center gap-1 mt-3 pt-2 border-t border-border">
                                                <a
                                                    href={job.url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="p-1.5 rounded hover:bg-surface-3 text-text-secondary hover:text-info transition-colors"
                                                    title="Open listing"
                                                >
                                                    <ExternalLink className="w-3.5 h-3.5" />
                                                </a>
                                                <button
                                                    onClick={() => removeJob(job.internal_hash)}
                                                    className="p-1.5 rounded hover:bg-surface-3 text-text-secondary hover:text-red-400 transition-colors ml-auto"
                                                    title="Remove"
                                                >
                                                    <Trash2 className="w-3.5 h-3.5" />
                                                </button>
                                            </div>
                                        </div>
                                    ))}

                                    {columnJobs.length === 0 && (
                                        <div className="text-center py-8 text-text-secondary text-xs border border-dashed border-border rounded-lg">
                                            {column.id === "saved"
                                                ? "Save jobs from the feed"
                                                : "Drag jobs here"}
                                        </div>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>

                {jobs.length === 0 && (
                    <div className="text-center py-20 animate-fade-in">
                        <p className="text-6xl mb-4">📋</p>
                        <h2 className="text-xl font-bold text-text-primary mb-2">No tracked jobs yet</h2>
                        <p className="text-text-secondary mb-6">
                            Browse the job feed and click "Save" to start tracking your applications.
                        </p>
                        <a href="/jobs" className="btn-primary">
                            Browse Jobs
                        </a>
                    </div>
                )}
            </div>
        </div>
    );
}
