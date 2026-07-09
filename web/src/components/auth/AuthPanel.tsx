"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { User } from "@supabase/supabase-js";
import { LogOut, Mail, MapPin, ShieldCheck, Target, UserRound } from "lucide-react";
import { createBrowserSupabaseClient } from "@/lib/supabase/browser";
import { isSupabaseConfigured } from "@/lib/supabase/config";

type AuthMode = "login" | "signup";

export default function AuthPanel({
    initialMode = "login",
    redirectTo = "/jobs",
}: {
    initialMode?: AuthMode;
    redirectTo?: string;
}) {
    const router = useRouter();
    const [mode, setMode] = useState<AuthMode>(initialMode);
    const [name, setName] = useState("");
    const [role, setRole] = useState("");
    const [location, setLocation] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState("");
    const supabase = createBrowserSupabaseClient();

    useEffect(() => {
        const requestedMode = new URLSearchParams(window.location.search).get("mode");
        if (requestedMode === "signup") setMode("signup");
        if (requestedMode === "login") setMode("login");

        if (!supabase) return;
        supabase.auth.getUser().then(({ data }) => setUser(data.user));
        const {
            data: { subscription },
        } = supabase.auth.onAuthStateChange((_event, session) => setUser(session?.user ?? null));
        return () => subscription.unsubscribe();
    }, [initialMode, supabase]);

    const displayName = user?.user_metadata?.full_name || user?.email?.split("@")[0] || "Nori user";

    const submit = async () => {
        if (!supabase) return;
        setLoading(true);
        setMessage("");

        const result =
            mode === "signup"
                ? await supabase.auth.signUp({
                          email,
                          password,
                          options: {
                              data: {
                                  full_name: name.trim(),
                                  role: role.trim(),
                                  location: location.trim(),
                              },
                              emailRedirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(redirectTo)}`,
                      },
                  })
                : await supabase.auth.signInWithPassword({ email, password });

        if (result.error) setMessage(result.error.message);
        else if (mode === "signup" && !result.data.session) setMessage("Check your email to confirm your account.");
        else {
            if (mode === "signup") {
                localStorage.setItem(
                    "nori_profile",
                    JSON.stringify({
                        name: name.trim(),
                        role: role.trim(),
                        location: location.trim(),
                    }),
                );
            }
            setMessage("You are logged in.");
            router.push(redirectTo);
        }
        setLoading(false);
    };

    const signOut = async () => {
        if (!supabase) return;
        await supabase.auth.signOut();
        setUser(null);
        setMessage("Logged out.");
    };

    if (!isSupabaseConfigured) {
        return (
            <section className="rounded-[22px] border border-[#E7D7B7] bg-[#FFF9EC] p-5 shadow-[0_16px_36px_rgba(44,30,12,0.10)]">
                <h2 className="font-serif text-2xl font-bold text-[#12302A]">Auth setup needed</h2>
                <p className="mt-2 text-sm font-medium leading-6 text-[#5F665C]">
                    Add `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` to enable login, signup, and persistent sessions.
                </p>
            </section>
        );
    }

    if (user) {
        return (
            <section className="rounded-[16px] border border-[#E7D7B7] bg-[#FFF9EC] p-5 shadow-[0_10px_24px_rgba(44,30,12,0.07)]">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-center gap-4">
                        <span className="grid h-12 w-12 place-items-center rounded-full bg-[#EEF1DD] text-[#526736]">
                            <ShieldCheck className="h-6 w-6" />
                        </span>
                        <div>
                            <h2 className="font-serif text-2xl font-bold text-[#12302A]">Signed in as {displayName}</h2>
                            <p className="mt-1 flex items-center gap-2 text-sm font-medium text-[#5F665C]">
                                <Mail className="h-4 w-4" />
                                {user.email}
                            </p>
                        </div>
                    </div>
                    <button type="button" onClick={signOut} className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-[#D8C9A7] bg-white px-4 text-sm font-bold text-[#123C24] transition hover:bg-[#EEF1DD]">
                        <LogOut className="h-4 w-4" />
                        Logout
                    </button>
                </div>
            </section>
        );
    }

    return (
        <section className="rounded-[24px] border border-[#E7D7B7] bg-[#FFF9EC]/95 p-6 shadow-[0_24px_70px_rgba(44,30,12,0.18)] backdrop-blur">
            <div className="mb-5">
                <p className="text-xs font-black uppercase tracking-[0.2em] text-[#526736]">{mode === "login" ? "Welcome back" : "Create account"}</p>
                <h2 className="mt-2 font-serif text-[34px] font-bold leading-none tracking-[-0.05em] text-[#12302A]">
                    {mode === "login" ? "Login to Nori" : "Sign up for Nori"}
                </h2>
                <p className="mt-2 text-sm font-medium leading-6 text-[#5F665C]">
                    {mode === "login" ? "Use your email and password to open your board." : "Tell Nori the basics, then jump into your dashboard."}
                </p>
            </div>

            <div className="grid gap-3">
                {mode === "signup" && (
                    <>
                        <label className="relative">
                            <UserRound className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#526736]" />
                            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Name" className="h-12 w-full rounded-xl border border-[#D8C9A7] bg-white px-4 pl-11 text-sm font-medium" />
                        </label>
                        <label className="relative">
                            <Target className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#526736]" />
                            <input value={role} onChange={(event) => setRole(event.target.value)} placeholder="Role or desired role" className="h-12 w-full rounded-xl border border-[#D8C9A7] bg-white px-4 pl-11 text-sm font-medium" />
                        </label>
                        <label className="relative">
                            <MapPin className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#526736]" />
                            <input value={location} onChange={(event) => setLocation(event.target.value)} placeholder="Location" className="h-12 w-full rounded-xl border border-[#D8C9A7] bg-white px-4 pl-11 text-sm font-medium" />
                        </label>
                    </>
                )}
                <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" placeholder="Email" className="h-12 rounded-xl border border-[#D8C9A7] bg-white px-4 text-sm font-medium" />
                <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" placeholder="Password" className="h-12 rounded-xl border border-[#D8C9A7] bg-white px-4 text-sm font-medium" />
            </div>

            {message && <p className="mt-3 rounded-xl bg-white px-4 py-3 text-sm font-semibold text-[#526736]">{message}</p>}

            <div className="mt-5 grid gap-3">
                <button type="button" disabled={loading || !email || !password || (mode === "signup" && (!name || !role || !location))} onClick={submit} className="h-12 rounded-xl bg-[#123C24] px-5 text-sm font-bold text-white disabled:opacity-50">
                    {loading ? "Working..." : mode === "login" ? "Login" : "Create account"}
                </button>
            </div>

            <p className="mt-5 text-center text-sm font-semibold text-[#5F665C]">
                {mode === "login" ? "Don't have an account? " : "Already have an account? "}
                <Link href={mode === "login" ? "/signup" : "/login"} className="text-[#526736] underline underline-offset-4">
                    {mode === "login" ? "Sign up" : "Login"}
                </Link>
            </p>
        </section>
    );
}
