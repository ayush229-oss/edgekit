/**
 * Server-side Supabase client.
 *
 * Uses the service_role key, which bypasses Row Level Security. Only import
 * this from server components, route handlers, or Server Actions — NEVER from
 * a "use client" file. Next.js will refuse to bundle SUPABASE_SERVICE_ROLE_KEY
 * into client code (no NEXT_PUBLIC_ prefix), but defense-in-depth: don't try.
 *
 * Note: typed via Database = any (Supabase default). Run `supabase gen types`
 * and import the generated types into createClient<Database>(...) when you want
 * full type-safety on table operations.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url        = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;

if (!url)        throw new Error("NEXT_PUBLIC_SUPABASE_URL is not set");
if (!serviceKey) throw new Error("SUPABASE_SERVICE_ROLE_KEY is not set");

// Singleton — re-creating the client on every request leaks memory.
// Tagged on globalThis so dev mode HMR doesn't multiply instances.
const globalForSupa = globalThis as unknown as {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  __edgekit_supabase?: SupabaseClient<any>;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const supabaseAdmin: SupabaseClient<any> =
  globalForSupa.__edgekit_supabase ??
  createClient(url, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

if (process.env.NODE_ENV !== "production") {
  globalForSupa.__edgekit_supabase = supabaseAdmin;
}
