"use client";

import { useEffect, useState } from "react";
import { ImagePlus, MessageSquareText, Send, X } from "lucide-react";
import { createBrowserSupabaseClient } from "@/lib/supabase/browser";

export default function FeedbackButton() {
    const [open, setOpen] = useState(false);
    const [message, setMessage] = useState("");
    const [email, setEmail] = useState("");
    const [files, setFiles] = useState<File[]>([]);
    const [status, setStatus] = useState("");
    const [sending, setSending] = useState(false);
    const supabase = createBrowserSupabaseClient();

    useEffect(() => {
        if (!supabase) return;
        supabase.auth.getUser().then(({ data }) => {
            if (data.user?.email) setEmail(data.user.email);
        });
    }, [supabase]);

    const submit = async () => {
        setSending(true);
        setStatus("");
        const formData = new FormData();
        formData.set("message", message);
        formData.set("email", email);
        formData.set("page", window.location.href);
        files.forEach((file) => formData.append("images", file));

        const response = await fetch("/api/feedback", { method: "POST", body: formData });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            setStatus(data.error || "Could not send feedback.");
        } else {
            setStatus("Sent. Thank you for the note.");
            setMessage("");
            setFiles([]);
        }
        setSending(false);
    };

    return (
        <>
            <button
                type="button"
                onClick={() => setOpen(true)}
                className="fixed bottom-5 right-5 z-40 inline-flex h-12 items-center gap-2 rounded-full border border-[#D8C9A7] bg-[#FFF9EC] px-5 text-sm font-bold text-[#123C24] shadow-[0_14px_32px_rgba(70,45,16,0.18)] transition hover:bg-[#EEF1DD]"
            >
                <MessageSquareText className="h-4 w-4" />
                Feedback
            </button>

            {open && (
                <div className="fixed inset-0 z-50 flex items-end justify-end bg-[#1F281B]/25 p-4 backdrop-blur-sm sm:p-6" onClick={() => setOpen(false)}>
                    <section className="w-full max-w-md rounded-[24px] border border-[#E7D7B7] bg-[#FFF9EC] p-5 shadow-[0_24px_70px_rgba(44,30,12,0.24)]" onClick={(event) => event.stopPropagation()}>
                        <div className="mb-4 flex items-center justify-between">
                            <div>
                                <h2 className="font-serif text-2xl font-bold tracking-[-0.04em] text-[#12302A]">Send feedback</h2>
                                <p className="mt-1 text-sm font-medium text-[#5F665C]">Tell us what felt off. Screenshots help.</p>
                            </div>
                            <button type="button" onClick={() => setOpen(false)} className="grid h-9 w-9 place-items-center rounded-xl text-[#526736] hover:bg-[#EEF1DD]" aria-label="Close feedback">
                                <X className="h-5 w-5" />
                            </button>
                        </div>

                        <div className="grid gap-3">
                            <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" placeholder="Your email, optional" className="h-11 rounded-xl border border-[#D8C9A7] bg-white px-4 text-sm" />
                            <textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Write your message..." rows={5} className="resize-none rounded-xl border border-[#D8C9A7] bg-white px-4 py-3 text-sm" />
                            <label className="flex min-h-12 cursor-pointer items-center justify-between gap-3 rounded-xl border border-dashed border-[#D8C9A7] bg-white px-4 py-3 text-sm font-semibold text-[#526736]">
                                <span className="inline-flex items-center gap-2">
                                    <ImagePlus className="h-4 w-4" />
                                    Add images
                                </span>
                                <span className="text-xs text-[#7B7F70]">{files.length}/4</span>
                                <input
                                    type="file"
                                    accept="image/*"
                                    multiple
                                    className="hidden"
                                    onChange={(event) => setFiles(Array.from(event.target.files || []).slice(0, 4))}
                                />
                            </label>
                            {files.length > 0 && (
                                <div className="rounded-xl bg-white px-4 py-3 text-xs font-semibold text-[#5F665C]">
                                    {files.map((file) => (
                                        <p key={`${file.name}-${file.size}`} className="truncate">
                                            {file.name}
                                        </p>
                                    ))}
                                </div>
                            )}
                        </div>

                        {status && <p className="mt-3 rounded-xl bg-white px-4 py-3 text-sm font-semibold text-[#526736]">{status}</p>}

                        <button type="button" disabled={sending || message.trim().length < 3} onClick={submit} className="mt-4 inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-[#526736] px-5 text-sm font-bold text-white transition hover:bg-[#43552C] disabled:opacity-50">
                            <Send className="h-4 w-4" />
                            {sending ? "Sending..." : "Send feedback"}
                        </button>
                    </section>
                </div>
            )}
        </>
    );
}

