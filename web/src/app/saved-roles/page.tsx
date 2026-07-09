"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import NoriAppSidebar from "@/components/NoriAppSidebar";
import JobCard, { Job } from "@/components/JobCard";
import { ArrowRight, Bookmark, ExternalLink } from "lucide-react";
import { useSavedJobsStorageKey } from "@/lib/use-saved-jobs-storage-key";

interface SavedRole extends Job {
    status?: string | null;
    addedAt?: string;
}

export default function SavedRolesPage() {
    const [roles, setRoles] = useState<SavedRole[]>([]);
    const savedJobsStorageKey = useSavedJobsStorageKey();

    useEffect(() => {
        try {
            const parsed = JSON.parse(localStorage.getItem(savedJobsStorageKey) || "[]") as SavedRole[];
            setRoles(Array.isArray(parsed) ? parsed : []);
        } catch {
            setRoles([]);
        }
    }, [savedJobsStorageKey]);

    const removeRole = (hash: string) => {
        const updated = roles.filter((role) => role.internal_hash !== hash);
        setRoles(updated);
        localStorage.setItem(savedJobsStorageKey, JSON.stringify(updated));
    };

    return (
        <div className="min-h-screen bg-[#FBF4E7] text-[#1F281B]">
            <NoriAppSidebar />

            <main className="px-5 py-8 sm:px-6 lg:ml-[280px]">
                <header className="mb-8 flex flex-col gap-4 rounded-[30px] bg-[#526736] p-6 text-white shadow-[0_18px_42px_rgba(38,58,34,0.18)] sm:p-8 lg:flex-row lg:items-end lg:justify-between">
                    <div>
                        <p className="mb-3 text-xs font-black uppercase tracking-[0.18em] text-white/55">saved roles</p>
                        <h1 className="text-4xl font-black tracking-[-0.06em] sm:text-5xl">Saved roles</h1>
                        <p className="mt-3 max-w-2xl text-sm font-medium text-white/65">
                            A clean list of roles you saved or applied to. Move them through the pipeline from Tracker.
                        </p>
                    </div>
                    <div className="flex flex-wrap gap-3">
                        <Link href="/tracker" className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-black text-[#1F281B] transition hover:bg-[#F7EED7]">
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
                    <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 xl:gap-5 2xl:grid-cols-4">
                        {roles.map((role) => (
                            <JobCard
                                key={role.internal_hash}
                                job={role}
                                saved
                                applied={role.status === "applied"}
                                onSave={() => removeRole(role.internal_hash)}
                                onApply={() => window.open(role.url, "_blank", "noopener,noreferrer")}
                            />
                        ))}
                    </section>
                )}
            </main>
        </div>
    );
}
