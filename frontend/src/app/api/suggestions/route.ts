/**
 * POST /api/suggestions — saves a feature request to usage_events.
 * No new table needed; event_type = 'feature_request'.
 */
import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { supabaseAdmin } from "@/lib/supabase-server";

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { category, title, detail } = await req.json().catch(() => ({}));
  if (!title?.trim())
    return NextResponse.json({ error: "title is required" }, { status: 400 });

  const { error } = await supabaseAdmin
    .from("usage_events")
    .insert({
      user_id:    userId,
      event_type: "feature_request",
      details:    { category: category ?? "Other", title: title.trim(), detail: detail?.trim() ?? "" },
    });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true }, { status: 201 });
}
