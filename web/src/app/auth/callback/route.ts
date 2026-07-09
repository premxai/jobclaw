import { NextResponse, type NextRequest } from "next/server";
import { createServerSupabaseClient } from "@/lib/supabase/server";

function safeNextPath(value: string | null, origin: string) {
    if (!value || !value.startsWith("/") || value.startsWith("//")) return "/jobs";
    try {
        const candidate = new URL(value, origin);
        if (candidate.origin !== origin) return "/jobs";
        return `${candidate.pathname}${candidate.search}${candidate.hash}`;
    } catch {
        return "/jobs";
    }
}

export async function GET(request: NextRequest) {
    const requestUrl = new URL(request.url);
    const code = requestUrl.searchParams.get("code");
    const next = safeNextPath(requestUrl.searchParams.get("next"), requestUrl.origin);
    const supabase = createServerSupabaseClient();

    if (code && supabase) {
        await supabase.auth.exchangeCodeForSession(code);
    }

    return NextResponse.redirect(new URL(next, requestUrl.origin));
}
