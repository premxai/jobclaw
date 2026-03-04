import { Search, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function SearchFilterBar() {
    return (
        <div className="max-w-5xl mx-auto mt-4 mb-16 px-4">
            <div className="flex flex-col lg:flex-row items-center bg-card rounded-2xl p-2.5 shadow-sm border border-black/5 gap-2">
                <div className="flex-1 flex items-center gap-2 px-4 min-w-[200px] border-b lg:border-b-0 lg:border-r border-slate-100 w-full lg:w-auto py-2 lg:py-0">
                    <input
                        type="text"
                        placeholder="Job title or company..."
                        className="w-full bg-transparent border-none outline-none text-sm placeholder:text-muted-foreground text-foreground font-medium"
                    />
                    <Search className="w-4 h-4 text-muted-foreground shrink-0" />
                </div>

                <div className="flex-1 flex items-center justify-between px-4 border-b lg:border-b-0 lg:border-r border-slate-100 cursor-pointer hover:bg-muted/50 rounded-lg p-2 transition-colors w-full lg:w-auto">
                    <span className="text-sm font-medium text-foreground/80">All categories</span>
                    <ChevronDown className="w-4 h-4 text-muted-foreground" />
                </div>

                <div className="flex-1 hidden md:flex items-center justify-between px-4 border-b lg:border-b-0 lg:border-r border-slate-100 cursor-pointer hover:bg-muted/50 rounded-lg p-2 transition-colors w-full lg:w-auto">
                    <span className="text-sm font-medium text-foreground/80">All related tags</span>
                    <ChevronDown className="w-4 h-4 text-muted-foreground" />
                </div>

                <div className="flex-1 hidden sm:flex items-center justify-between px-4 border-b lg:border-b-0 lg:border-r border-slate-100 cursor-pointer hover:bg-muted/50 rounded-lg p-2 transition-colors w-full lg:w-auto">
                    <span className="text-sm font-medium text-foreground/80">Job type</span>
                    <ChevronDown className="w-4 h-4 text-muted-foreground" />
                </div>

                <div className="flex-1 flex items-center justify-between px-4 cursor-pointer hover:bg-muted/50 rounded-lg p-2 transition-colors w-full lg:w-auto">
                    <span className="text-sm font-medium text-foreground/80">Location</span>
                    <ChevronDown className="w-4 h-4 text-muted-foreground" />
                </div>

                <div className="w-full lg:w-auto px-2 lg:px-0 pb-2 lg:pb-0 pt-2 lg:pt-0">
                    <Button className="w-full lg:w-auto rounded-xl px-8 bg-secondary hover:bg-secondary/90 text-white font-medium h-11 border-none shadow-sm">
                        Filter jobs
                    </Button>
                </div>
            </div>
        </div>
    );
}
