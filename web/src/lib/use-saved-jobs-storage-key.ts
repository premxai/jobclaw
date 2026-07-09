"use client";

import { useEffect, useState } from "react";
import { createBrowserSupabaseClient } from "@/lib/supabase/browser";

export const ANONYMOUS_SAVED_JOBS_KEY = "jobclaw_saved";

export function getSavedJobsStorageKey(userId?: string | null) {
    return userId ? `${ANONYMOUS_SAVED_JOBS_KEY}:${userId}` : ANONYMOUS_SAVED_JOBS_KEY;
}

export function useSavedJobsStorageKey() {
    const [storageKey, setStorageKey] = useState(ANONYMOUS_SAVED_JOBS_KEY);

    useEffect(() => {
        const supabase = createBrowserSupabaseClient();
        if (!supabase) return;

        let active = true;
        supabase.auth.getUser().then(({ data }) => {
            if (active) setStorageKey(getSavedJobsStorageKey(data.user?.id));
        });

        const {
            data: { subscription },
        } = supabase.auth.onAuthStateChange((_event, session) => {
            setStorageKey(getSavedJobsStorageKey(session?.user?.id));
        });

        return () => {
            active = false;
            subscription.unsubscribe();
        };
    }, []);

    return storageKey;
}

