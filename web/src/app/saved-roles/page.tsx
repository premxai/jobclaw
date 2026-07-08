"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import NoriAppSidebar from "@/components/NoriAppSidebar";
import CompanyLogo from "@/components/CompanyLogo";
import { Job } from "@/components/JobCard";
import { displayCompany, displayTitle } from "@/lib/job-display";
import { ArrowRight, Bookmark, ExternalLink, Trash2 } from "lucide-react";

interface SavedRole extends Job {
    status?: string | null;
    addedAt?: string;
}

function statusLabel(status?: string | null) {
    if (!status || status === "saved") return "Saved";
    if (status === "oa") return "OA";
    return status.charAt(0).toUpperCase() + status.slice(1);
}

export default function SavedRolesPage() {
    const [roles, setRoles] = useState<SavedRole[]>([]);

    useEffect(() => {
        try {
            const parsed = JSON.parse(localStorage.getItem("jobclaw_saved") || "[]") as SavedRole[];
            setRoles(Array.isArray(parsed) ? parsed : []);
        } catch {
            setRoles([]);
        }
    }, []);

    const removeRole = (hash: string) => {
        const updated = roles.filter((role) => role.internal_hash !== hash);
        setRoles(updated);
        localStorage.setItem("jobclaw_saved", JSON.stringify(updated));
    };

    return (
        <div className="min-h-screen bg-[#FBF4E7] text-[#1F281B]">
            <NoriAppSidebar />

            <main className="px-5 py-8 sm:px-6 lg:ml-[280px]">
                <header className="mb-8 flex flex-col gap-4 rounded-[30px] bg-ink p-6 text-white sm:p-8 lg:flex-row lg:items-end lg:justify-between">
                    <div>
                        <p className="mb-3 text-xs font-black uppercase tracking-[0.18em] text-white/55">saved roles</p>
                        <h1 className="text-4xl font-black tracking-[-0.06em] sm:text-5xl">Saved roles</h1>
                        <p className="mt-3 max-w-2xl text-sm font-medium text-white/65">
                            A clean list of roles you saved or applied to. Move them through the pipeline from Tracker.
                        </p>
                    </div>
                    <div className="flex flex-wrap gap-3">
                        <Link href="/tracker" className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-black text-ink transition hover:bg-surface-2">
                            Open tracker
                            <ArrowRight className="h-4 w-4" />
                        </Link>
                        <Link href="/jobs" className="inline-flex items-center justify-center gap-2 rounded-xl bg-white/10 px-5 py-3 text-sm font-black text-white transition hover:bg-white/15">
                            Browse jobs
                            <ExternalLink className="h-4 w-4" />
                        </Link>
                    </div>
                </header>

                {roles.length === 0 ? (
                    <section className="rounded-[28px] border border-[#E7D7B7] bg-[#FFF9EC] py-20 text-center shadow-[0_10px_24px_rgba(70,45,16,0.08)]">
                        <div className="mx-auto mb-6 grid h-20 w-20 place-items-center rounded-full bg-[#EEF1DD] text-[#526736]">
                            <Bookmark className="h-9 w-9" />
                        </div>
                        <h2 className="font-serif text-3xl font-bold tracking-[-0.04em] text-[#1F281B]">No saved roles yet</h2>
                        <p className="mx-auto mt-2 max-w-md text-sm font-medium text-[#5F665C]">
                            Save a job from the live feed and it will appear here.
                        </p>
                        <Link href="/jobs" className="btn-primary mt-6">
                            Browse jobs
                        </Link>
                    </section>
                ) : (
                    <section className="grid gap-4 xl:grid-cols-2">
                        {roles.map((role) => {
                            const company = displayCompany(role);
                            return (
                                <article
                                    key={role.internal_hash}
                                    className="rounded-2xl border border-[#E7D7B7] bg-[#FFF9EC] p-5 shadow-[0_8px_18px_rgba(70,45,16,0.06)] [background-image:linear-gradient(rgba(255,249,236,0.84),rgba(255,249,236,0.84)),url('/nori-assets/paper-texture.png')] [background-size:cover]"
                                >
                                    <div className="flex items-start gap-4">
                                        <CompanyLogo company={company} size="md" shape="rounded" />
                                        <div className="min-w-0 flex-1">
                                            <div className="mb-1 flex flex-wrap items-center gap-2">
                                                <span className="text-sm font-black text-[#1F281B]">{company}</span>
                                                <span className="rounded-full border border-[#D8C9A7] bg-[#F7EED7] px-2.5 py-1 text-xs font-bold text-[#526736]">
                                                    {statusLabel(role.status)}
                                                </span>
                                            </div>
                                            <h2 className="line-clamp-2 font-serif text-2xl font-bold leading-tight tracking-[-0.04em] text-[#1F281B]">
                                                {displayTitle(role)}
                                            </h2>
                                            <p className="mt-2 text-sm font-medium text-[#5F665C]">{role.location || "Location not listed"}</p>
                                        </div>
                                    </div>
                                    <div className="mt-5 flex items-center gap-2 border-t border-[#E7D7B7] pt-4">
                                        <a href={role.url} target="_blank" rel="noopener noreferrer" className="inline-flex h-10 items-center gap-2 rounded-xl bg-[#526736] px-4 text-sm font-bold text-white">
                                            Open job
                                            <ExternalLink className="h-4 w-4" />
                                        </a>
                                        <Link href="/tracker" className="inline-flex h-10 items-center gap-2 rounded-xl border border-[#D8C9A7] bg-[#FFF9EC] px-4 text-sm font-bold text-[#1F281B]">
                                            Track
                                            <ArrowRight className="h-4 w-4" />
                                        </Link>
                                        <button
                                            type="button"
                                            onClick={() => removeRole(role.internal_hash)}
                                            className="ml-auto grid h-10 w-10 place-items-center rounded-xl border border-[#D8C9A7] bg-[#FFF9EC] text-[#5F665C] transition hover:text-red-600"
                                            aria-label="Remove saved role"
                                        >
                                            <Trash2 className="h-4 w-4" />
                                        </button>
                                    </div>
                                </article>
                            );
                        })}
                    </section>
                )}
            </main>
        </div>
    );
}
