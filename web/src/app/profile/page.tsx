"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
    ArrowRight,
    Bell,
    Calendar,
    ChevronDown,
    ClipboardCheck,
    Compass,
    Edit3,
    MapPin,
    Search,
    Sparkles,
    Target,
    Trophy,
} from "lucide-react";
import NoriAppSidebar from "@/components/NoriAppSidebar";
import NoriMark from "@/components/landing/NoriMark";

interface TrackedRole {
    status?: string | null;
}

interface PipelineCounts {
    saved: number;
    applied: number;
    oa: number;
    interview: number;
    offer: number;
    rejected: number;
    withdrawn: number;
}

const emptyPipeline: PipelineCounts = {
    saved: 0,
    applied: 0,
    oa: 0,
    interview: 0,
    offer: 0,
    rejected: 0,
    withdrawn: 0,
};

const activeStages = ["applied", "oa", "interview"] as const;

function getAppliedTotal(counts: PipelineCounts) {
    return counts.applied + counts.oa + counts.interview + counts.offer + counts.rejected + counts.withdrawn;
}

function percent(value: number, total: number) {
    if (total <= 0) return "0%";
    return `${Math.round((value / total) * 100)}%`;
}

function ProfileHeader() {
    return (
        <header className="sticky top-0 z-20 flex min-h-[100px] items-center gap-6 border-b border-[#E7D7B7] bg-[#FFF9EC]/86 px-5 backdrop-blur-md sm:px-8 lg:ml-[280px] lg:px-11">
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

                <Link
                    href="/settings"
                    aria-label="Edit profile"
                    className="inline-flex min-h-11 items-center justify-center gap-2 rounded-[10px] border border-[#D8C9A7] bg-[#FFF9EC] px-4 text-sm font-bold text-[#1F281B] transition hover:bg-[#EEF1DD] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#526736]"
                >
                    <Edit3 className="h-4 w-4" />
                    Edit profile
                </Link>
            </div>
        </section>
    );
}

function MetricCards({ appliedTotal }: { appliedTotal: number }) {
    const dailyTarget = 25;
    const dailyProgress = Math.min(100, Math.round((appliedTotal / dailyTarget) * 100));

    return (
        <div className="mt-6 grid gap-6 xl:grid-cols-2">
            <section className="relative rounded-2xl border border-[#E7D7B7] bg-[#FFF9EC] p-6 shadow-[0_8px_18px_rgba(70,45,16,0.06)] [background-image:linear-gradient(rgba(255,249,236,0.84),rgba(255,249,236,0.84)),url('/nori-assets/paper-texture.png')] [background-size:cover]">
                <Pin className="right-8 top-[-8px]" />
                <div className="flex items-start justify-between gap-4">
                    <div>
                        <h2 className="font-serif text-2xl font-bold tracking-[-0.035em] text-[#1F281B]">Daily target</h2>
                        <p className="mt-1 text-sm font-medium text-[#5F665C]">Applications to keep momentum.</p>
                    </div>
                    <Link
                        href="/settings"
                        aria-label="Edit daily target"
                        className="grid min-h-11 min-w-11 place-items-center rounded-[10px] border border-[#D8C9A7] bg-[#FFF9EC] text-[#526736] transition hover:bg-[#EEF1DD] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#526736]"
                    >
                        <Edit3 className="h-4 w-4" />
                    </Link>
                </div>
                <div className="mt-6 flex items-end justify-between gap-4">
                    <p className="font-serif text-4xl font-bold leading-none text-[#1F281B]">
                        {appliedTotal}<span className="text-2xl text-[#5F665C]">/{dailyTarget}</span>
                    </p>
                    <p className="text-sm font-bold text-[#526736]">{dailyProgress}%</p>
                </div>
                <div className="mt-4 h-3 overflow-hidden rounded-full bg-[#E7D7B7]">
                    <div className="h-full rounded-full bg-[#526736]" style={{ width: `${dailyProgress}%` }} />
                </div>
            </section>

            <section className="relative rounded-2xl border border-[#E7D7B7] bg-[#FFF9EC] p-6 shadow-[0_8px_18px_rgba(70,45,16,0.06)] [background-image:linear-gradient(rgba(255,249,236,0.84),rgba(255,249,236,0.84)),url('/nori-assets/paper-texture.png')] [background-size:cover]">
                <Pin className="right-8 top-[-8px]" />
                <h2 className="font-serif text-2xl font-bold tracking-[-0.035em] text-[#1F281B]">Jobs applied</h2>
                <p className="mt-1 text-sm font-medium text-[#5F665C]">This week across saved roles and direct applies.</p>
                <div className="mt-5 flex items-end justify-between gap-4">
                    <p className="font-serif text-[58px] font-bold leading-none tracking-[-0.045em] text-[#1F281B]">{appliedTotal}</p>
                    <span className="mb-2 inline-flex items-center gap-2 rounded-full border border-[#D8C9A7] bg-[#F7EED7] px-3 py-1 text-sm font-bold text-[#526736]">
                        <ArrowRight className="h-4 w-4 -rotate-45" />
                        +11%
                    </span>
                </div>
            </section>
        </div>
    );
}

