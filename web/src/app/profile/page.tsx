"use client";

import Image from "next/image";
import Link from "next/link";
import {
    ArrowRight,
    Bell,
    Bookmark,
    Calendar,
    ChevronDown,
    ClipboardCheck,
    Compass,
    Edit3,
    Home,
    MapPin,
    Search,
    Settings,
    Sparkles,
    Target,
    Trophy,
    UserRound,
} from "lucide-react";
import NoriMark from "@/components/landing/NoriMark";

const sidebarNav = [
    { label: "Home", href: "/", icon: Home },
    { label: "Profile", href: "/profile", icon: UserRound, active: true },
    { label: "Applications", href: "/jobs", icon: ClipboardCheck },
    { label: "Saved roles", href: "/saved-roles", icon: Bookmark },
    { label: "Settings", href: "/settings", icon: Settings },
];

const summaryItems = [
    { label: "Total applied", value: "22", icon: ClipboardCheck },
    { label: "In progress", value: "14 (64%)", icon: Target },
    { label: "Converted to offer", value: "2 (9%)", icon: Trophy },
    { label: "Rejected", value: "4 (18%)", icon: Bell },
    { label: "Withdrawn", value: "2 (9%)", icon: Compass },
];

function ProfileSidebar() {
    return (
        <aside className="fixed inset-y-0 left-0 z-30 hidden w-[320px] border-r border-[#E7D7B7] bg-[#FFF8EA] px-6 py-7 lg:flex lg:flex-col 2xl:w-[320px]">
            <Link href="/" className="mb-12 flex items-center gap-3" aria-label="Nori home">
                <NoriMark />
                <span className="font-serif text-[38px] font-bold leading-none tracking-[-0.04em] text-[#1F281B]">Nori</span>
            </Link>

            <nav className="space-y-2.5" aria-label="Profile navigation">
                {sidebarNav.map(({ label, href, icon: Icon, active }) => (
                    <Link
                        key={label}
                        href={href}
                        className={`flex min-h-14 items-center gap-4 rounded-[14px] px-[18px] text-[17px] transition ${
                            active ? "bg-[#EEF1DD] font-bold text-[#526736]" : "font-medium text-[#1F281B] hover:bg-[#FFF9EC]"
                        }`}
                    >
                        <Icon className="h-6 w-6" />
                        {label}
                    </Link>
                ))}
            </nav>

            <div className="mt-auto">
                <div className="mb-8 rounded-[18px] border border-[#E7D7B7] bg-[#FFF9EC]/80 p-[18px] shadow-[0_8px_18px_rgba(70,45,16,0.06)]">
                    <div className="flex items-start gap-3">
                        <NoriMark />
                        <p className="text-[15px] font-medium leading-6 text-[#1F281B]">Nori is quietly scouting roles that match your profile.</p>
                    </div>
                    <Link href="/jobs" className="mt-3 inline-flex items-center gap-2 text-[15px] font-semibold text-[#526736]">
                        See today&apos;s notes
                        <ArrowRight className="h-4 w-4" />
                    </Link>
                </div>

                <div className="relative -ml-14 h-80 overflow-hidden">
                    <div className="absolute bottom-0 left-0 h-64 w-52 -rotate-12 rounded-[20px] border border-[#526736]/35 bg-[#526736] shadow-[0_18px_34px_rgba(70,45,16,0.18)] [background-image:linear-gradient(rgba(82,103,54,0.42),rgba(82,103,54,0.42)),url('/nori-assets/notebook-texture.png')] [background-size:cover]" />
                    <span className="absolute bottom-11 left-32 h-52 w-44 rotate-12 opacity-85">
                        <Image src="/nori-assets/dried-flowers.png" alt="" aria-hidden="true" fill sizes="176px" className="object-contain" />
                    </span>
                </div>
            </div>
        </aside>
    );
}

