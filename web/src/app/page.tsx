"use client";

import { useEffect, useState, useCallback } from 'react';
import { TopNav } from '@/components/TopNav';
import { HeroSection } from '@/components/HeroSection';
import { SearchFilterBar } from '@/components/SearchFilterBar';
import { JobCard, JobGridCard, JobProps } from '@/components/JobCard';
import { Button } from '@/components/ui/button';
import { Grid2X2, List, Loader2 } from 'lucide-react';

const PAGE_SIZE = 20;

export default function Home() {
  const [jobs, setJobs] = useState<JobProps[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [view, setView] = useState<'list' | 'grid'>('list');

  const fetchJobs = useCallback(async (pageNum: number, replace = false) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/jobs?page=${pageNum}&per_page=${PAGE_SIZE}`);
      if (res.ok) {
        const data = await res.json();
        const incoming: JobProps[] = data.jobs ?? [];
        setJobs(prev => replace ? incoming : [...prev, ...incoming]);
        setHasMore(data.has_more ?? incoming.length === PAGE_SIZE);
      }
    } catch (err) {
      console.error('Failed to fetch jobs:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs(1, true);
  }, [fetchJobs]);

  const loadMore = () => {
    const next = page + 1;
    setPage(next);
    fetchJobs(next);
  };

  return (
    <div className="min-h-screen bg-background text-foreground font-sans selection:bg-primary/20">
      <TopNav />
      <main className="px-4 pb-24">
        <HeroSection />
        <SearchFilterBar />

        {/* View toggle + count */}
        <div className="max-w-5xl mx-auto flex items-center justify-between mb-6 px-1">
          <span className="text-sm font-semibold text-muted-foreground">
            {loading && jobs.length === 0 ? 'Loading jobs…' : `${jobs.length} jobs found`}
          </span>
          <div className="flex items-center gap-1 bg-muted rounded-xl p-1">
            <button
              onClick={() => setView('list')}
              className={`p-2 rounded-lg transition-colors ${view === 'list' ? 'bg-white shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
            >
              <List className="w-4 h-4" />
            </button>
            <button
              onClick={() => setView('grid')}
              className={`p-2 rounded-lg transition-colors ${view === 'grid' ? 'bg-white shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
            >
              <Grid2X2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Job listings */}
        <div className="max-w-5xl mx-auto">
          {loading && jobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 gap-4 text-muted-foreground">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
              <span className="font-medium">Loading the latest jobs…</span>
            </div>
          ) : jobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
              <span className="text-4xl">🔍</span>
              <span className="font-semibold text-lg text-foreground">No jobs found yet</span>
              <span className="text-sm">The scraper is running — check back in a few minutes!</span>
            </div>
          ) : view === 'list' ? (
            <div className="flex flex-col gap-0">
              {jobs.map((job) => <JobCard key={job.internal_hash} job={job} />)}
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {jobs.map((job) => <JobGridCard key={job.internal_hash} job={job} />)}
            </div>
          )}

          {/* Load more */}
          {!loading && hasMore && jobs.length > 0 && (
            <div className="flex justify-center mt-10">
              <Button
                onClick={loadMore}
                variant="outline"
                className="rounded-full px-8 h-11 font-semibold border-black/10 hover:bg-muted"
              >
                Load more jobs
              </Button>
            </div>
          )}
          {loading && jobs.length > 0 && (
            <div className="flex justify-center mt-10">
              <Loader2 className="w-5 h-5 animate-spin text-primary" />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
