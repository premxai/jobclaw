"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { User } from "@supabase/supabase-js";
import { ChevronDown, LogOut, UserCircle } from "lucide-react";
import { createBrowserSupabaseClient } from "@/lib/supabase/browser";

function initialsFor(user: User | null) {
    const source = String(user?.user_metadata?.full_name || user?.email || "Guest");
    return source
        .split(/[\s@._-]+/)
        .filter(Boolean)
        .map((part) => part[0])
        .join("")
        .slice(0, 2)
        .toUpperCase();
}

export default function UserMenu() {
    const [open, setOpen] = useState(false);
    const [user, setUser] = useState<User | null>(null);
    const router = useRouter();
    const supabase = createBrowserSupabaseClient();
    const initials = useMemo(() => initialsFor(user), [user]);
    const displayName = user?.user_metadata?.full_name || user?.email?.split("@")[0] || "Guest";

    useEffect(() => {
        if (!supabase) return;
        supabase.auth.getUser().then(({ data }) => setUser(data.user));
        const {
            data: { subscription },
        } = supabase.auth.onAuthStateChange((_event, session) => setUser(session?.user ?? null));
        return () => subscription.unsubscribe();
    }, [supabase]);

    const signOut = async () => {
        const result = await supabase?.auth.signOut();
        if (result?.error) return;
        window.sessionStorage.removeItem("nori_pending_apply");
        setUser(null);
        setOpen(false);
        router.replace("/");
    };

    return (
        <div className="relative order-2 block sm:order-3">
            <button type="button" onClick={() => setOpen((value) => !value)} className="flex items-center gap-3" aria-expanded={open} aria-haspopup="menu">
                <span className="grid h-12 w-12 place-items-center rounded-full bg-[#D9B08C] text-sm font-black text-[#1F281B] shadow-sm">{initials}</span>
                <span className="hidden leading-tight sm:block">
                    <span className="block text-[15px] font-bold text-[#1F281B]">{displayName}</span>
                </span>
                <ChevronDown className={`h-4 w-4 text-[#526736] transition ${open ? "rotate-180" : ""}`} />
            </button>
            {open && (
                <div role="menu" className="absolute right-0 top-[calc(100%+14px)] w-48 rounded-2xl border border-[#E7D7B7] bg-[#FFF9EC] p-2 shadow-[0_18px_42px_rgba(70,45,16,0.16)]">
                    <Link href="/profile" role="menuitem" className="flex h-10 items-center gap-2 rounded-xl px-3 text-sm font-semibold text-[#1F281B] hover:bg-[#F7EED7]">
                        <UserCircle className="h-4 w-4 text-[#526736]" />
                        Profile
                    </Link>
                    {user ? (
                        <button type="button" onClick={signOut} role="menuitem" className="flex h-10 w-full items-center gap-2 rounded-xl px-3 text-left text-sm font-semibold text-[#1F281B] hover:bg-[#F7EED7]">
                            <LogOut className="h-4 w-4 text-[#526736]" />
                            Logout
                        </button>
                    ) : (
                        <Link href="/login" role="menuitem" className="flex h-10 items-center gap-2 rounded-xl px-3 text-sm font-semibold text-[#1F281B] hover:bg-[#F7EED7]">
                            <LogOut className="h-4 w-4 text-[#526736]" />
                            Login
                        </Link>
                    )}
                </div>
            )}
        </div>
    );
}
