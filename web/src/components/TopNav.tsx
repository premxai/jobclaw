"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
    { href: "/", label: "Home" },
    { href: "/jobs", label: "Jobs" },
    { href: "/tracker", label: "Tracker" },
    { href: "/dashboard", label: "Dashboard" },
];

export default function TopNav() {
    const pathname = usePathname();

    return (
        <nav className="sticky top-0 z-50 bg-[#FAF7F2]/90 backdrop-blur-md border-b border-border">
            <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
                {/* Logo */}
                <Link href="/" className="flex items-center gap-2 group">
                    <span className="text-2xl">🦀</span>
                    <span className="text-lg font-bold text-text-primary tracking-tight">
                        Job<span className="text-accent">Claw</span>
                    </span>
                </Link>

                {/* Nav links */}
                <div className="hidden md:flex items-center gap-1">
                    {NAV_ITEMS.map((item) => {
                        const isActive = pathname === item.href ||
                            (item.href !== "/" && pathname.startsWith(item.href));
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${isActive
                                        ? "text-accent bg-accent-light"
                                        : "text-text-secondary hover:text-text-primary hover:bg-surface-2"
                                    }`}
                            >
                                {item.label}
                            </Link>
                        );
                    })}
                </div>

                {/* Mobile */}
                <div className="md:hidden flex items-center gap-1">
                    {NAV_ITEMS.map((item) => {
                        const isActive = pathname === item.href ||
                            (item.href !== "/" && pathname.startsWith(item.href));
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors ${isActive
                                        ? "text-accent bg-accent-light"
                                        : "text-text-secondary hover:text-text-primary"
                                    }`}
                            >
                                {item.label}
                            </Link>
                        );
                    })}
                </div>
            </div>
        </nav>
    );
}