function StageBarChart({ counts }: { counts: PipelineCounts }) {
    const appliedTotal = getAppliedTotal(counts);
    const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
    const max = Math.max(1, ...Object.values(counts));
    const bars = [
        { key: "saved", label: "Saved", value: counts.saved, color: "#A5A777" },
        { key: "applied", label: "Applied", value: counts.applied, color: "#8E9463" },
        { key: "oa", label: "OA", value: counts.oa, color: "#C7C78B" },
        { key: "interview", label: "Interview", value: counts.interview, color: "#E8B85B" },
        { key: "offer", label: "Offer", value: counts.offer, color: "#708052" },
        { key: "rejected", label: "Rejected", value: counts.rejected, color: "#D87861" },
        { key: "withdrawn", label: "Withdrawn", value: counts.withdrawn, color: "#969184" },
    ];
    const ariaSummary = `Tracker status: ${counts.saved} saved, ${counts.applied} applied, ${counts.oa} OA, ${counts.interview} interview, ${counts.offer} offers, ${counts.rejected} rejected, ${counts.withdrawn} withdrawn.`;

    return (
        <div className="mt-5" role="img" aria-label={ariaSummary}>
            <div className="grid min-h-[230px] grid-cols-7 items-end gap-3 rounded-2xl border border-[#E7D7B7] bg-[#FFF7E5]/72 p-4 sm:gap-5 sm:p-6">
                {bars.map((bar) => {
                    const height = `${Math.max(10, Math.round((bar.value / max) * 100))}%`;
                    return (
                        <div key={bar.key} className="flex h-[180px] min-w-0 flex-col items-center justify-end gap-2">
                            <div className="text-sm font-black text-[#1F281B]">{bar.value}</div>
                            <div className="flex h-full w-full max-w-[72px] items-end rounded-t-2xl bg-[#EFE5C9]">
                                <div
                                    className="w-full rounded-t-2xl shadow-[0_8px_18px_rgba(70,45,16,0.08)] transition-all"
                                    style={{ height, backgroundColor: bar.color }}
                                />
                            </div>
                            <div className="w-full truncate text-center text-[11px] font-bold text-[#5F665C] sm:text-xs">{bar.label}</div>
                        </div>
                    );
                })}
            </div>
            <div className="mt-4 grid gap-3 rounded-2xl border border-[#E7D7B7] bg-[#FFF9EC] p-4 sm:grid-cols-3">
                <div>
                    <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#7B7F70]">All tracked</p>
                    <p className="mt-1 font-serif text-3xl font-bold text-[#1F281B]">{total}</p>
                </div>
                <div>
                    <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#7B7F70]">Applied pipeline</p>
                    <p className="mt-1 font-serif text-3xl font-bold text-[#1F281B]">{appliedTotal}</p>
                </div>
                <div>
                    <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#7B7F70]">Offer rate</p>
                    <p className="mt-1 font-serif text-3xl font-bold text-[#1F281B]">{percent(counts.offer, appliedTotal)}</p>
                </div>
            </div>
        </div>
    );
}

