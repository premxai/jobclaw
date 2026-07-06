"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import TopNav from "@/components/TopNav";
import CompanyLogo from "@/components/CompanyLogo";
import { sourceLabel } from "@/components/JobCard";
import { fetchCompanies, Company } from "@/lib/api";

export default function CompaniesPage() {
    const [companies, setCompanies] = useState<Company[]>([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");

    useEffect(() => {
        fetchCompanies().then((data) => {
            setCompanies(data);
            setLoading(false);
        });
    }, []);

    const filtered = search.trim()
        ? companies.filter((c) => c.company.toLowerCase().includes(search.trim().toLowerCase()))
        : companies;

    return (
        <div className="min-h-screen">
            <TopNav />

            <div className="max-w-7xl mx-auto px-6 py-8">
                <div className="mb-6 flex items-center justify-between">
                    <div>
                        <h1 className="text-xl font-bold text-text-primary">Companies</h1>
                        <p className="text-sm text-text-secondary">
                            {loading ? "Loading…" : `${companies.length} companies actively monitored`}
                        </p>
                    </div>
                    {/* Client-side filter — fine at current scale; revisit with
                        server-side search/virtualization if the list grows large. */}
                    {companies.length > 20 && (
                        <input
                            type="text"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder="Filter companies…"
                            className="input-field max-w-xs"
                        />
                    )}
                </div>

                {loading ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                        {Array.from({ length: 9 }).map((_, i) => (
                            <div key={i} className="bg-white rounded-xl border border-border h-20 animate-pulse" />
                        ))}
                    </div>
                ) : filtered.length === 0 ? (
                    <div className="text-center py-20">
                        <p className="text-xl font-bold text-text-primary mb-2">No companies found</p>
                        <p className="text-text-secondary">Try a different search.</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                        {filtered.map((c) => (
                            <Link
                                key={`${c.company}-${c.source_ats}`}
                                href={`/jobs?search=${encodeURIComponent(c.company)}`}
                                className="card-hover-lift flex items-center gap-3 rounded-xl border border-border bg-white p-4"
                            >
                                <CompanyLogo company={c.company} size="md" />
                                <div className="min-w-0 flex-1">
                                    <p className="truncate text-sm font-semibold text-text-primary">{c.company}</p>
                                    <div className="mt-1 flex items-center gap-1.5">
                                        <span className="pill pill-accent text-xs">{c.job_count} open</span>
                                        <span className="pill pill-white text-xs">{sourceLabel(c.source_ats)}</span>
                                    </div>
                                </div>
                            </Link>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
