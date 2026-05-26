/**
 * AI key storage — backed by Supabase `api_keys` table (AES-256-GCM encrypted).
 *
 * GET  /api/ai-keys  → returns [{ provider, key (decrypted), hint }]
 * POST /api/ai-keys  → upsert { provider, key } — encrypts + stores
 */
import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { supabaseAdmin } from "@/lib/supabase-server";
import { encryptString, decryptString, keyHint } from "@/lib/encryption";

export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { data, error } = await supabaseAdmin
    .from("api_keys")
    .select("id, provider, encrypted_value, hint")
    .eq("user_id", userId);

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  const result = (data ?? []).map((row: any) => {
    let key = "";
    try { key = decryptString(row.encrypted_value); } catch {}
    return { id: row.id, provider: row.provider, key, hint: row.hint };
  });

  return NextResponse.json(result);
}

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { provider, key } = await req.json().catch(() => ({}));
  if (!provider || !key)
    return NextResponse.json({ error: "provider and key are required" }, { status: 400 });

  const encrypted_value = encryptString(key);
  const hint            = keyHint(key);

  const { data, error } = await supabaseAdmin
    .from("api_keys")
    .upsert(
      { user_id: userId, provider, encrypted_value, hint },
      { onConflict: "user_id,provider" }
    )
    .select("id, provider, hint")
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data, { status: 201 });
}
