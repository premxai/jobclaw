"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import TopNav from "@/components/TopNav";
import CompanyLogo from "@/components/CompanyLogo";
import { sourceLabel } from "@/components/JobCard";
import { fetchCompanies, Company } from "@/lib/api";
import { Building2, Search } from "lucide-react";

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
        <div className="page-shell">
            <TopNav />

            <main className="mx-auto max-w-7xl px-5 py-8 sm:px-6">
                <header className="mb-8 flex flex-col gap-4 rounded-[30px] bg-ink p-6 text-white sm:p-8 lg:flex-row lg:items-end lg:justify-between">
                    <div>
                        <p className="mb-3 text-xs font-black uppercase tracking-[0.18em] text-white/55">company index</p>
                        <h1 className="text-4xl font-black tracking-[-0.06em] sm:text-5xl">Companies Nori watches</h1>
                        <p className="mt-3 text-sm font-medium text-white/65">
                            {loading ? "Loading..." : `${companies.length} companies with active roles in the board`}
                        </p>
                    </div>
                    {companies.length > 20 && (
                        <div className="flex min-h-[3rem] items-center gap-3 rounded-2xl bg-white px-4 text-ink">
                            <Search className="h-4 w-4 text-text-secondary" />
                            <input
                                type="text"
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder="Filter companies"
                                className="w-full min-w-0 bg-transparent text-sm font-bold outline-none placeholder:text-text-secondary lg:w-72"
                            />
                        </div>
                    )}
                </header>

                {loading ? (
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                        {Array.from({ length: 9 }).map((_, i) => (
                            <div key={i} className="h-24 animate-pulse rounded-[22px] border border-border bg-white" />
                        ))}
                    </div>
                ) : filtered.length === 0 ? (
                    <div className="nori-panel py-20 text-center">
                        <Building2 className="mx-auto mb-4 h-10 w-10 text-text-secondary" />
                        <p className="mb-2 text-xl font-black text-text-primary">No companies found</p>
                        <p className="font-medium text-text-secondary">Try a different search.</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                        {filtered.map((c) => (
                            <Link
                                key={`${c.company}-${c.source_ats}`}
                                href={`/jobs?search=${encodeURIComponent(c.company)}`}
                                className="card-hover-lift flex items-center gap-4 rounded-[22px] border border-border bg-white p-5"
                            >
                                <CompanyLogo company={c.company} size="md" />
                                <div className="min-w-0 flex-1">
                                    <p className="truncate text-base font-black text-text-primary">{c.company}</p>
                                    <div className="mt-2 flex items-center gap-1.5">
                                        <span className="pill pill-accent text-xs">{c.job_count} open</span>
                                        <span className="pill pill-white text-xs">{sourceLabel(c.source_ats)}</span>
                                    </div>
                                </div>
                            </Link>
                        ))}
                    </div>
                )}
            </main>
        </div>
    );
}
