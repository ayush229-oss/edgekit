/**
 * POST /api/affiliate-waitlist — saves affiliate interest to usage_events.
 * event_type = 'affiliate_waitlist'.
 */
import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { supabaseAdmin } from "@/lib/supabase-server";

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { email } = await req.json().catch(() => ({}));
  if (!email?.trim())
    return NextResponse.json({ error: "email is required" }, { status: 400 });

  const { error } = await supabaseAdmin
    .from("usage_events")
    .insert({
      user_id:    userId,
      event_type: "affiliate_waitlist",
      details:    { email: email.trim() },
    });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true }, { status: 201 });
}
