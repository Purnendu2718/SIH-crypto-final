/**
 * Supabase JS Client configuration.
 * Configured with default session persistence and auto-refresh as required in PROJECT.md:
 * "Session persistence: use the Supabase JS client's default behavior
 *  (persistSession: true, autoRefreshToken: true) — this alone satisfies
 *  'officer doesn't have to log in every time.'"
 */

import { createClient } from '@supabase/supabase-js';

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || 'https://placeholder-project.supabase.co';
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || 'placeholder-anon-key';

export const isSupabaseConfigured =
  !SUPABASE_URL.includes('placeholder') && !SUPABASE_ANON_KEY.includes('placeholder');

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});
