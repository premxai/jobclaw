"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { ArrowRight, Bookmark, BriefcaseBusiness, Calendar, Edit3, FileText, MapPin, Target, Users, XCircle } from "lucide-react";
import NoriAppSidebar from "@/components/NoriAppSidebar";
import { createBrowserSupabaseClient } from "@/lib/supabase/browser";
import { useProfileStorageKey, useSavedJobsStorageKey } from "@/lib/use-saved-jobs-storage-key";

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
}

interface ProfileInfo {
    name: string;
    location: string;
    role: string;
}

const emptyPipeline: PipelineCounts = {
    saved: 0,
    applied: 0,
    oa: 0,
    interview: 0,
    offer: 0,
    rejected: 0,
};

const defaultProfile: ProfileInfo = {
    name: "Alex Chen",
    location: "San Francisco, CA",
    role: "Senior Product Designer",
};

function getAppliedTotal(counts: PipelineCounts) {
    return counts.applied + counts.oa + counts.interview + counts.offer + counts.rejected;
}

function percent(value: number, total: number) {
    if (total <= 0) return "0%";
    return `${Math.round((value / total) * 100)}%`;
}

function normalizeStatus(status?: string | null): keyof PipelineCounts {
    const value = (status || "saved").toLowerCase();
    if (value === "phone_screen" || value === "onsite") return "interview";
    if (value === "withdrawn") return "rejected";
    if (value in emptyPipeline) return value as keyof PipelineCounts;
    return "saved";
}

function ProfileAvatar({ profile }: { profile: ProfileInfo }) {
    const initials = profile.name
        .split(" ")
        .map((part) => part[0])
        .join("")
        .slice(0, 2)
        .toUpperCase();

    return (
        <div className="grid h-[104px] w-[104px] shrink-0 place-items-center rounded-full bg-[radial-gradient(circle_at_35%_25%,#8EA66C_0%,#496B2D_48%,#203D18_100%)] font-serif text-[34px] font-bold tracking-[-0.06em] text-[#FFF9EC] shadow-[inset_0_0_0_10px_rgba(238,241,221,0.82),0_12px_28px_rgba(47,74,29,0.18)] xl:h-[118px] xl:w-[118px] xl:text-[38px]">
            {initials || "AC"}
        </div>
    );
}

function EditProfileDialog({
    profile,
    onClose,
    onSave,
}: {
    profile: ProfileInfo;
    onClose: () => void;
    onSave: (profile: ProfileInfo) => void;
}) {
    const [draft, setDraft] = useState(profile);

    return (
        <div className="fixed inset-0 z-50 grid place-items-center bg-[#1F281B]/35 px-5 backdrop-blur-sm" onClick={onClose}>
            <form
                onSubmit={(event) => {
                    event.preventDefault();
                    onSave(draft);
                }}
                className="w-full max-w-lg rounded-[24px] border border-[#E7D7B7] bg-[#FFF9EC] p-6 shadow-[0_24px_60px_rgba(60,42,16,0.22)]"
                onClick={(event) => event.stopPropagation()}
            >
                <div className="mb-5 flex items-center justify-between gap-4">
                    <h2 className="font-serif text-3xl font-bold tracking-[-0.04em] text-[#12302A]">Edit profile</h2>
                    <button type="button" onClick={onClose} className="rounded-xl px-3 py-2 text-sm font-bold text-[#5F665C]">
                        Close
                    </button>
                </div>
                <div className="grid gap-3">
                    <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="Name" className="h-12 rounded-xl border border-[#D8C9A7] bg-white px-4 text-sm" />
                    <input value={draft.role} onChange={(event) => setDraft({ ...draft, role: event.target.value })} placeholder="Role or desired role" className="h-12 rounded-xl border border-[#D8C9A7] bg-white px-4 text-sm" />
                    <input value={draft.location} onChange={(event) => setDraft({ ...draft, location: event.target.value })} placeholder="Location" className="h-12 rounded-xl border border-[#D8C9A7] bg-white px-4 text-sm" />
                </div>
                <button type="submit" className="mt-5 h-12 rounded-xl bg-[#123C24] px-5 text-sm font-bold text-white">
                    Save profile
                </button>
            </form>
        </div>
    );
}