function ProfileHeader() {
    return (
        <header className="sticky top-0 z-20 flex min-h-[100px] items-center gap-6 border-b border-[#E7D7B7] bg-[#FFF9EC]/86 px-5 backdrop-blur-md sm:px-8 lg:ml-[280px] lg:px-11 2xl:ml-[320px]">
            <Link href="/" className="flex items-center gap-2 lg:hidden" aria-label="Nori home">
                <NoriMark />
                <span className="font-serif text-3xl font-bold tracking-[-0.04em] text-[#1F281B]">Nori</span>
            </Link>

            <div className="hidden h-14 flex-1 max-w-[820px] items-center gap-4 rounded-[14px] border border-[#D8C9A7] bg-[#FFF9EC] px-[22px] shadow-[0_4px_12px_rgba(70,45,16,0.04)] sm:flex">
                <Search className="h-[22px] w-[22px] shrink-0 text-[#0F2744]" />
                <input
                    placeholder="Search profile, skills, or preferences..."
                    className="h-full min-w-0 flex-1 bg-transparent text-[15px] text-[#1F281B] placeholder:text-[#7B7F70] focus:outline-none"
                    aria-label="Search profile, skills, or preferences"
                />
            </div>

            <div className="ml-auto hidden items-center gap-2.5 text-[15px] font-medium text-[#1F281B] xl:flex">
                <Calendar className="h-5 w-5" />
                May 15, 2025
                <span aria-hidden="true">·</span>
                10:24 AM
            </div>

            <div className="hidden h-11 w-px bg-[#E7D7B7] xl:block" />

            <Link href="/profile" className="flex items-center gap-3">
                <span className="relative grid h-12 w-12 place-items-center overflow-hidden rounded-full border border-[#E7D7B7] bg-[#EFD3B0] text-sm font-black text-[#1F281B] shadow-sm">
                    AC
                    <span className="absolute inset-x-2 bottom-1 h-2 rounded-full bg-[#D9A978]/70" />
                </span>
                <span className="hidden leading-tight sm:block">
                    <span className="block text-[15px] font-bold text-[#1F281B]">Alex Chen</span>
                    <span className="block text-[13px] font-medium text-[#5F665C]">Premium Scout</span>
                </span>
                <ChevronDown className="hidden h-4 w-4 text-[#526736] sm:block" />
            </Link>
        </header>
    );
}

function Pin({ className = "" }: { className?: string }) {
    return <span className={`absolute h-[18px] w-[18px] rounded-full bg-[#C99635] shadow-[0_4px_8px_rgba(70,45,16,0.18),inset_0_1px_2px_rgba(255,255,255,0.55)] ${className}`} />;
}

