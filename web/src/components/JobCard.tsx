/* eslint-disable @next/next/no-img-element */
import { Button } from '@/components/ui/button';
import { BookmarkIcon } from 'lucide-react';

export interface JobProps {
    internal_hash: string;
    title: string;
    company: string;
    location: string;
    job_type?: string;
    salary_min?: number;
    salary_max?: number;
    salary_currency?: string;
    first_seen?: string;
    source_ats?: string;
    url?: string;
    keywords_matched?: string[];
}

function formatSalary(min?: number, max?: number, currency?: string) {
    const sym = currency === 'USD' ? '$' : '';
    if (min && max) return `${sym}${Math.floor(min / 1000)}k – ${sym}${Math.floor(max / 1000)}k`;
    if (min) return `${sym}${Math.floor(min / 1000)}k+`;
    return null;
}

function getAtsLabel(ats?: string) {
    const map: Record<string, string> = {
        linkedin: 'LinkedIn', indeed: 'Indeed', glassdoor: 'Glassdoor',
        greenhouse: 'Greenhouse', lever: 'Lever', workday: 'Workday',
        smartrecruiters: 'SmartRecruiters', ashby: 'Ashby',
    };
    return ats ? (map[ats.toLowerCase()] ?? ats) : 'Direct';
}

function formatDate(dateStr?: string) {
    if (!dateStr) return 'Recently';
    try {
        const d = new Date(dateStr);
        const now = new Date();
        const diffH = Math.floor((now.getTime() - d.getTime()) / 3600000);
        if (diffH < 1) return 'Just now';
        if (diffH < 24) return `${diffH}h ago`;
        const diffD = Math.floor(diffH / 24);
        if (diffD < 7) return `${diffD}d ago`;
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch { return 'Recently'; }
}

/** Row-style job card for the main feed */
export function JobCard({ job }: { job: JobProps }) {
    const fallbackLogo = `https://ui-avatars.com/api/?name=${encodeURIComponent(job.company)}&background=e88b68&color=fff&size=64&bold=true&length=1`;
    const salaryText = formatSalary(job.salary_min, job.salary_max, job.salary_currency);
    const atsLabel = getAtsLabel(job.source_ats);

    return (
        <a
            href={job.url || '#'}
            target="_blank"
            rel="noopener noreferrer"
            className="group bg-card hover:shadow-lg transition-all duration-200 rounded-2xl px-6 py-5 border border-black/[0.06] flex flex-col sm:flex-row items-start sm:items-center gap-5 mb-3 hover:-translate-y-px"
        >
            <div className="w-14 h-14 rounded-xl overflow-hidden shrink-0 border border-black/5 bg-white shadow-sm flex items-center justify-center">
                <img src={fallbackLogo} alt={`${job.company}`} className="w-full h-full object-cover" />
            </div>

            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-semibold text-muted-foreground">{job.company}</span>
                    <span className="text-muted-foreground/40">•</span>
                    <span className="text-xs text-muted-foreground">{atsLabel}</span>
                    <span className="text-muted-foreground/40">•</span>
                    <span className="text-xs text-muted-foreground">{formatDate(job.first_seen)}</span>
                </div>
                <h3 className="text-[1.1rem] font-bold text-foreground group-hover:text-primary transition-colors leading-snug truncate pr-4">
                    {job.title}
                </h3>
                <div className="flex flex-wrap items-center gap-2 mt-2.5">
                    {job.location && (
                        <span className="px-2.5 py-0.5 bg-muted rounded-md text-xs font-medium text-muted-foreground">{job.location}</span>
                    )}
                    {job.job_type && (
                        <span className="px-2.5 py-0.5 bg-muted rounded-md text-xs font-medium text-muted-foreground">{job.job_type}</span>
                    )}
                    {(job.keywords_matched ?? []).slice(0, 3).map((kw) => (
                        <span key={kw} className="px-2.5 py-0.5 bg-primary/10 text-primary/80 rounded-md text-xs font-medium">{kw}</span>
                    ))}
                </div>
            </div>

            <div className="flex items-center gap-3 self-end sm:self-auto">
                {salaryText && (
                    <span className="text-sm font-semibold text-green-700 bg-green-50 px-3 py-1 rounded-full border border-green-100 whitespace-nowrap">
                        {salaryText}
                    </span>
                )}
                <Button
                    onClick={(e) => e.preventDefault()}
                    variant="ghost"
                    size="icon"
                    className="rounded-full text-muted-foreground hover:text-foreground hover:bg-muted h-9 w-9 shrink-0 border border-black/5"
                >
                    <BookmarkIcon className="w-4 h-4" />
                </Button>
                <Button className="rounded-full px-5 py-2 bg-foreground hover:bg-foreground/85 text-white font-semibold text-sm transition-all hover:scale-[1.02] border-none shadow-sm h-9">
                    Apply
                </Button>
            </div>
        </a>
    );
}

/** Grid-style compact card for the /jobs page grid view */
export function JobGridCard({ job }: { job: JobProps }) {
    const fallbackLogo = `https://ui-avatars.com/api/?name=${encodeURIComponent(job.company)}&background=e88b68&color=fff&size=64&bold=true&length=1`;
    const salaryText = formatSalary(job.salary_min, job.salary_max, job.salary_currency);

    return (
        <a
            href={job.url || '#'}
            target="_blank"
            rel="noopener noreferrer"
            className="group bg-white hover:shadow-lg transition-all duration-200 rounded-3xl p-6 border border-black/[0.06] flex flex-col gap-4 hover:-translate-y-px"
        >
            <div className="flex items-start justify-between">
                <div className="w-12 h-12 rounded-xl overflow-hidden border border-black/5 bg-white shadow-sm flex items-center justify-center shrink-0">
                    <img src={fallbackLogo} alt={job.company} className="w-full h-full object-cover" />
                </div>
                <Button
                    onClick={(e) => e.preventDefault()}
                    variant="outline"
                    className="rounded-full text-xs h-8 px-3 border border-black/10 text-muted-foreground font-medium hover:bg-muted"
                >
                    <BookmarkIcon className="w-3 h-3 mr-1.5" />
                    Save
                </Button>
            </div>

            <div>
                <div className="text-xs text-muted-foreground mb-1 font-medium">{job.company} <span className="text-muted-foreground/50">·</span> {formatDate(job.first_seen)}</div>
                <h3 className="text-xl font-bold text-foreground group-hover:text-primary transition-colors leading-tight">
                    {job.title}
                </h3>
            </div>

            <div className="flex flex-wrap gap-2">
                {job.job_type && (
                    <span className="px-2.5 py-1 bg-slate-100 text-slate-600 rounded-lg text-xs font-semibold">{job.job_type}</span>
                )}
                {job.location && (
                    <span className="px-2.5 py-1 bg-slate-100 text-slate-600 rounded-lg text-xs font-semibold">{job.location}</span>
                )}
            </div>

            <div className="flex items-center justify-between mt-auto pt-2 border-t border-slate-50">
                <div>
                    {salaryText ? (
                        <div className="text-base font-bold text-foreground">{salaryText}</div>
                    ) : (
                        <div className="text-sm text-muted-foreground font-medium">{job.location || 'Remote'}</div>
                    )}
                </div>
                <Button className="rounded-full px-5 py-2 bg-foreground hover:bg-foreground/85 text-white font-semibold text-sm transition-all hover:scale-[1.02] border-none shadow-sm h-9">
                    Apply now
                </Button>
            </div>
        </a>
    );
}