function MetricCards({ appliedTotal }: { appliedTotal: number }) {
    const dailyTarget = 25;
    const dailyProgress = Math.min(100, Math.round((appliedTotal / dailyTarget) * 100));

    return (
        <section className="mt-5 grid gap-5 xl:grid-cols-2">
            <article className="rounded-[16px] border border-[#E7D7B7] bg-white p-5 shadow-[0_10px_24px_rgba(44,30,12,0.07)] xl:p-6">
                <div className="flex items-start gap-5">
                    <span className="grid h-[74px] w-[74px] shrink-0 place-items-center rounded-full bg-[#EEF1DD] text-[#2F6B22] xl:h-[86px] xl:w-[86px]">
                        <Target className="h-8 w-8" />
                    </span>
                    <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-4">
                            <div>
                                <h2 className="font-serif text-[22px] font-bold tracking-[-0.035em] text-[#12302A]">Daily target</h2>
                                <p className="mt-1 text-sm font-medium text-[#5F665C]">Applications to keep momentum.</p>
                            </div>
                            <button type="button" className="grid h-10 w-10 place-items-center rounded-xl border border-[#D8C9A7] text-[#123C24]" aria-label="Edit daily target">
                                <Edit3 className="h-4 w-4" />
                            </button>
                        </div>
                        <div className="mt-4 flex items-end justify-between">
                            <p className="font-serif text-[38px] font-bold leading-none text-[#12302A]">
                                {appliedTotal}<span className="text-2xl text-[#1F281B]">/{dailyTarget}</span>
                            </p>
                            <p className="text-sm font-bold text-[#2F6B22]">{dailyProgress}%</p>
                        </div>
                        <div className="mt-4 h-3 overflow-hidden rounded-full bg-[#EFE8D6]">
                            <div className="h-full rounded-full bg-[#2F6B22]" style={{ width: `${dailyProgress}%` }} />
                        </div>
                    </div>
                </div>
            </article>

            <article className="rounded-[16px] border border-[#E7D7B7] bg-white p-5 shadow-[0_10px_24px_rgba(44,30,12,0.07)] xl:p-6">
                <div className="flex items-center gap-5">
                    <span className="grid h-[74px] w-[74px] shrink-0 place-items-center rounded-full bg-[#EEF1DD] text-[#2F6B22] xl:h-[86px] xl:w-[86px]">
                        <BriefcaseBusiness className="h-8 w-8" />
                    </span>
                    <div className="min-w-0 flex-1">
                        <h2 className="font-serif text-[22px] font-bold tracking-[-0.035em] text-[#12302A]">Jobs applied</h2>
                        <p className="mt-1 text-sm font-medium text-[#5F665C]">This week across saved roles and direct applies.</p>
                        <div className="mt-4 flex items-end justify-between gap-4">
                            <p className="font-serif text-[48px] font-bold leading-none tracking-[-0.045em] text-[#12302A]">{appliedTotal}</p>
                            <span className="mb-2 inline-flex items-center gap-2 rounded-xl bg-[#EEF1DD] px-4 py-2 text-sm font-bold text-[#2F6B22]">
                                <ArrowRight className="h-4 w-4 -rotate-45" />
                                +11%
                            </span>
                        </div>
                    </div>
                </div>
            </article>
        </section>
    );
}

