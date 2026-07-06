"use client";
import { useState } from "react";
import { X, Loader2 } from "lucide-react";
import JobCard, { Job } from "./JobCard";
import { matchResume } from "@/lib/api";

interface ResumeMatchModalProps {
    open: boolean;
    onClose: () => void;
    onSave?: (job: Job) => void;
    savedJobs?: Set<string>;
}

type Phase = "input" | "loading" | "disabled" | "error" | "results";

export default function ResumeMatchModal({ open, onClose, onSave, savedJobs }: ResumeMatchModalProps) {
    const [resumeText, setResumeText] = useState("");
    const [phase, setPhase] = useState<Phase>("input");
    const [results, setResults] = useState<Job[]>([]);
    const [error, setError] = useState("");

    if (!open) return null;

    const handleSubmit = async () => {
        if (!resumeText.trim()) return;
        setPhase("loading");
        const { enabled, jobs, error: err } = await matchResume(resumeText, 20);
        if (!enabled) {
            setPhase("disabled");
        } else if (err) {
            setError(err);
            setPhase("error");
        } else {
            setResults(jobs);
            setPhase("results");
        }
    };

    const reset = () => {
        setPhase("input");
        setResults([]);
        setError("");
    };

    return (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 pt-16 sm:pt-24" onClick={onClose}>
            <div
                className="w-full max-w-3xl rounded-2xl border border-border bg-white p-6 shadow-popover animate-slide-up"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="mb-4 flex items-center justify-between">
                    <h2 className="text-lg font-bold text-text-primary">Match my resume</h2>
                    <button onClick={onClose} aria-label="Close" className="text-text-secondary hover:text-text-primary">
                        <X className="h-5 w-5" />
                    </button>
                </div>

                {phase === "input" && (
                    <>
                        <p className="mb-3 text-sm text-text-secondary">
                            Paste your resume text and we&rsquo;ll rank every open role by how well it fits — nothing is stored.
                        </p>
                        <textarea
                            value={resumeText}
                            onChange={(e) => setResumeText(e.target.value)}
                            placeholder="Paste your resume text here…"
                            rows={10}
                            className="input-field resize-none"
                        />
                        <button onClick={handleSubmit} disabled={!resumeText.trim()} className="btn-primary mt-4 disabled:opacity-40">
                            Find my best matches
                        </button>
                    </>
                )}

                {phase === "loading" && (
                    <div className="flex flex-col items-center justify-center py-16 text-text-secondary">
                        <Loader2 className="mb-3 h-6 w-6 animate-spin" />
                        <p className="text-sm">Scoring jobs against your resume…</p>
                    </div>
                )}

                {phase === "disabled" && (
                    <div className="py-10 text-center">
                        <p className="text-base font-semibold text-text-primary mb-2">Resume matching isn&rsquo;t enabled on this deployment yet</p>
                        <p className="text-sm text-text-secondary">Try the &ldquo;Best match&rdquo; search on the jobs page instead — it works without any extra setup.</p>
                    </div>
                )}

                {phase === "error" && (
                    <div className="py-10 text-center">
                        <p className="text-base font-semibold text-text-primary mb-2">Couldn&rsquo;t score jobs right now</p>
                        <p className="text-sm text-text-secondary mb-4">{error}</p>
                        <button onClick={reset} className="btn-outline">Try again</button>
                    </div>
                )}

                {phase === "results" && (
                    <>
                        <div className="mb-4 flex items-center justify-between">
                            <p className="text-sm text-text-secondary">
                                <span className="font-medium text-text-primary">{results.length}</span> jobs ranked by fit
                            </p>
                            <button onClick={reset} className="text-sm font-medium text-accent hover:underline">Start over</button>
                        </div>
                        {results.length === 0 ? (
                            <p className="py-10 text-center text-text-secondary">No strong matches found — try a more detailed resume.</p>
                        ) : (
                            <div className="grid max-h-[60vh] grid-cols-1 gap-4 overflow-y-auto sm:grid-cols-2">
                                {results.map((job) => (
                                    <JobCard key={job.internal_hash} job={job} onSave={onSave} saved={savedJobs?.has(job.internal_hash)} />
                                ))}
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}
