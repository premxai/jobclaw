"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, BookmarkCheck, BookmarkPlus, BriefcaseBusiness, CalendarDays, ExternalLink, Link2, MapPin } from "lucide-react";
import TopNav from "@/components/TopNav";
import CompanyLogo from "@/components/CompanyLogo";
import JobCard, { Job, sourceLabel } from "@/components/JobCard";
import { fetchJobById, fetchJobs } from "@/lib/api";
import { displayCompany, displayTitle } from "@/lib/job-display";

export default function JobDetailPage() {
    const params = useParams();
    const router = useRouter();
    const [job, setJob] = useState<Job | null>(null);
    const [companyJobs, setCompanyJobs] = useState<Job[]>([]);
    const [saved, setSaved] = useState(false);

    useEffect(() => {
        const id = params.id as string;
        fetchJobById(id).then((j) => {
            setJob(j);
            const savedList = JSON.parse(localStorage.getItem("jobclaw_saved") || "[]") as Array<{ internal_hash: string }>;
            setSaved(savedList.some((s) => s.internal_hash === j?.internal_hash));
            if (j) {
                const company = displayCompany(j);
                fetchJobs({ company: j.company || company, limit: 6 }).then((data) => {
                    const sameCompany = data.jobs
                        .filter((candidate) => candidate.internal_hash !== j.internal_hash)
                        .filter((candidate) => displayCompany(candidate).toLowerCase() === company.toLowerCase())
                        .slice(0, 3);
                    setCompanyJobs(sameCompany);
                });
            }
        });
    }, [params.id]);

    const toggleSave = () => {
        if (!job) return;
        const savedList: Job[] = JSON.parse(localStorage.getItem("jobclaw_saved") || "[]");
        if (saved) {
            localStorage.setItem("jobclaw_saved", JSON.stringify(savedList.filter((j) => j.internal_hash !== job.internal_hash)));
        } else {
            localStorage.setItem("jobclaw_saved", JSON.stringify([...savedList, { ...job, status: "saved" }]));
        }
        setSaved(!saved);
    };

    if (!job) {
        return (
            <div className="page-shell">
                <TopNav />
                <div className="mx-auto max-w-4xl px-6 py-16">
                    <div className="nori-panel p-8">
                        <div className="mb-6 h-16 w-16 animate-pulse rounded-full bg-surface-2" />
                        <div className="mb-3 h-9 w-2/3 animate-pulse rounded-xl bg-surface-2" />
                        <div className="h-5 w-1/2 animate-pulse rounded-xl bg-surface-2" />
                    </div>
                </div>
            </div>
        );
    }

    const company = displayCompany(job);
    const title = displayTitle(job);
    let category = "";
    try {
        const kw = JSON.parse(job.keywords_matched || "[]");
        category = kw[0] || "";
    } catch {
        category = "";
    }

    return (
        <div className="page-shell">
            <TopNav />

            <main className="mx-auto max-w-5xl px-5 py-8 sm:px-6">
                <button
                    onClick={() => router.back()}
                    className="mb-6 inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-bold text-text-secondary shadow-card transition hover:text-ink"
                >
                    <ArrowLeft className="h-4 w-4" />
                    Back to jobs
                </button>

                <section className="nori-panel p-6 sm:p-8">
                    <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
                        <div className="flex gap-5">
                            <CompanyLogo company={company} size="lg" />
                            <div>
                                <p className="mb-2 text-sm font-black text-text-secondary">{company}</p>
                                <h1 className="max-w-3xl text-4xl font-black leading-[1.03] tracking-[-0.06em] text-ink sm:text-5xl">
                                    {title}
                                </h1>
                            </div>
                        </div>
                        <div className="flex shrink-0 flex-col gap-2 sm:flex-row lg:flex-col">
                            <a href={job.url} target="_blank" rel="noopener noreferrer" className="btn-primary gap-2 px-6">
                                Apply now
                                <ExternalLink className="h-4 w-4" />
                            </a>
                            <button onClick={toggleSave} className="btn-outline gap-2">
                                {saved ? <BookmarkCheck className="h-4 w-4" /> : <BookmarkPlus className="h-4 w-4" />}
                                {saved ? "Saved" : "Save job"}
                            </button>
                        </div>
                    </div>

                    <div className="mt-8 flex flex-wrap gap-2">
                        {job.location && (
                            <span className="pill pill-white gap-2">
                                <MapPin className="h-4 w-4" />
                                {job.location}
                            </span>
                        )}
                        {job.date_posted && (
                            <span className="pill pill-white gap-2">
                                <CalendarDays className="h-4 w-4" />
                                {job.date_posted}
                            </span>
                        )}
                        {job.source_ats && (
                            <span className="pill pill-white gap-2">
                                <Link2 className="h-4 w-4" />
                                {sourceLabel(job.source_ats)}
                            </span>
                        )}
                        {category && (
                            <span className="pill pill-accent gap-2">
                                <BriefcaseBusiness className="h-4 w-4" />
                                {category}
                            </span>
                        )}
                    </div>
                </section>

                {job.description && (
                    <section className="mt-6 nori-panel p-6 sm:p-8">
                        <h2 className="mb-4 text-xl font-black tracking-[-0.04em] text-ink">About this role</h2>
                        <div className="whitespace-pre-line text-sm font-medium leading-7 text-text-secondary sm:text-base">
                            {job.description}
                        </div>
                    </section>
                )}

                {companyJobs.length > 0 && (
                    <section className="mt-10">
                        <div className="mb-4 flex items-end justify-between gap-4">
                            <div>
                                <p className="text-xs font-black uppercase tracking-[0.18em] text-text-secondary">same company</p>
                                <h2 className="text-2xl font-black tracking-[-0.05em] text-ink">More jobs at {company}</h2>
                            </div>
                        </div>
                        <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
                            {companyJobs.map((candidate) => (
                                <JobCard key={candidate.internal_hash} job={candidate} />
                            ))}
                        </div>
                    </section>
                )}
            </main>
        </div>
    );
}