function ProfileSummaryCard() {
    return (
        <section className="relative min-h-[210px] rounded-2xl border border-[#E7D7B7] bg-[#FFF9EC] p-6 shadow-[0_10px_24px_rgba(70,45,16,0.08)] [background-image:linear-gradient(rgba(255,249,236,0.82),rgba(255,249,236,0.82)),url('/nori-assets/paper-texture.png')] [background-size:cover] sm:p-7">
            <Pin className="left-1/2 top-[-8px] -translate-x-1/2" />
            <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
                <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
                    <div className="relative grid h-[132px] w-[132px] shrink-0 place-items-center overflow-hidden rounded-full border border-[#E7D7B7] bg-[#F0D4B1] shadow-[0_8px_18px_rgba(70,45,16,0.08)]">
                        <span className="text-[42px] font-black text-[#1F281B]">AC</span>
                        <span className="absolute bottom-5 h-7 w-20 rounded-t-full bg-[#BC7C53]/50" />
                    </div>
                    <div>
                        <p className="mb-2 inline-flex items-center gap-2 rounded-full border border-[#D8C9A7] bg-[#F7EED7] px-3 py-1 text-sm font-semibold text-[#526736]">
                            <Sparkles className="h-4 w-4 text-[#C99635]" />
                            Premium Scout
                        </p>
                        <h1 className="font-serif text-[42px] font-bold leading-none tracking-[-0.045em] text-[#1F281B]">Alex Chen</h1>
                        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-[18px] font-medium text-[#5F665C]">
                            <span>Senior Product Designer</span>
                            <span className="inline-flex items-center gap-1.5">
                                <MapPin className="h-4 w-4" />
                                San Francisco
                            </span>
                        </div>
                    </div>
                </div>

                <button
                    type="button"
                    aria-label="Edit profile"
                    className="inline-flex min-h-11 items-center justify-center gap-2 rounded-[10px] border border-[#D8C9A7] bg-[#FFF9EC] px-4 text-sm font-bold text-[#1F281B] transition hover:bg-[#EEF1DD] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#526736]"
                >
                    <Edit3 className="h-4 w-4" />
                    Edit profile
                </button>
            </div>
        </section>
    );
}

function MetricCards() {
    return (
        <div className="mt-6 grid gap-6 xl:grid-cols-2">
            <section className="relative rounded-2xl border border-[#E7D7B7] bg-[#FFF9EC] p-6 shadow-[0_8px_18px_rgba(70,45,16,0.06)] [background-image:linear-gradient(rgba(255,249,236,0.84),rgba(255,249,236,0.84)),url('/nori-assets/paper-texture.png')] [background-size:cover]">
                <Pin className="right-8 top-[-8px]" />
                <div className="flex items-start justify-between gap-4">
                    <div>
                        <h2 className="font-serif text-2xl font-bold tracking-[-0.035em] text-[#1F281B]">Daily target</h2>
                        <p className="mt-1 text-sm font-medium text-[#5F665C]">Applications to keep momentum.</p>
                    </div>
                    <button
                        type="button"
                        aria-label="Edit daily target"
                        className="grid min-h-11 min-w-11 place-items-center rounded-[10px] border border-[#D8C9A7] bg-[#FFF9EC] text-[#526736] transition hover:bg-[#EEF1DD] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#526736]"
                    >
                        <Edit3 className="h-4 w-4" />
                    </button>
                </div>
                <div className="mt-6 flex items-end justify-between gap-4">
                    <p className="font-serif text-4xl font-bold leading-none text-[#1F281B]">
                        18<span className="text-2xl text-[#5F665C]">/25</span>
                    </p>
                    <p className="text-sm font-bold text-[#526736]">72%</p>
                </div>
                <div className="mt-4 h-3 overflow-hidden rounded-full bg-[#E7D7B7]">
                    <div className="h-full w-[72%] rounded-full bg-[#526736]" />
                </div>
            </section>

            <section className="relative rounded-2xl border border-[#E7D7B7] bg-[#FFF9EC] p-6 shadow-[0_8px_18px_rgba(70,45,16,0.06)] [background-image:linear-gradient(rgba(255,249,236,0.84),rgba(255,249,236,0.84)),url('/nori-assets/paper-texture.png')] [background-size:cover]">
                <Pin className="right-8 top-[-8px]" />
                <h2 className="font-serif text-2xl font-bold tracking-[-0.035em] text-[#1F281B]">Jobs applied</h2>
                <p className="mt-1 text-sm font-medium text-[#5F665C]">This week across saved roles and direct applies.</p>
                <div className="mt-5 flex items-end justify-between gap-4">
                    <p className="font-serif text-[58px] font-bold leading-none tracking-[-0.045em] text-[#1F281B]">42</p>
                    <span className="mb-2 inline-flex items-center gap-2 rounded-full border border-[#D8C9A7] bg-[#F7EED7] px-3 py-1 text-sm font-bold text-[#526736]">
                        <ArrowRight className="h-4 w-4 -rotate-45" />
                        +11%
                    </span>
                </div>
            </section>
        </div>
    );
}

function SankeyGraph() {
    return (
        <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(640px,1fr)_190px]">
            <div className="overflow-x-auto pb-2" role="img" aria-label="Application status: 22 applied, 8 OA, 6 interview, 2 offers, 4 rejected, 2 withdrawn.">
                <svg className="h-[195px] min-w-[700px] w-full" viewBox="0 0 760 195" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M126 92 C188 92 188 70 238 70" stroke="rgba(142,148,99,0.35)" strokeWidth="48" strokeLinecap="round" />
                    <path d="M126 114 C236 142 316 144 392 110" stroke="rgba(142,148,99,0.28)" strokeWidth="34" strokeLinecap="round" />
                    <path d="M366 82 C394 82 414 92 452 92" stroke="rgba(232,184,91,0.35)" strokeWidth="42" strokeLinecap="round" />
                    <path d="M552 79 C590 64 600 38 642 38" stroke="rgba(112,128,82,0.35)" strokeWidth="24" strokeLinecap="round" />
                    <path d="M552 98 C594 98 598 96 642 96" stroke="rgba(216,120,97,0.35)" strokeWidth="36" strokeLinecap="round" />
                    <path d="M552 118 C592 132 600 150 642 150" stroke="rgba(150,145,132,0.35)" strokeWidth="24" strokeLinecap="round" />

                    <foreignObject x="10" y="30" width="120" height="135">
                        <div className="flex h-full flex-col items-center justify-center rounded-[10px] bg-[#A5A777] text-[#1F281B] shadow-sm">
                            <span className="text-[16px] font-semibold">Applied</span>
                            <span className="mt-1 text-[20px] font-bold">22</span>
                        </div>
                    </foreignObject>
                    <foreignObject x="238" y="46" width="130" height="100">
                        <div className="flex h-full flex-col items-center justify-center rounded-[10px] bg-[#C7C78B] text-[#1F281B] shadow-sm">
                            <span className="text-[16px] font-semibold">OA</span>
                            <span className="mt-1 text-[20px] font-bold">8</span>
                        </div>
                    </foreignObject>
                    <foreignObject x="442" y="50" width="120" height="95">
                        <div className="flex h-full flex-col items-center justify-center rounded-[10px] bg-[#E8B85B] text-[#1F281B] shadow-sm">
                            <span className="text-[16px] font-semibold">Interview</span>
                            <span className="mt-1 text-[20px] font-bold">6</span>
                        </div>
                    </foreignObject>
                    <foreignObject x="620" y="10" width="130" height="58">
                        <div className="flex h-full items-center justify-between rounded-[10px] bg-[#C7D0A4] px-5 text-[#1F281B] shadow-sm">
                            <span className="text-[16px] font-semibold">Offer</span>
                            <span className="text-[20px] font-bold">2</span>
                        </div>
                    </foreignObject>
                    <foreignObject x="620" y="80" width="130" height="58">
                        <div className="flex h-full items-center justify-between rounded-[10px] bg-[#E3A08E] px-5 text-[#1F281B] shadow-sm">
                            <span className="text-[16px] font-semibold">Rejected</span>
                            <span className="text-[20px] font-bold">4</span>
                        </div>
                    </foreignObject>
                    <foreignObject x="620" y="145" width="130" height="58">
                        <div className="flex h-full items-center justify-between rounded-[10px] bg-[#D7D2C8] px-5 text-[#1F281B] shadow-sm">
                            <span className="text-[16px] font-semibold">Withdrawn</span>
                            <span className="text-[20px] font-bold">2</span>
                        </div>
                    </foreignObject>
                </svg>
            </div>

            <div className="border-[#E7D7B7] pl-0 xl:border-l xl:pl-6">
                <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                    {[
                        ["Offer", "9%", "#708052"],
                        ["Rejected", "18%", "#D87861"],
                        ["Withdrawn", "9%", "#969184"],
                        ["In progress", "64%", "#8E9463"],
                    ].map(([label, value, color]) => (
                        <div key={label} className="flex items-center justify-between gap-3 text-[14px] font-medium text-[#5F665C]">
                            <dt className="flex items-center gap-3">
                                <span className="h-3 w-3 rounded-full" style={{ backgroundColor: color }} />
                                {label}
                            </dt>
                            <dd className="font-bold text-[#1F281B]">{value}</dd>
                        </div>
                    ))}
                </dl>
            </div>
        </div>
    );
}

