import { Briefcase, Monitor, MonitorPlay, Code2 } from 'lucide-react';

export function HeroSection() {
    return (
        <section className="flex flex-col items-center justify-center pt-16 pb-12 px-4 text-center max-w-4xl mx-auto">
            <h1 className="text-5xl md:text-6xl font-extrabold tracking-tight text-foreground mb-6 leading-[1.15]">
                Find top jobs for AI engineers and developers.
            </h1>
            <p className="text-lg text-muted-foreground mb-10 max-w-2xl px-4">
                Hiring? Connect with over 11,000 talented engineers and developers available for full-time, part-time, or freelance opportunities.
            </p>

            <div className="flex flex-wrap items-center justify-center gap-4">
                <button className="flex items-center gap-2 px-5 py-2.5 bg-muted hover:bg-slate-200 transition-colors rounded-xl text-sm font-semibold border border-black/5 text-foreground/80">
                    <Monitor className="w-4 h-4 text-slate-500" /> Web Design
                </button>
                <button className="flex items-center gap-2 px-5 py-2.5 bg-muted hover:bg-slate-200 transition-colors rounded-xl text-sm font-semibold border border-black/5 text-foreground/80">
                    <Code2 className="w-4 h-4 text-slate-500" /> Web Development
                </button>
                <button className="flex items-center gap-2 px-5 py-2.5 bg-muted hover:bg-slate-200 transition-colors rounded-xl text-sm font-semibold border border-black/5 text-foreground/80">
                    <Briefcase className="w-4 h-4 text-slate-500" /> Web Entry
                </button>
            </div>
        </section>
    );
}