function ApplicationStatusCard({ counts }: { counts: PipelineCounts }) {
    const [range, setRange] = useState("This week");
    const appliedTotal = getAppliedTotal(counts);
    const inProgress = activeStages.reduce((total, stage) => total + counts[stage], 0);
    const summaryItems = [
        { label: "Total applied", value: String(appliedTotal), icon: ClipboardCheck },
        { label: "In progress", value: `${inProgress} (${percent(inProgress, appliedTotal)})`, icon: Target },
        { label: "Converted to offer", value: `${counts.offer} (${percent(counts.offer, appliedTotal)})`, icon: Trophy },
        { label: "Rejected", value: `${counts.rejected} (${percent(counts.rejected, appliedTotal)})`, icon: Bell },
        { label: "Withdrawn", value: `${counts.withdrawn} (${percent(counts.withdrawn, appliedTotal)})`, icon: Compass },
    ];

    return (
        <section className="relative mt-6 rounded-2xl border border-[#E7D7B7] bg-[#FFF9EC] px-5 py-6 shadow-[0_10px_24px_rgba(70,45,16,0.08)] [background-image:linear-gradient(rgba(255,249,236,0.84),rgba(255,249,236,0.84)),url('/nori-assets/paper-texture.png')] [background-size:cover] sm:px-8 sm:py-7">
            <Pin className="left-1/2 top-[-8px] -translate-x-1/2" />
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <h2 className="font-serif text-[26px] font-bold tracking-[-0.035em] text-[#1F281B]">Application status</h2>
                <button
                    type="button"
                    aria-label="Change date range"
                    onClick={() => setRange((current) => (current === "This week" ? "All saved" : "This week"))}
                    className="inline-flex min-h-[42px] items-center justify-center gap-2 rounded-[10px] border border-[#D8C9A7] bg-[#FFF9EC] px-4 text-sm font-semibold text-[#1F281B] transition hover:bg-[#EEF1DD] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#526736]"
                >
                    <Calendar className="h-4 w-4 text-[#526736]" />
                    {range}
                    <ChevronDown className="h-4 w-4" />
                </button>
            </div>

            <StageBarChart counts={counts} />

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
    const [trackedRoles, setTrackedRoles] = useState<TrackedRole[]>([]);

    useEffect(() => {
        try {
            const parsed = JSON.parse(localStorage.getItem("jobclaw_saved") || "[]") as TrackedRole[];
            setTrackedRoles(Array.isArray(parsed) ? parsed : []);
        } catch {
            setTrackedRoles([]);
        }
    }, []);

    const counts = useMemo(
        () =>
            trackedRoles.reduce<PipelineCounts>((acc, role) => {
                const status = (role.status || "saved").toLowerCase();
                if (status in acc) acc[status as keyof PipelineCounts] += 1;
                else acc.saved += 1;
                return acc;
            }, { ...emptyPipeline }),
        [trackedRoles],
    );
    const appliedTotal = getAppliedTotal(counts);

    return (
        <div className="min-h-screen bg-[#FFF3D6] text-[#1F281B] [background-image:radial-gradient(circle_at_8%_8%,rgba(146,189,179,0.25),transparent_32%),radial-gradient(circle_at_96%_4%,rgba(255,211,130,0.26),transparent_30%),linear-gradient(rgba(255,243,214,0.80),rgba(255,243,214,0.80)),url('/nori-assets/desk-paper-texture.png')] [background-size:auto,auto,auto,520px]">
            <NoriAppSidebar />
            <ProfileHeader />

            <main className="px-5 py-8 sm:px-8 lg:ml-[280px] lg:px-11">
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
                    <MetricCards appliedTotal={appliedTotal} />
                    <ApplicationStatusCard counts={counts} />
                </div>
            </main>
        </div>
    );
}
