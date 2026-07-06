// Server-side proxy for the protected /resume/match backend endpoint.
//
// next.config.mjs's /api/:path* rewrite is a dumb passthrough — it can't
// attach a secret header the browser never had. /resume/match requires
// X-API-Key (api/auth.py PROTECTED_PREFIXES), so this Route Handler is the
// only place that ever sees JOBCLAW_API_KEY; it never reaches the browser.
import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
    let body: { resume_text?: string; top_k?: number };
    try {
        body = await req.json();
    } catch {
        return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
    }

    const resumeText = (body.resume_text || "").trim();
    if (!resumeText) {
        return NextResponse.json({ error: "resume_text is required" }, { status: 400 });
    }
    const topK = body.top_k ?? 20;

    const apiKey = process.env.JOBCLAW_API_KEY;
    if (!apiKey) {
        // Matches today's actual production state (docs/railway-web-api-setup.md
        // ships JOBCLAW_API_KEY blank) — tell the UI plainly instead of forcing
        // a round trip to the backend just to get back a 503.
        return NextResponse.json({ enabled: false }, { status: 200 });
    }

    const apiBase = (process.env.JOBCLAW_API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
    const sp = new URLSearchParams({ resume_text: resumeText, top_k: String(topK) });

    try {
        const res = await fetch(`${apiBase}/resume/match?${sp.toString()}`, {
            method: "POST",
            headers: { "X-API-Key": apiKey },
            cache: "no-store",
        });
        if (!res.ok) {
            const detail = await res.text().catch(() => "");
            return NextResponse.json({ enabled: true, error: detail || `API ${res.status}` }, { status: res.status });
        }
        const data = await res.json();
        return NextResponse.json({ enabled: true, ...data });
    } catch (e) {
        return NextResponse.json({ enabled: true, error: e instanceof Error ? e.message : "Request failed" }, { status: 502 });
    }
}
