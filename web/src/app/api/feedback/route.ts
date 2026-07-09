import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { createServerSupabaseClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

const MAX_IMAGES = 4;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

function escapeHtml(value: string) {
    return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char] || char);
}

function safeFileName(name: string) {
    return name.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "feedback-image";
}

export async function POST(request: NextRequest) {
    const formData = await request.formData();
    const message = String(formData.get("message") || "").trim();
    const senderEmail = String(formData.get("email") || "").trim();
    const page = String(formData.get("page") || "").trim();
    const files = formData.getAll("images").filter((item): item is File => item instanceof File && item.size > 0).slice(0, MAX_IMAGES);

    if (message.length < 3) {
        return NextResponse.json({ error: "Please write a short message first." }, { status: 400 });
    }

    for (const file of files) {
        if (!file.type.startsWith("image/")) return NextResponse.json({ error: "Only image uploads are supported." }, { status: 400 });
        if (file.size > MAX_IMAGE_BYTES) return NextResponse.json({ error: "Each image must be 5MB or less." }, { status: 400 });
    }

    const supabase = createServerSupabaseClient();
    const userResult = supabase ? await supabase.auth.getUser() : null;
    const userEmail = userResult?.data.user?.email || "";
    const fromEmail = senderEmail || userEmail || "anonymous";

    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
    const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY || "";
    const bucket = process.env.SUPABASE_FEEDBACK_BUCKET || "feedback";
    const uploadedUrls: string[] = [];
    const attachments = [];

    if (supabaseUrl && serviceRoleKey && files.length > 0) {
        const admin = createClient(supabaseUrl, serviceRoleKey, { auth: { persistSession: false } });
        for (const file of files) {
            const storagePath = `feedback/${new Date().toISOString().slice(0, 10)}/${crypto.randomUUID()}-${safeFileName(file.name)}`;
            const upload = await admin.storage.from(bucket).upload(storagePath, file, {
                contentType: file.type,
                upsert: false,
            });
            if (!upload.error) {
                const signed = await admin.storage.from(bucket).createSignedUrl(storagePath, 60 * 60 * 24 * 7);
                if (signed.data?.signedUrl) uploadedUrls.push(signed.data.signedUrl);
            }
        }
    }

    for (const file of files) {
        const buffer = Buffer.from(await file.arrayBuffer());
        attachments.push({
            filename: safeFileName(file.name),
            content: buffer.toString("base64"),
            content_type: file.type,
        });
    }

    const resendApiKey = process.env.RESEND_API_KEY || "";
    if (!resendApiKey) {
        return NextResponse.json({ error: "Feedback email is not configured. Add RESEND_API_KEY in deployment." }, { status: 503 });
    }

    const to = process.env.FEEDBACK_TO_EMAIL || "kanaparthiprem03@gmail.com";
    const from = process.env.FEEDBACK_FROM_EMAIL || "Nori Feedback <feedback@norinote.xyz>";
    const imageLinks = uploadedUrls.length
        ? `<p><strong>Stored images:</strong></p><ul>${uploadedUrls.map((url) => `<li><a href="${escapeHtml(url)}">${escapeHtml(url)}</a></li>`).join("")}</ul>`
        : "";

    const response = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
            Authorization: `Bearer ${resendApiKey}`,
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            from,
            to,
            subject: "New Nori feedback",
            html: `
                <div style="font-family:Arial,sans-serif;line-height:1.6;color:#1f281b">
                    <h2>New Nori feedback</h2>
                    <p><strong>From:</strong> ${escapeHtml(fromEmail)}</p>
                    <p><strong>Page:</strong> ${escapeHtml(page || "unknown")}</p>
                    <p><strong>Message:</strong></p>
                    <p>${escapeHtml(message).replace(/\n/g, "<br />")}</p>
                    ${imageLinks}
                </div>
            `,
            attachments,
        }),
    });

    if (!response.ok) {
        const detail = await response.text();
        return NextResponse.json({ error: "Could not send feedback email.", detail }, { status: 502 });
    }

    return NextResponse.json({ ok: true });
}