function ApplicationStatusCard({ counts }: { counts: PipelineCounts }) {
    const appliedTotal = getAppliedTotal(counts);
    const max = Math.max(15, ...Object.values(counts));
    const bars = [
        { key: "saved", label: "Saved", value: counts.saved, color: "#486D26", icon: Bookmark },
        { key: "applied", label: "Applied", value: counts.applied, color: "#91B27F", icon: Target },
        { key: "oa", label: "OA", value: counts.oa, color: "#6EA0BF", icon: FileText },
        { key: "interview", label: "Interview", value: counts.interview, color: "#E8B42F", icon: Users },
        { key: "offer", label: "Offer", value: counts.offer, color: "#50B9A3", icon: ArrowRight },
        { key: "rejected", label: "Rejected", value: counts.rejected, color: "#E1644F", icon: XCircle },
    ];

    return (
        <section className="mt-5 rounded-[16px] border border-[#E7D7B7] bg-white p-5 shadow-[0_10px_24px_rgba(44,30,12,0.07)] xl:p-6">
            <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <h2 className="font-serif text-[24px] font-bold tracking-[-0.035em] text-[#12302A]">Application status</h2>
                <button type="button" className="inline-flex h-10 items-center gap-3 rounded-xl border border-[#E7D7B7] px-4 text-sm font-semibold text-[#1F281B]">
                    <Calendar className="h-4 w-4 text-[#123C24]" />
                    This week
                </button>
            </div>

            <div className="relative min-h-[190px] border-b border-[#B9B2A4] pl-9 xl:min-h-[220px]">
                {[15, 10, 5, 0].map((tick) => (
                    <div key={tick} className="absolute left-0 right-0 flex items-center gap-4" style={{ bottom: `${(tick / max) * 100}%` }}>
                        <span className="w-7 text-sm text-[#5F665C]">{tick}</span>
                        <span className="h-px flex-1 border-t border-dashed border-[#E1D8C8]" />
                    </div>
                ))}
                <div className="absolute inset-x-8 bottom-0 grid h-full grid-cols-6 items-end gap-4 xl:gap-7">
                    {bars.map((bar) => (
                        <div key={bar.key} className="relative z-10 flex min-w-0 flex-col items-center gap-2">
                            <p className="font-serif text-xl font-bold text-[#1F281B]">{bar.value}</p>
                            <div className="w-full max-w-[76px] rounded-t-md shadow-[0_10px_18px_rgba(44,30,12,0.12)]" style={{ height: `${Math.max(10, Math.round((bar.value / max) * 100))}%`, minHeight: 12, backgroundColor: bar.color }} />
                            <p className="text-sm font-medium text-[#5F665C]">{bar.label}</p>
                        </div>
                    ))}
                </div>
            </div>

            <div className="mt-4 grid rounded-2xl border border-[#E7D7B7] bg-[#FFFDF8] sm:grid-cols-3 xl:grid-cols-6">
                {bars.map(({ key, label, value, icon: Icon }, index) => (
                    <div key={key} className={`flex items-center gap-2.5 px-4 py-3 ${index > 0 ? "border-t border-[#E7D7B7] sm:border-l sm:border-t-0" : ""}`}>
                        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#EEF1DD] text-[#2F6B22]">
                            <Icon className="h-4 w-4" />
                        </span>
                        <div>
                            <p className="text-xs font-medium text-[#5F665C]">{label === "Saved" ? "Total saved" : label}</p>
                            <p className="font-serif text-lg font-bold text-[#1F281B]">
                                {value}
                                {key !== "saved" ? ` (${percent(value, appliedTotal)})` : ""}
                            </p>
                        </div>
                    </div>
                ))}
            </div>
        </section>
    );
}

