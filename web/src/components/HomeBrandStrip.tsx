"use client";
import { useEffect, useState } from "react";
import { fetchStats } from "@/lib/api";

// Compact brand moment for the merged home/jobs landing page — replaces the
// old full-height "room scene" hero. Keeps some personality (mascot + tagline)
// and a trust signal (live counts) without a second, largely-duplicate page.
export default function HomeBrandStrip() {
    const [companies, setCompanies] = useState<number | null>(null);
    const [newToday, setNewToday] = useState<number | null>(null);

    useEffect(() => {
        fetchStats().then((s) => {
            setCompanies(s.total_companies || null);
            setNewToday(s.jobs_last_24h ?? null);
        });
    }, []);

    return (
        <div className="mb-6 flex flex-col items-center justify-between gap-4 rounded-2xl border border-border bg-white p-5 shadow-card sm:flex-row">
            <div className="text-center sm:text-left">
                <div className="flex items-center justify-center gap-2 sm:justify-start">
                    <span className="text-2xl">🦀</span>
                    <h1 className="text-lg font-bold text-text-primary">
                        Job<span className="text-accent">Claw</span>
                    </h1>
                </div>
                <p className="mt-1 text-sm text-text-secondary">Fresh tech jobs from the last 48 hours, less noise.</p>
            </div>
            <div className="flex items-center gap-6">
                <div className="text-center">
                    <p className="text-xl font-bold text-text-primary">{companies !== null ? companies.toLocaleString() : "—"}</p>
                    <p className="text-xs text-text-secondary">companies monitored</p>
                </div>
                <div className="text-center">
                    <p className="text-xl font-bold text-text-primary">{newToday !== null ? newToday.toLocaleString() : "—"}</p>
                    <p className="text-xs text-text-secondary">new in 24h</p>
                </div>
            </div>
        </div>
    );
}