function ApplicationStatusCard() {
    return (
        <section className="relative mt-6 rounded-2xl border border-[#E7D7B7] bg-[#FFF9EC] px-5 py-6 shadow-[0_10px_24px_rgba(70,45,16,0.08)] [background-image:linear-gradient(rgba(255,249,236,0.84),rgba(255,249,236,0.84)),url('/nori-assets/paper-texture.png')] [background-size:cover] sm:px-8 sm:py-7">
            <Pin className="left-1/2 top-[-8px] -translate-x-1/2" />
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <h2 className="font-serif text-[26px] font-bold tracking-[-0.035em] text-[#1F281B]">Application status</h2>
                <button
                    type="button"
                    aria-label="Change date range"
                    className="inline-flex min-h-[42px] items-center justify-center gap-2 rounded-[10px] border border-[#D8C9A7] bg-[#FFF9EC] px-4 text-sm font-semibold text-[#1F281B] transition hover:bg-[#EEF1DD] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#526736]"
                >
                    <Calendar className="h-4 w-4 text-[#526736]" />
                    This week
                    <ChevronDown className="h-4 w-4" />
                </button>
            </div>

            <SankeyGraph />

            <div className="mt-[18px] grid border-t border-[#E7D7B7] pt-[18px] sm:grid-cols-2 xl:grid-cols-5">
                {summaryItems.map(({ label, value, icon: Icon }, index) => (
                    <div key={label} className={`flex items-center gap-3 py-3 xl:px-4 xl:py-0 ${index > 0 ? "xl:border-l xl:border-[#E7D7B7]" : ""}`}>
                        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-[#F2E8C9] text-[#526736]">
                            <Icon className="h-5 w-5" />
                        </span>
                        <div>
                            <p className="text-[14px] font-medium text-[#5F665C]">{label}</p>
                            <p className="text-[15px] font-bold text-[#1F281B]">{value}</p>
                        </div>
                    </div>
                ))}
            </div>
        </section>
    );
}

export default function ProfilePage() {
    return (
        <div className="min-h-screen bg-[#FFF3D6] text-[#1F281B] [background-image:radial-gradient(circle_at_8%_8%,rgba(146,189,179,0.25),transparent_32%),radial-gradient(circle_at_96%_4%,rgba(255,211,130,0.26),transparent_30%),linear-gradient(rgba(255,243,214,0.80),rgba(255,243,214,0.80)),url('/nori-assets/desk-paper-texture.png')] [background-size:auto,auto,auto,520px]">
            <ProfileSidebar />
            <ProfileHeader />

            <main className="px-5 py-8 sm:px-8 lg:ml-[280px] lg:px-11 2xl:ml-[320px]">
                <div className="mx-auto max-w-[1280px]">
                    <div className="mb-4 flex items-center justify-between gap-4">
                        <div>
                            <p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-[#526736]">Profile dashboard</p>
                            <h1 className="font-serif text-[38px] font-bold leading-tight tracking-[-0.045em] text-[#1F281B]">My Profile</h1>
                        </div>
                        <Link
                            href="/jobs"
                            className="hidden min-h-11 items-center gap-2 rounded-[10px] bg-[#526736] px-5 text-sm font-bold text-white shadow-[0_10px_18px_rgba(70,45,16,0.16)] transition hover:bg-[#415329] sm:inline-flex"
                        >
                            Browse jobs
                            <ArrowRight className="h-4 w-4" />
                        </Link>
                    </div>

                    <ProfileSummaryCard />
                    <MetricCards />
                    <ApplicationStatusCard />
                </div>
            </main>
        </div>
    );
}
