import { NextResponse, type NextRequest } from "next/server";
import nodemailer from "nodemailer";
import { createServerSupabaseClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

const MAX_IMAGES = 4;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_TOTAL_IMAGE_BYTES = 20 * 1024 * 1024;
const MAX_MESSAGE_LENGTH = 5_000;
const MAX_PAGE_LENGTH = 2_048;
const MAX_EMAIL_LENGTH = 254;
const RATE_LIMIT_WINDOW_MS = 10 * 60 * 1_000;
const RATE_LIMIT_MAX = 5;
const SMTP_TIMEOUT_MS = 15_000;
const rateLimit = new Map<string, { count: number; resetAt: number }>();

function escapeHtml(value: string) {
    return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char] || char);
}

function safeFileName(name: string) {
    return name.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "feedback-image";
}

export async function POST(request: NextRequest) {
    const now = Date.now();
    const forwardedFor = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
    const ipKey = forwardedFor || request.headers.get("x-real-ip") || "unknown";
    const currentLimit = rateLimit.get(ipKey);
    if (!currentLimit || currentLimit.resetAt <= now) {
        rateLimit.set(ipKey, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS });
    } else if (currentLimit.count >= RATE_LIMIT_MAX) {
        return NextResponse.json({ error: "Please wait a few minutes before sending more feedback." }, { status: 429 });
    } else {
        currentLimit.count += 1;
    }

    let formData: FormData;
    try {
        formData = await request.formData();
    } catch {
        return NextResponse.json({ error: "The feedback form could not be read." }, { status: 400 });
    }
    const message = String(formData.get("message") || "").trim();
    const senderEmail = String(formData.get("email") || "").trim();
    const page = String(formData.get("page") || "").trim();
    const images = formData.getAll("images").filter((item): item is File => item instanceof File && item.size > 0).slice(0, MAX_IMAGES);

    if (message.length < 3) {
        return NextResponse.json({ error: "Please write a short message first." }, { status: 400 });
    }
    if (message.length > MAX_MESSAGE_LENGTH || page.length > MAX_PAGE_LENGTH || senderEmail.length > MAX_EMAIL_LENGTH) {
        return NextResponse.json({ error: "Please shorten the feedback details and try again." }, { status: 400 });
    }
    if (senderEmail && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(senderEmail)) {
        return NextResponse.json({ error: "Please enter a valid email address." }, { status: 400 });
    }

    let totalImageBytes = 0;
    for (const image of images) {
        if (!image.type.startsWith("image/")) {
            return NextResponse.json({ error: "Only image uploads are supported." }, { status: 400 });
        }
        if (image.size > MAX_IMAGE_BYTES) {
            return NextResponse.json({ error: "Each image must be 5MB or less." }, { status: 400 });
        }
        totalImageBytes += image.size;
    }
    if (totalImageBytes > MAX_TOTAL_IMAGE_BYTES) {
        return NextResponse.json({ error: "Please keep all attachments under 20MB total." }, { status: 400 });
    }

    const supabase = createServerSupabaseClient();
    const userResult = supabase ? await supabase.auth.getUser() : null;
    const userEmail = userResult?.data.user?.email || "";
    const fromEmail = senderEmail || userEmail || "anonymous";

    const smtpUser = process.env.SMTP_USER || "";
    const smtpPassword = process.env.SMTP_PASSWORD || "";
    if (!smtpUser || !smtpPassword) {
        return NextResponse.json({ error: "Feedback email is not configured. Add SMTP_USER and SMTP_PASSWORD in deployment." }, { status: 503 });
    }

    const smtpPort = Number(process.env.SMTP_PORT || "465");
    const smtpSecure = process.env.SMTP_SECURE ? process.env.SMTP_SECURE === "1" : smtpPort === 465;
    const smtpHost = process.env.SMTP_HOST || "smtp.gmail.com";
    const to = process.env.FEEDBACK_TO_EMAIL || "kanaparthiprem03@gmail.com";
    const from = process.env.FEEDBACK_FROM_EMAIL || smtpUser;
    const attachments = await Promise.all(
        images.map(async (image) => ({
            filename: safeFileName(image.name),
            content: Buffer.from(await image.arrayBuffer()).toString("base64"),
        })),
    );

    const transporter = nodemailer.createTransport({
        host: smtpHost,
        port: smtpPort,
        secure: smtpSecure,
        auth: { user: smtpUser, pass: smtpPassword },
        connectionTimeout: SMTP_TIMEOUT_MS,
        greetingTimeout: SMTP_TIMEOUT_MS,
        socketTimeout: SMTP_TIMEOUT_MS,
    });
    try {
        await transporter.sendMail({
            from,
            to,
            replyTo: fromEmail === "anonymous" ? undefined : fromEmail,
            subject: "New Nori feedback",
            html: `
                <div style="font-family:Arial,sans-serif;line-height:1.6;color:#1f281b">
                    <h2>New Nori feedback</h2>
                    <p><strong>From:</strong> ${escapeHtml(fromEmail)}</p>
                    <p><strong>Page:</strong> ${escapeHtml(page || "unknown")}</p>
                    <p><strong>Images attached:</strong> ${attachments.length}</p>
                    <p><strong>Message:</strong></p>
                    <p>${escapeHtml(message).replace(/\n/g, "<br />")}</p>
                </div>
            `,
            attachments,
        });
    } catch (error) {
        console.error("[feedback] SMTP delivery failed", error instanceof Error ? error.message : error);
        return NextResponse.json({ error: "Could not send feedback email. Check the SMTP settings." }, { status: 502 });
    } finally {
        transporter.close();
    }

    return NextResponse.json({ ok: true });
}
