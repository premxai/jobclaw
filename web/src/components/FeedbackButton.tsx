"use client";

import { useEffect, useState } from "react";
import { ImagePlus, MessageSquareText, Send, X } from "lucide-react";
import { createBrowserSupabaseClient } from "@/lib/supabase/browser";

const MAX_IMAGES = 4;

export default function FeedbackButton() {
    const [open, setOpen] = useState(false);
    const [message, setMessage] = useState("");
    const [email, setEmail] = useState("");
    const [accountEmail, setAccountEmail] = useState("");
    const [images, setImages] = useState<File[]>([]);
    const [status, setStatus] = useState("");
    const [sending, setSending] = useState(false);
    const supabase = createBrowserSupabaseClient();

    useEffect(() => {
        if (!supabase) return;
        supabase.auth.getUser().then(({ data }) => {
            if (!data.user?.email) return;
            setAccountEmail(data.user.email);
            setEmail(data.user.email);
        });
    }, [supabase]);

    const resetDraft = () => {
        setMessage("");
        setEmail(accountEmail);
        setImages([]);
        setStatus("");
        setSending(false);
    };

    const openFeedback = () => {
        resetDraft();
        setOpen(true);
    };

    const closeFeedback = () => {
        setOpen(false);
        resetDraft();
    };

    const addImages = (selectedFiles: FileList | null) => {
        if (!selectedFiles) return;
        setImages((current) => {
            const existingKeys = new Set(current.map((file) => `${file.name}-${file.size}-${file.lastModified}`));
            const next = [...current];
            Array.from(selectedFiles).forEach((file) => {
                const key = `${file.name}-${file.size}-${file.lastModified}`;
                if (next.length < MAX_IMAGES && file.type.startsWith("image/") && !existingKeys.has(key)) {
                    next.push(file);
                    existingKeys.add(key);
                }
            });
            return next;
        });
    };

    const removeImage = (index: number) => {
        setImages((current) => current.filter((_file, currentIndex) => currentIndex !== index));
    };

    const submit = async () => {
        setSending(true);
        setStatus("");
        const formData = new FormData();
        formData.set("message", message);
        formData.set("email", email);
        formData.set("page", window.location.href);
        images.forEach((image) => formData.append("images", image));

        const response = await fetch("/api/feedback", { method: "POST", body: formData });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            setStatus(data.error || "Could not send feedback.");
        } else {
            setStatus("Sent. Thank you for the note.");
            setMessage("");
            setImages([]);
        }
        setSending(false);
    };

    return (
        <>
            <button
                type="button"
                onClick={openFeedback}
                className="fixed bottom-5 right-5 z-40 inline-flex h-12 items-center gap-2 rounded-full border border-[#D8C9A7] bg-[#FFF9EC] px-5 text-sm font-bold text-[#123C24] shadow-[0_14px_32px_rgba(70,45,16,0.18)] transition hover:bg-[#EEF1DD]"
            >
                <MessageSquareText className="h-4 w-4" />
                Feedback
            </button>

            {open && (
                <div className="fixed inset-0 z-50 flex items-end justify-end bg-[#1F281B]/25 p-4 backdrop-blur-sm sm:p-6" onClick={closeFeedback}>
                    <section className="w-full max-w-md rounded-[24px] border border-[#E7D7B7] bg-[#FFF9EC] p-5 shadow-[0_24px_70px_rgba(44,30,12,0.24)]" onClick={(event) => event.stopPropagation()}>
                        <div className="mb-4 flex items-center justify-between">
                            <div>
                                <h2 className="font-serif text-2xl font-bold tracking-[-0.04em] text-[#12302A]">Send feedback</h2>
                                <p className="mt-1 text-sm font-medium text-[#5F665C]">Tell us what felt off. It goes straight to Prem.</p>
                            </div>
                            <button type="button" onClick={closeFeedback} className="grid h-9 w-9 place-items-center rounded-xl text-[#526736] hover:bg-[#EEF1DD]" aria-label="Close feedback">
                                <X className="h-5 w-5" />
                            </button>
                        </div>

                        <div className="grid gap-3">
                            <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" placeholder="Your email, optional" className="h-11 rounded-xl border border-[#D8C9A7] bg-white px-4 text-sm" />
                            <textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Write your message..." rows={5} className="resize-none rounded-xl border border-[#D8C9A7] bg-white px-4 py-3 text-sm" />
                            <label className="flex min-h-12 cursor-pointer items-center justify-between gap-3 rounded-xl border border-dashed border-[#D8C9A7] bg-white px-4 py-3 text-sm font-semibold text-[#526736] transition hover:bg-[#FFFDF8]">
                                <span className="inline-flex items-center gap-2">
                                    <ImagePlus className="h-4 w-4" />
                                    Add image
                                </span>
                                <span className="text-xs text-[#7B7F70]">{images.length}/{MAX_IMAGES}</span>
                                <input
                                    type="file"
                                    accept="image/*"
                                    multiple
                                    className="hidden"
                                    onChange={(event) => {
                                        addImages(event.target.files);
                                        event.target.value = "";
                                    }}
                                />
                            </label>
                            {images.length > 0 && (
                                <div className="grid gap-2 rounded-xl bg-white px-3 py-3">
                                    {images.map((image, index) => (
                                        <div key={`${image.name}-${image.size}-${image.lastModified}`} className="flex items-center justify-between gap-3 rounded-lg bg-[#FFF9EC] px-3 py-2 text-xs font-semibold text-[#5F665C]">
                                            <span className="min-w-0 truncate">{image.name}</span>
                                            <button type="button" onClick={() => removeImage(index)} className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-[#526736] hover:bg-[#EEF1DD]" aria-label={`Remove ${image.name}`}>
                                                <X className="h-4 w-4" />
                                            </button>
                                        </div>
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
