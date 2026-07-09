"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bookmark, UserRound } from "lucide-react";
import BrandMark from "./BrandMark";
import LiveJobFeed from "./LiveJobFeed";

const NAV_ITEMS = [
    { href: "/jobs", label: "Jobs" },
    { href: "/saved-roles", label: "Saved Roles" },
    { href: "/profile", label: "Profile" },
];

export default function TopNav() {
    const pathname = usePathname();

    return (
        <nav className="sticky top-0 z-50 border-b border-border/80 bg-background/88 backdrop-blur-xl">
            <div className="mx-auto flex h-20 max-w-7xl items-center justify-between gap-4 px-5 sm:px-6">
                <BrandMark />

                <div className="hidden items-center gap-1 rounded-2xl bg-white p-1 shadow-card md:flex">
                    {NAV_ITEMS.map((item) => {
                        const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={`rounded-xl px-4 py-2 text-sm font-bold transition-colors ${
                                    isActive ? "bg-ink text-white" : "text-text-secondary hover:bg-surface-2 hover:text-ink"
                                }`}
                            >
                                {item.label}
                            </Link>
                        );
                    })}
                </div>

                <div className="flex items-center gap-2">
                    <LiveJobFeed />
                    <Link href="/saved-roles" className="hidden items-center gap-2 rounded-xl border border-border bg-white px-3.5 py-2 text-sm font-bold text-ink shadow-card transition hover:bg-surface-2 sm:inline-flex">
                        <Bookmark className="h-4 w-4" />
                        Saved
                    </Link>
                    <Link href="/profile" className="rounded-xl bg-ink p-2.5 text-white transition hover:bg-neutral-800" aria-label="Profile">
                        <UserRound className="h-4 w-4" />
                    </Link>
                </div>
            </div>

            <div className="flex gap-1 overflow-x-auto border-t border-border/60 px-4 py-2 md:hidden">
                {NAV_ITEMS.map((item) => {
                    const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-bold ${
                                isActive ? "bg-ink text-white" : "bg-white text-text-secondary"
                            }`}
                        >
                            {item.label}
                        </Link>
                    );
                })}
            </div>
        </nav>
    );
}
