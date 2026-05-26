/**
 * Sync the current Clerk user into Supabase `profiles` on each request.
 *
 * Cheap upsert — runs on protected page loads via a server-side call. Updates
 * `last_seen_at` so we have a single source of activity truth.
 *
 * Returns the synced profile row (or null if not authenticated).
 */
import { currentUser } from "@clerk/nextjs/server";
import { supabaseAdmin } from "./supabase-server";

export type Profile = {
  id:            string;
  email:         string;
  name:          string | null;
  image_url:     string | null;
  signin_method: string | null;
  created_at:    string;
  last_seen_at:  string;
};

export async function syncCurrentUserProfile(): Promise<Profile | null> {
  const user = await currentUser();
  if (!user) return null;

  const email =
    user.emailAddresses.find((e) => e.id === user.primaryEmailAddressId)?.emailAddress ??
    user.emailAddresses[0]?.emailAddress ??
    "";

  const name =
    [user.firstName, user.lastName].filter(Boolean).join(" ") || user.username || null;

  // signin method — pull from the primary external account if present
  const signin_method =
    user.externalAccounts[0]?.provider || "email";

  const { data, error } = await supabaseAdmin
    .from("profiles")
    .upsert(
      {
        id:            user.id,
        email,
        name,
        image_url:     user.imageUrl || null,
        signin_method,
        last_seen_at:  new Date().toISOString(),
      },
      { onConflict: "id" }
    )
    .select()
    .single();

  if (error) {
    console.error("syncCurrentUserProfile failed:", error);
    return null;
  }
  return data as Profile;
}

/**
 * Returns true if the current user is an admin.
 * Checks BOTH the ADMIN_EMAIL env var and the is_admin column in Supabase profiles.
 * Set is_admin=true in Supabase Table Editor to grant admin access without env vars.
 */
export async function isAdmin(): Promise<boolean> {
  const user = await currentUser();
  if (!user) return false;

  // 1. Check ADMIN_EMAIL env var (skip if still set to placeholder)
  const adminEmail = (process.env.ADMIN_EMAIL || "").toLowerCase().trim();
  if (adminEmail && adminEmail !== "your_email") {
    const match = user.emailAddresses.some(
      (e) => e.emailAddress.toLowerCase() === adminEmail
    );
    if (match) return true;
  }

  // 2. Check is_admin column in Supabase profiles table
  const { data } = await supabaseAdmin
    .from("profiles")
    .select("is_admin")
    .eq("id", user.id)
    .single();

  return data?.is_admin === true;
}
