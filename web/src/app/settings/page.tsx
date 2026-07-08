"use client";

import Link from "next/link";
import TopNav from "@/components/TopNav";
import { Bell, LockKeyhole, MapPin, Moon, ShieldCheck, SlidersHorizontal } from "lucide-react";

const settings = [
    {
        icon: Bell,
        title: "Job alerts",
        description: "Daily and instant alerts will be available once accounts are enabled.",
    },
    {
        icon: SlidersHorizontal,
        title: "Role preferences",
        description: "Choose preferred categories, seniority, and source types for Nori to prioritize.",
    },
    {
        icon: MapPin,
        title: "Location defaults",
        description: "Set remote, hybrid, or city preferences for future personalized feeds.",
    },
    {
        icon: Moon,
        title: "Display",
        description: "Theme and density controls will live here after the first account release.",
    },
];

export default function SettingsPage() {
    return (
        <div className="page-shell">
            <TopNav />

            <main className="mx-auto max-w-6xl px-5 py-8 sm:px-6">
                <header className="mb-8 rounded-[30px] bg-ink p-6 text-white sm:p-8">
                    <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-xs font-black uppercase tracking-[0.18em] text-white/60">
                        <LockKeyhole className="h-3.5 w-3.5" />
                        Settings preview
                    </div>
                    <h1 className="max-w-3xl text-4xl font-black leading-tight tracking-[-0.06em] sm:text-5xl">Nori settings are ready for accounts.</h1>
                    <p className="mt-3 max-w-2xl text-sm font-medium text-white/65">
                        These preferences are designed now, but syncing them will wait until authentication is connected.
                    </p>
                </header>

                <section className="grid gap-4 md:grid-cols-2">
                    {settings.map(({ icon: Icon, title, description }) => (
                        <article key={title} className="nori-panel p-6">
                            <div className="mb-5 grid h-12 w-12 place-items-center rounded-2xl bg-surface-2 text-ink">
                                <Icon className="h-5 w-5" />
                            </div>
                            <h2 className="text-xl font-black tracking-[-0.04em] text-ink">{title}</h2>
                            <p className="mt-2 text-sm font-medium leading-6 text-text-secondary">{description}</p>
                            <div className="mt-5 inline-flex items-center gap-2 rounded-full bg-surface-2 px-3 py-1.5 text-xs font-black uppercase tracking-[0.14em] text-text-secondary">
                                <ShieldCheck className="h-3.5 w-3.5" />
                                Coming with auth
                            </div>
                        </article>
                    ))}
                </section>

                <Link href="/jobs" className="btn-primary mt-8">
                    Back to jobs
                </Link>
            </main>
        </div>
    );
}
