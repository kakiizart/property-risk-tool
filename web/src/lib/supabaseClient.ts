/**
 * Supabase browser client (auth only).
 *
 * Auth is optional: if NEXT_PUBLIC_SUPABASE_URL / _ANON_KEY are not set, the app
 * still runs — public report lookups work and the saved-report features hide
 * themselves. This keeps local dev and the wiring-ready build working before a
 * Supabase project exists.
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

/** True when Supabase auth is configured for this build. */
export const isAuthEnabled = Boolean(supabaseUrl && supabaseAnonKey);

export const supabase: SupabaseClient | null = isAuthEnabled
  ? createClient(supabaseUrl as string, supabaseAnonKey as string, {
      auth: { persistSession: true, autoRefreshToken: true },
    })
  : null;
