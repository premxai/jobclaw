"use client";

import { useEffect, useState } from "react";
import { createBrowserSupabaseClient } from "@/lib/supabase/browser";

export const ANONYMOUS_SAVED_JOBS_KEY = "jobclaw_saved";
export const ANONYMOUS_PROFILE_KEY = "nori_profile";

function getScopedStorageKey(prefix: string, anonymousKey: string, userId?: string | null) {
    return userId ? `${prefix}:${userId}` : anonymousKey;
}

function useUserScopedStorageKey(prefix: string, anonymousKey: string) {
    const [storageKey, setStorageKey] = useState(anonymousKey);

    useEffect(() => {
        const supabase = createBrowserSupabaseClient();
        if (!supabase) return;

        let active = true;
        supabase.auth.getUser().then(({ data }) => {
            if (active) setStorageKey(getScopedStorageKey(prefix, anonymousKey, data.user?.id));
        });

        const {
            data: { subscription },
        } = supabase.auth.onAuthStateChange((_event, session) => {
            setStorageKey(getScopedStorageKey(prefix, anonymousKey, session?.user?.id));
        });

        return () => {
            active = false;
            subscription.unsubscribe();
        };
    }, [anonymousKey, prefix]);

    return storageKey;
}

export function getSavedJobsStorageKey(userId?: string | null) {
    return getScopedStorageKey(ANONYMOUS_SAVED_JOBS_KEY, ANONYMOUS_SAVED_JOBS_KEY, userId);
}

export function useSavedJobsStorageKey() {
    return useUserScopedStorageKey(ANONYMOUS_SAVED_JOBS_KEY, ANONYMOUS_SAVED_JOBS_KEY);
}

export function useProfileStorageKey() {
    return useUserScopedStorageKey(ANONYMOUS_PROFILE_KEY, ANONYMOUS_PROFILE_KEY);
}
