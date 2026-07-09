"use client";

import { useEffect, useState } from "react";
import type { User } from "@supabase/supabase-js";
import { LogOut, Mail, ShieldCheck } from "lucide-react";
import { createBrowserSupabaseClient } from "@/lib/supabase/browser";
import { isSupabaseConfigured } from "@/lib/supabase/config";

type AuthMode = "login" | "signup";

export default function AuthPanel() {
    const [mode, setMode] = useState<AuthMode>("login");
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState("");
    const supabase = createBrowserSupabaseClient();

    useEffect(() => {
        const requestedMode = new URLSearchParams(window.location.search).get("mode");
        if (requestedMode === "signup") setMode("signup");

        if (!supabase) return;
        supabase.auth.getUser().then(({ data }) => setUser(data.user));
        const {
            data: { subscription },
        } = supabase.auth.onAuthStateChange((_event, session) => setUser(session?.user ?? null));
        return () => subscription.unsubscribe();
    }, [supabase]);

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
                          data: { full_name: name.trim() },
                          emailRedirectTo: `${window.location.origin}/auth/callback?next=/profile`,
                      },
                  })
                : await supabase.auth.signInWithPassword({ email, password });

        if (result.error) setMessage(result.error.message);
        else setMessage(mode === "signup" ? "Check your email to confirm your account." : "You are logged in.");
        setLoading(false);
    };

    const signInWithGoogle = async () => {
        if (!supabase) return;
        await supabase.auth.signInWithOAuth({
            provider: "google",
            options: { redirectTo: `${window.location.origin}/auth/callback?next=/profile` },
        });
    };

    const signOut = async () => {
        if (!supabase) return;
        await supabase.auth.signOut();
        setUser(null);
        setMessage("Logged out.");
    };

    if (!isSupabaseConfigured) {
        return (
            <section className="rounded-[16px] border border-[#E7D7B7] bg-[#FFF9EC] p-5 shadow-[0_10px_24px_rgba(44,30,12,0.07)]">
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
        <section className="rounded-[16px] border border-[#E7D7B7] bg-[#FFF9EC] p-5 shadow-[0_10px_24px_rgba(44,30,12,0.07)]">
            <div className="mb-5 flex rounded-xl border border-[#E7D7B7] bg-white p-1">
                {(["login", "signup"] as AuthMode[]).map((option) => (
                    <button
                        key={option}
                        type="button"
                        onClick={() => setMode(option)}
                        className={`h-10 flex-1 rounded-lg text-sm font-bold capitalize transition ${mode === option ? "bg-[#526736] text-white" : "text-[#526736] hover:bg-[#EEF1DD]"}`}
                    >
                        {option === "login" ? "Login" : "Sign up"}
                    </button>
                ))}
            </div>

            <div className="grid gap-3">
                {mode === "signup" && <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Full name" className="h-12 rounded-xl border border-[#D8C9A7] bg-white px-4 text-sm" />}
                <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" placeholder="Email" className="h-12 rounded-xl border border-[#D8C9A7] bg-white px-4 text-sm" />
                <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" placeholder="Password" className="h-12 rounded-xl border border-[#D8C9A7] bg-white px-4 text-sm" />
            </div>

            {message && <p className="mt-3 rounded-xl bg-white px-4 py-3 text-sm font-semibold text-[#526736]">{message}</p>}

            <div className="mt-5 grid gap-3 sm:grid-cols-2">
                <button type="button" disabled={loading || !email || !password} onClick={submit} className="h-12 rounded-xl bg-[#123C24] px-5 text-sm font-bold text-white disabled:opacity-50">
                    {loading ? "Working..." : mode === "login" ? "Login" : "Create account"}
                </button>
                <button type="button" onClick={signInWithGoogle} className="h-12 rounded-xl border border-[#D8C9A7] bg-white px-5 text-sm font-bold text-[#123C24]">
                    Continue with Google
                </button>
            </div>
        </section>
    );
}