export default function ProfilePage() {
    const [trackedRoles, setTrackedRoles] = useState<TrackedRole[]>([]);
    const [profile, setProfile] = useState<ProfileInfo>(defaultProfile);
    const [editingProfile, setEditingProfile] = useState(false);
    const supabase = createBrowserSupabaseClient();
    const savedJobsStorageKey = useSavedJobsStorageKey();
    const profileStorageKey = useProfileStorageKey();

    useEffect(() => {
        try {
            const parsed = JSON.parse(localStorage.getItem(savedJobsStorageKey) || "[]") as TrackedRole[];
            setTrackedRoles(Array.isArray(parsed) ? parsed : []);
        } catch {
            setTrackedRoles([]);
        }
    }, [savedJobsStorageKey]);

    useEffect(() => {
        try {
            const savedProfile = JSON.parse(localStorage.getItem(profileStorageKey) || "null") as ProfileInfo | null;
            if (savedProfile) setProfile({ ...defaultProfile, ...savedProfile });
        } catch {}

        if (!supabase) return;
        supabase.auth.getUser().then(({ data }) => {
            if (!data.user) return;
            const metadata = data.user.user_metadata || {};
            setProfile((current) => ({
                ...current,
                name: metadata.full_name || data.user.email?.split("@")[0] || current.name,
                role: metadata.role || current.role,
                location: metadata.location || current.location,
            }));
        });
        const {
            data: { subscription },
        } = supabase.auth.onAuthStateChange((_event, session) => {
            if (!session?.user) return;
            const metadata = session.user.user_metadata || {};
            setProfile((current) => ({
                ...current,
                name: metadata.full_name || session.user.email?.split("@")[0] || current.name,
                role: metadata.role || current.role,
                location: metadata.location || current.location,
            }));
        });
        return () => subscription.unsubscribe();
    }, [profileStorageKey, supabase]);

    const counts = useMemo(
        () =>
            trackedRoles.reduce<PipelineCounts>((acc, role) => {
                acc[normalizeStatus(role.status)] += 1;
                return acc;
            }, { ...emptyPipeline }),
        [trackedRoles],
    );
    const appliedTotal = getAppliedTotal(counts);

    return (
        <div className="min-h-screen bg-[#FAF6EF] text-[#1F281B]">
            {editingProfile && (
                <EditProfileDialog
                    profile={profile}
                    onClose={() => setEditingProfile(false)}
                    onSave={(updatedProfile) => {
                        const cleanProfile = {
                            ...defaultProfile,
                            ...updatedProfile,
                            name: updatedProfile.name.trim() || defaultProfile.name,
                            location: updatedProfile.location.trim() || defaultProfile.location,
                            role: updatedProfile.role.trim() || defaultProfile.role,
                        };
                        setProfile(cleanProfile);
                        localStorage.setItem(profileStorageKey, JSON.stringify(cleanProfile));
                        void supabase?.auth.updateUser({
                            data: {
                                full_name: cleanProfile.name,
                                role: cleanProfile.role,
                                location: cleanProfile.location,
                            },
                        });
                        setEditingProfile(false);
                    }}
                />
            )}
            <NoriAppSidebar />

            <main className="px-5 py-7 sm:px-8 lg:ml-[280px] lg:px-9 xl:px-10">
                <div className="mx-auto max-w-[1400px]">
                    <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                        <div>
                            <p className="mb-2 text-xs font-black uppercase tracking-[0.26em] text-[#2F6B22]">Profile Dashboard</p>
                            <h1 className="font-serif text-[42px] font-bold leading-none tracking-[-0.05em] text-[#12302A] sm:text-[52px]">My Profile</h1>
                        </div>
                        <Link href="/jobs" className="inline-flex h-12 items-center justify-center gap-3 rounded-xl bg-[#123C24] px-6 text-base font-semibold text-white shadow-[0_14px_30px_rgba(18,60,36,0.22)] transition hover:bg-[#0F2F1E]">
                            Browse jobs
                            <ArrowRight className="h-5 w-5" />
                        </Link>
                    </div>

                    <section className="relative overflow-hidden rounded-[16px] border border-[#E7D7B7] bg-white p-6 shadow-[0_10px_24px_rgba(44,30,12,0.07)] sm:p-7">
                        <div className="relative flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
                            <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
                                <ProfileAvatar profile={profile} />
                                <div>
                                    <h2 className="font-serif text-[36px] font-bold leading-none tracking-[-0.045em] text-[#12302A] xl:text-[40px]">{profile.name}</h2>
                                    <p className="mt-3 text-lg font-medium text-[#1F281B]">{profile.role}</p>
                                    <p className="mt-2 inline-flex items-center gap-2 text-base font-medium text-[#5F665C]">
                                        <MapPin className="h-5 w-5" />
                                        {profile.location}
                                    </p>
                                </div>
                            </div>
                            <div className="relative z-10 flex flex-col items-end gap-3">
                                <button type="button" onClick={() => setEditingProfile(true)} className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-[#D8C9A7] bg-white px-4 text-sm font-bold text-[#123C24] transition hover:bg-[#EEF1DD]">
                                    <Edit3 className="h-4 w-4" />
                                    Edit profile
                                </button>
                                <span className="pointer-events-none relative hidden h-20 w-24 opacity-45 sm:block">
                                    <Image src="/nori-assets/dried-flowers.png" alt="" aria-hidden="true" fill sizes="96px" className="object-contain object-right-top" />
                                </span>
                            </div>
                        </div>
                    </section>

                    <MetricCards appliedTotal={appliedTotal} />
                    <ApplicationStatusCard counts={counts} />
                </div>
            </main>
        </div>
    );
}
