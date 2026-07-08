"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bookmark, BriefcaseBusiness, KanbanSquare, Settings, UserRound } from "lucide-react";
import NoriMark from "@/components/landing/NoriMark";

const navItems = [
    { label: "Live Feed", href: "/jobs", icon: BriefcaseBusiness },
    { label: "Saved Roles", href: "/saved-roles", icon: Bookmark },
    { label: "Tracker", href: "/tracker", icon: KanbanSquare },
    { label: "Profile", href: "/profile", icon: UserRound },
    { label: "Settings", href: "/settings", icon: Settings },
];

export default function NoriAppSidebar() {
    const pathname = usePathname();

    return (
        <aside className="fixed inset-y-0 left-0 z-30 hidden w-[280px] border-r border-[#E7D7B7] bg-[#FFF8EA] px-[18px] py-7 lg:flex lg:flex-col">
            <Link href="/" className="mb-[46px] flex items-center gap-3" aria-label="Nori home">
                <NoriMark />
                <span className="font-serif text-[34px] font-bold leading-none tracking-[-0.04em] text-[#1F281B]">Nori</span>
            </Link>

            <nav className="space-y-2.5" aria-label="Nori app navigation">
                {navItems.map(({ label, href, icon: Icon }) => {
                    const active = pathname === href || pathname.startsWith(`${href}/`);
                    return (
                        <Link
                            key={href}
                            href={href}
                            className={`flex h-14 items-center gap-3.5 rounded-[14px] px-[18px] text-[17px] transition ${
                                active ? "bg-[#EEF1DD] font-bold text-[#526736]" : "font-medium text-[#1F281B] hover:bg-[#FFF9EC]"
                            }`}
                        >
                            <Icon className="h-6 w-6" />
                            {label}
                        </Link>
                    );
                })}
            </nav>

            <div className="mt-auto">
                <div className="mb-8 rounded-[18px] border border-[#E7D7B7] bg-[#FFF9EC]/80 p-[18px] shadow-[0_8px_18px_rgba(70,45,16,0.06)]">
                    <div className="flex items-start gap-3">
                        <NoriMark />
                        <p className="text-[15px] font-medium leading-6 text-[#1F281B]">Nori keeps your roles, saves, and progress in one calm place.</p>
                    </div>
                    <Link href="/tracker" className="mt-3 inline-flex items-center gap-2 text-[15px] font-semibold text-[#526736]">
                        Open tracker
                    </Link>
                </div>

                <div className="relative -ml-12 h-80 overflow-hidden">
                    <div className="absolute bottom-0 left-0 h-64 w-48 -rotate-12 rounded-[20px] border border-[#526736]/35 bg-[#526736] shadow-[0_18px_34px_rgba(70,45,16,0.18)] [background-image:linear-gradient(rgba(82,103,54,0.42),rgba(82,103,54,0.42)),url('/nori-assets/notebook-texture.png')] [background-size:cover]" />
                    <span className="absolute bottom-12 left-28 h-48 w-40 rotate-12 opacity-80">
                        <Image src="/nori-assets/dried-flowers.png" alt="" aria-hidden="true" fill sizes="160px" className="object-contain" />
                    </span>
                </div>
            </div>
        </aside>
    );
}
