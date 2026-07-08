"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import TopNav from "@/components/TopNav";
import BrandMark from "@/components/BrandMark";
import { ArrowRight, Bell, Github, LockKeyhole, Mail, ShieldCheck, UserRound } from "lucide-react";

interface SavedJobRef {
    internal_hash: string;
    status?: string;
}

const authEnabled = process.env.NEXT_PUBLIC_AUTH_ENABLED === "1";

export default function ProfilePage() {
    const [savedCount, setSavedCount] = useState(0);
    const [appliedCount, setAppliedCount] = useState(0);

    useEffect(() => {
        const saved = localStorage.getItem("jobclaw_saved");
        if (!saved) return;
        try {
            const jobs: SavedJobRef[] = JSON.parse(saved);
            setSavedCount(jobs.length);
            setAppliedCount(jobs.filter((job) => ["applied", "interview", "offer"].includes(job.status || "")).length);
        } catch { }
    }, []);

    return (
        <div className="page-shell">
            <TopNav />

            <main className="mx-auto max-w-6xl px-5 py-8 sm:px-6">
                <header className="mb-8 rounded-[30px] bg-ink p-6 text-white sm:p-8">
                    <div className="mb-6 flex items-center justify-between gap-4">
                        <BrandMark href="" inverse />
                        <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-xs font-black uppercase tracking-[0.18em] text-white/60">
                            <LockKeyhole className="h-3.5 w-3.5" />
                            Auth locked
                        </span>
                    </div>
                    <h1 className="max-w-3xl text-4xl font-black leading-tight tracking-[-0.06em] sm:text-5xl">
                        Your Nori Note profile is designed and waiting for launch.
                    </h1>
                    <p className="mt-3 max-w-2xl text-sm font-medium text-white/65">
                        Accounts are intentionally disabled for this version. Saved jobs and tracker data stay on this device until auth is enabled.
                    </p>
                </header>

                <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
                    <section className="nori-panel p-6">
                        <div className="mb-6 grid h-16 w-16 place-items-center rounded-full bg-surface-2">
                            <UserRound className="h-7 w-7 text-ink" />
                        </div>
                        <h2 className="text-2xl font-black tracking-[-0.04em] text-ink">Local search profile</h2>
                        <p className="mt-2 text-sm font-medium leading-6 text-text-secondary">
                            Today, Nori keeps your saved roles in your browser. When accounts unlock, this page will sync your saved jobs, tracker stages, notes, and preferences.
                        </p>

                        <div className="mt-6 grid grid-cols-2 gap-3">
                            <div className="rounded-2xl bg-surface-2 p-4">
                                <p className="text-3xl font-black text-ink">{savedCount}</p>
                                <p className="text-xs font-black uppercase tracking-[0.14em] text-text-secondary">saved jobs</p>
                            </div>
                            <div className="rounded-2xl bg-surface-2 p-4">
                                <p className="text-3xl font-black text-ink">{appliedCount}</p>
                                <p className="text-xs font-black uppercase tracking-[0.14em] text-text-secondary">active apps</p>
                            </div>
                        </div>

                        <Link href="/tracker" className="btn-primary mt-6 w-full gap-2">
                            Open tracker
                            <ArrowRight className="h-4 w-4" />
                        </Link>
                    </section>

                    <section className="nori-panel p-6">
                        <div className="mb-6 flex items-center gap-3">
                            <ShieldCheck className="h-6 w-6 text-ink" />
                            <div>
                                <h2 className="text-2xl font-black tracking-[-0.04em] text-ink">Sign in options</h2>
                                <p className="text-sm font-medium text-text-secondary">Designed now, disabled until publishing.</p>
                            </div>
                        </div>

                        <div className="space-y-3">
                            <button disabled={!authEnabled} className="flex w-full items-center justify-between rounded-2xl border border-border bg-surface-2 px-4 py-4 text-left opacity-70">
                                <span className="flex items-center gap-3">
                                    <Mail className="h-5 w-5 text-ink" />
                                    <span>
                                        <span className="block font-black text-ink">Email and password</span>
                                        <span className="text-sm font-medium text-text-secondary">Create an account with secure credentials.</span>
                                    </span>
                                </span>
                                <LockKeyhole className="h-4 w-4 text-text-secondary" />
                            </button>
                            <button disabled={!authEnabled} className="flex w-full items-center justify-between rounded-2xl border border-border bg-surface-2 px-4 py-4 text-left opacity-70">
                                <span className="flex items-center gap-3">
                                    <Github className="h-5 w-5 text-ink" />
                                    <span>
                                        <span className="block font-black text-ink">OAuth sign in</span>
                                        <span className="text-sm font-medium text-text-secondary">Google and GitHub providers are planned.</span>
                                    </span>
                                </span>
                                <LockKeyhole className="h-4 w-4 text-text-secondary" />
                            </button>
                        </div>

                        <div className="mt-6 rounded-2xl bg-ink p-5 text-white">
                            <div className="mb-3 flex items-center gap-2">
                                <Bell className="h-5 w-5" />
                                <h3 className="font-black">Future preferences</h3>
                            </div>
                            <p className="text-sm font-medium text-white/65">
                                Job alerts, preferred categories, remote/location preferences, and dashboard goals will live here once account sync is enabled.
                            </p>
                        </div>
                    </section>
                </div>
            </main>
        </div>
    );
}
