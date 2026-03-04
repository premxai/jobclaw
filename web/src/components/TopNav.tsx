import Link from 'next/link';
import { Button } from '@/components/ui/button';

export function TopNav() {
    return (
        <nav className="w-full flex items-center justify-between py-6 px-8 max-w-7xl mx-auto">
            <div className="flex items-center gap-2 font-semibold text-lg hover:opacity-80 transition-opacity cursor-pointer">
                <span className="text-foreground">JobClaw</span>
            </div>

            <div className="hidden md:flex items-center gap-8 text-sm font-medium text-foreground/80">
                <Link href="/jobs" className="hover:text-primary transition-colors">Jobs</Link>
                <Link href="/companies" className="hover:text-primary transition-colors">Companies</Link>
                <Link href="/blog" className="hover:text-primary transition-colors">Blog</Link>
            </div>

            <div className="flex items-center gap-4">
                <Button variant="outline" className="rounded-full px-6 border-slate-200">Sign in</Button>
                <Button className="rounded-full px-6 bg-primary hover:bg-primary/90 text-white shadow-sm border-none">Post a job</Button>
            </div>
        </nav>
    );
}
