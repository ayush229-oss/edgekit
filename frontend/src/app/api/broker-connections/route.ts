import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { supabaseAdmin } from "@/lib/supabase-server";
import { encryptString, decryptString, keyHint } from "@/lib/encryption";

export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { data, error } = await supabaseAdmin
    .from("broker_connections")
    .select("id, source_id, label, config, credentials_enc, is_active, created_at")
    .eq("user_id", userId)
    .order("created_at", { ascending: false });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  // Decrypt sensitive fields → return only hints (never raw keys to client)
  const safe = (data ?? []).map((row: any) => {
    let credHints: Record<string, string> = {};
    if (row.credentials_enc) {
      try {
        const raw = JSON.parse(decryptString(row.credentials_enc)) as Record<string, string>;
        credHints = Object.fromEntries(
          Object.entries(raw).map(([k, v]) => [k, keyHint(v)])
        );
      } catch { /* decryption failed — credentials corrupt */ }
    }
    return { ...row, credentials_enc: undefined, credential_hints: credHints };
  });

  return NextResponse.json(safe);
}

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const { source_id, label, config = {}, credentials = {}, is_active = false } = body;

  if (!source_id) return NextResponse.json({ error: "source_id required" }, { status: 400 });

  // Encrypt sensitive credentials before storing
  const credentials_enc = Object.keys(credentials).length > 0
    ? encryptString(JSON.stringify(credentials))
    : null;

  const { data, error } = await supabaseAdmin
    .from("broker_connections")
    .upsert(
      { user_id: userId, source_id, label, config, credentials_enc, is_active },
      { onConflict: "user_id,source_id" }
    )
    .select("id, source_id, label, config, is_active, created_at")
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data, { status: 201 });
}
