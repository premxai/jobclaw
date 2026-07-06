"use client";
import { useEffect, useRef, useState } from "react";
import { Radio } from "lucide-react";

interface NewJobEvent {
    type: string;
    data?: {
        title?: string;
        company?: string;
    };
}

interface Toast {
    id: number;
    title: string;
    company: string;
}

const DEFAULT_WS_URL = "wss://api.norinote.xyz/ws/jobs";

function resolveWsUrl(): string {
    const configured = (process.env.NEXT_PUBLIC_WS_URL || "").trim();
    if (configured) return configured;

    const apiUrl = (process.env.NEXT_PUBLIC_API_URL || "").trim().replace(/\/$/, "");
    if (apiUrl.startsWith("https://")) {
        return `${apiUrl.replace(/^https:\/\//, "wss://")}/ws/jobs`;
    }
    return DEFAULT_WS_URL;
}

const PING_INTERVAL_MS = 30_000;
const TOAST_LIFETIME_MS = 6_000;
const RECONNECT_BASE_MS = 2_000;
const RECONNECT_MAX_MS = 30_000;

export default function LiveJobFeed() {
    const [connected, setConnected] = useState(false);
    const [liveCount, setLiveCount] = useState(0);
    const [toasts, setToasts] = useState<Toast[]>([]);
    const nextToastId = useRef(0);
    const reconnectDelay = useRef(RECONNECT_BASE_MS);

    useEffect(() => {
        let socket: WebSocket | null = null;
        let pingTimer: ReturnType<typeof setInterval> | null = null;
        let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
        let cancelled = false;

        const connect = () => {
            if (cancelled) return;

            // No API key is threaded into this URL on purpose — see the security
            // note in the redesign plan. JOBCLAW_API_KEY also unlocks /applications
            // writes, /scraper/trigger, and /admin/dedup, so putting it in a
            // browser-visible WS query string would be a real secret exposure, not
            // just a minor scope issue. Production today runs with no key set, so
            // /ws/jobs is already unauthenticated in practice — this connects for
            // that reality. If JOBCLAW_API_KEY is ever configured in production, a
            // separate low-privilege token (e.g. JOBCLAW_WS_PUBLIC_TOKEN, checked
            // only by the /ws/jobs handler) would be needed before this could
            // safely carry a token — that's a backend change, out of scope here.
            socket = new WebSocket(resolveWsUrl());

            socket.onopen = () => {
                if (cancelled) return;
                setConnected(true);
                reconnectDelay.current = RECONNECT_BASE_MS;
                pingTimer = setInterval(() => {
                    if (socket?.readyState === WebSocket.OPEN) socket.send("ping");
                }, PING_INTERVAL_MS);
            };

            socket.onmessage = (event) => {
                if (event.data === "pong") return;
                let parsed: NewJobEvent;
                try {
                    parsed = JSON.parse(event.data);
                } catch {
                    return;
                }
                if (parsed.type !== "new_job" || !parsed.data) return;

                setLiveCount((n) => n + 1);
                const id = nextToastId.current++;
                setToasts((prev) => [...prev, { id, title: parsed.data!.title || "New role", company: parsed.data!.company || "" }]);
                setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), TOAST_LIFETIME_MS);
            };

            const scheduleReconnect = () => {
                if (cancelled) return;
                setConnected(false);
                if (pingTimer) clearInterval(pingTimer);
                reconnectTimer = setTimeout(connect, reconnectDelay.current);
                reconnectDelay.current = Math.min(reconnectDelay.current * 2, RECONNECT_MAX_MS);
            };

            socket.onclose = scheduleReconnect;
            socket.onerror = () => socket?.close();
        };

        connect();

        return () => {
            cancelled = true;
            if (pingTimer) clearInterval(pingTimer);
            if (reconnectTimer) clearTimeout(reconnectTimer);
            socket?.close();
        };
    }, []);

    return (
        <>
            <div className="flex items-center gap-1.5 text-xs font-medium text-text-secondary" title={connected ? "Live job feed connected" : "Reconnecting…"}>
                <Radio className={`h-3.5 w-3.5 ${connected ? "text-success" : "text-text-secondary"}`} />
                {liveCount > 0 && <span className="text-text-primary">{liveCount}</span>}
            </div>

            {toasts.length > 0 && (
                <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
                    {toasts.map((t) => (
                        <div key={t.id} className="animate-slide-up rounded-xl border border-border bg-white px-4 py-3 shadow-popover">
                            <p className="text-xs font-semibold text-accent">New role just posted</p>
                            <p className="text-sm font-medium text-text-primary">{t.title}</p>
                            {t.company && <p className="text-xs text-text-secondary">{t.company}</p>}
                        </div>
                    ))}
                </div>
            )}
        </>
    );
}
