"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import TopNav from "@/components/TopNav";
import JobCard, { Job } from "@/components/JobCard";
import { fetchJobs, fetchStats } from "@/lib/api";
import { Search, ArrowRight, Zap, Building2, Clock } from "lucide-react";

export default function LandingPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [stats, setStats] = useState({ total_jobs: 608, total_companies: 11800, sources: 9 });
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    fetchJobs({ limit: 6 }).then((data) => setJobs(data.jobs.slice(0, 6)));
    fetchStats().then(setStats).catch(() => { });
  }, []);

  const handleSearch = () => {
    if (searchQuery.trim()) {
      window.location.href = `/jobs?search=${encodeURIComponent(searchQuery)}`;
    }
  };

  return (
    <div className="min-h-screen">
      <TopNav />

      {/* Hero */}
      <section className="pt-20 pb-16 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-5xl md:text-6xl font-bold tracking-tight mb-4 animate-fade-in">
            Track Every Tech Job.
            <br />
            <span className="text-accent">Automatically.</span>
          </h1>
          <p className="text-lg text-text-secondary max-w-2xl mx-auto mb-10 animate-fade-in">
            {stats.total_companies.toLocaleString()}+ companies monitored 24/7. Updated every hour from
            Greenhouse, Lever, Workday, LinkedIn, and more.
          </p>

          {/* Search bar */}
          <div className="max-w-xl mx-auto mb-16 animate-slide-up">
            <div className="flex items-center bg-surface border border-border rounded-xl overflow-hidden focus-within:border-accent transition-colors">
              <Search className="w-5 h-5 text-text-secondary ml-4 shrink-0" />
              <input
                type="text"
                placeholder="Search jobs, companies, or keywords…"
                className="flex-1 bg-transparent px-4 py-4 text-text-primary placeholder-text-secondary text-sm outline-none"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              />
              <button onClick={handleSearch} className="btn-primary m-1.5 rounded-lg">
                Search
              </button>
            </div>
          </div>
        </div>

        {/* Stats */}
        <div className="max-w-3xl mx-auto grid grid-cols-3 gap-4 mb-20">
          {[
            { icon: Zap, value: `${stats.total_jobs}+`, label: "Jobs Tracked", color: "text-accent" },
            { icon: Building2, value: stats.total_companies.toLocaleString(), label: "Companies", color: "text-info" },
            { icon: Clock, value: "24/7", label: "Monitoring", color: "text-success" },
          ].map((stat, i) => (
            <div key={i} className="stat-card text-center animate-slide-up" style={{ animationDelay: `${i * 100}ms` }}>
              <stat.icon className={`w-6 h-6 ${stat.color} mx-auto mb-2`} />
              <div className={`text-3xl font-bold ${stat.color}`}>{stat.value}</div>
              <div className="text-sm text-text-secondary mt-1">{stat.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Latest Jobs */}
      <section className="pb-20 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="flex items-center justify-between mb-8">
            <h2 className="section-heading">Latest Jobs</h2>
            <Link href="/jobs" className="flex items-center gap-1 text-accent text-sm font-medium hover:underline">
              View all <ArrowRight className="w-4 h-4" />
            </Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {jobs.map((job, i) => (
              <div key={job.internal_hash || i} className="animate-slide-up" style={{ animationDelay: `${i * 50}ms` }}>
                <Link href={`/jobs/${job.id}`}>
                  <JobCard job={job} />
                </Link>
              </div>
            ))}
          </div>

          {jobs.length === 0 && (
            <div className="text-center py-20">
              <p className="text-text-secondary">Loading latest jobs…</p>
            </div>
          )}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border py-8 px-6">
        <div className="max-w-6xl mx-auto flex items-center justify-between text-sm text-text-secondary">
          <p>🦀 JobClaw — Tracking {stats.total_companies.toLocaleString()} companies</p>
          <div className="flex items-center gap-4">
            <Link href="/jobs" className="hover:text-text-primary transition-colors">Jobs</Link>
            <Link href="/tracker" className="hover:text-text-primary transition-colors">Tracker</Link>
            <Link href="/dashboard" className="hover:text-text-primary transition-colors">Dashboard</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
