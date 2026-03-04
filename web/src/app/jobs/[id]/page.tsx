"use client";
import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import TopNav from "@/components/TopNav";
import CompanyLogo from "@/components/CompanyLogo";
import JobCard, { Job } from "@/components/JobCard";
import { fetchJobById, fetchJobs } from "@/lib/api";
import { ArrowLeft, MapPin, DollarSign, Calendar, Link2, Briefcase, BookmarkPlus, BookmarkCheck } from "lucide-react";

function formatSalary(min?: number | null, max?: number | null): string | null {
    if (!min && !max) return null;
    const fmt = (n: number) => `$${Math.round(n / 1000)}k`;
    if (min && max) return `${fmt(min)} – ${fmt(max)}`;
    if (min) return `${fmt(min)}+`;
    return max ? `Up to ${fmt(max)}` : null;
}

export default function JobDetailPage() {
    const params = useParams();
    const router = useRouter();
    const [job, setJob] = useState<Job | null>(null);
    const [related, setRelated] = useState<Job[]>([]);
    const [saved, setSaved] = useState(false);

    useEffect(() => {
        const id = params.id as string;
        fetchJobById(id).then((j) => {
            setJob(j);
            // Check if saved
            const savedList = JSON.parse(localStorage.getItem("jobclaw_saved") || "[]");
            setSaved(savedList.some((s: any) => s.internal_hash === j?.internal_hash));
            // Load related jobs
            if (j) {
                fetchJobs({ limit: 6 }).then((data) => {
                    setRelated(data.jobs.filter((r) => r.internal_hash !== j.internal_hash).slice(0, 3));
                });
            }
        });
    }, [params.id]);

    const toggleSave = () => {
        if (!job) return;
        const savedList: Job[] = JSON.parse(localStorage.getItem("jobclaw_saved") || "[]");
        if (saved) {
            const filtered = savedList.filter((j) => j.internal_hash !== job.internal_hash);
            localStorage.setItem("jobclaw_saved", JSON.stringify(filtered));
        } else {
            savedList.push({ ...job, status: "saved" });
            localStorage.setItem("jobclaw_saved", JSON.stringify(savedList));
        }
        setSaved(!saved);
    };

    if (!job) {
        return (
            <div className="min-h-screen">
                <TopNav />
                <div className="max-w-3xl mx-auto px-6 py-20 text-center">
                    <div className="w-16 h-16 rounded-full bg-surface mx-auto mb-4 animate-pulse" />
                    <div className="h-8 bg-surface rounded-lg w-64 mx-auto mb-3 animate-pulse" />
                    <div className="h-5 bg-surface rounded w-48 mx-auto animate-pulse" />
                </div>
            </div>
        );
    }

    const salary = formatSalary(job.salary_min, job.salary_max);
    let category = null;
    try { const kw = JSON.parse(job.keywords_matched || "[]"); category = kw[0]; } catch { }

    return (
        <div className="min-h-screen">
            <TopNav />

            <div className="max-w-3xl mx-auto px-6 py-8">
                {/* Back */}
                <button
                    onClick={() => router.back()}
                    className="flex items-center gap-2 text-text-secondary hover:text-text-primary text-sm mb-8 transition-colors"
                >
                    <ArrowLeft className="w-4 h-4" />
                    Back to Jobs
                </button>

                {/* Header */}
                <div className="flex items-start gap-5 mb-8 animate-fade-in">
                    <CompanyLogo company={job.company} size="lg" />
                    <div className="flex-1">
                        <p className="text-sm text-text-secondary mb-1">{job.company}</p>
                        <h1 className="text-3xl font-bold text-text-primary tracking-tight mb-3">{job.title}</h1>

                        {/* Info pills */}
                        <div className="flex flex-wrap gap-3">
                            {job.location && (
                                <div className="flex items-center gap-1.5 pill-dark">
                                    <MapPin className="w-3.5 h-3.5" />
                                    {job.location}
                                </div>
                            )}
                            {salary && (
                                <div className="flex items-center gap-1.5 pill-dark">
                                    <DollarSign className="w-3.5 h-3.5" />
                                    {salary}
                                </div>
                            )}
                            {job.date_posted && (
                                <div className="flex items-center gap-1.5 pill-dark">
                                    <Calendar className="w-3.5 h-3.5" />
                                    {job.date_posted}
                                </div>
                            )}
                            {job.source_ats && (
                                <div className="flex items-center gap-1.5 pill-dark">
                                    <Link2 className="w-3.5 h-3.5" />
                                    {job.source_ats}
                                </div>
                            )}
                            {category && (
                                <div className="flex items-center gap-1.5 pill-accent">
                                    <Briefcase className="w-3.5 h-3.5" />
                                    {category}
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* CTA */}
                <div className="flex gap-3 mb-10 animate-slide-up">
                    <a
                        href={job.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn-primary text-base px-8 py-3"
                    >
                        Apply Now →
                    </a>
                    <button onClick={toggleSave} className="btn-outline flex items-center gap-2">
                        {saved ? <BookmarkCheck className="w-4 h-4" /> : <BookmarkPlus className="w-4 h-4" />}
                        {saved ? "Saved" : "Save Job"}
                    </button>
                </div>

                {/* Description */}
                {job.description && (
                    <div className="mb-12 animate-fade-in">
                        <h2 className="text-lg font-bold text-text-primary mb-4">About this Role</h2>
                        <div className="bg-surface border border-border rounded-xl p-6">
                            <p className="text-text-secondary leading-relaxed whitespace-pre-line">
                                {job.description}
                            </p>
                        </div>
                    </div>
                )}

                {/* Related jobs */}
                {related.length > 0 && (
                    <div className="animate-slide-up">
                        <h2 className="text-lg font-bold text-text-primary mb-4">Similar Jobs</h2>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            {related.map((r, i) => (
                                <a key={r.internal_hash || i} href={`/jobs/${r.id}`}>
                                    <JobCard job={r} />
                                </a>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
