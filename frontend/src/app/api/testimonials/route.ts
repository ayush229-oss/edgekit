import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { supabaseAdmin } from "@/lib/supabase-server";

/** Public — returns only approved testimonials (sorted newest first). */
export async function GET() {
  const { data, error } = await supabaseAdmin
    .from("testimonials")
    .select("id, name, role, text, tags, avatar, created_at")
    .eq("status", "approved")
    .order("created_at", { ascending: false });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data ?? []);
}

/** Authenticated — submit a new testimonial for review. */
export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const { name, role, text, tags } = body;

  if (!name?.trim()) return NextResponse.json({ error: "name is required" }, { status: 400 });
  if (!text?.trim()) return NextResponse.json({ error: "text is required" }, { status: 400 });

  // Derive avatar initial from name
  const avatar = name.trim()[0].toUpperCase();

  const { data, error } = await supabaseAdmin
    .from("testimonials")
    .insert({
      user_id: userId,
      name:    name.trim(),
      role:    role?.trim() || null,
      text:    text.trim(),
      tags:    Array.isArray(tags) ? tags : [],
      avatar,
      status:  "pending",
    })
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data, { status: 201 });
}
