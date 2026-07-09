"use client";

import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";
import { isSupabaseConfigured, supabaseAnonKey, supabaseUrl } from "./config";

let browserClient: SupabaseClient | null = null;

export function createBrowserSupabaseClient() {
    if (!isSupabaseConfigured) return null;
    browserClient ||= createBrowserClient(supabaseUrl, supabaseAnonKey);
    return browserClient;
}

