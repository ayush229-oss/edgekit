/**
 * Admin-only: approve or reject a pending testimonial.
 * PATCH /api/testimonials/<id>   body: { status: "approved" | "rejected" }
 */
import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { supabaseAdmin } from "@/lib/supabase-server";
import { isAdmin } from "@/lib/profile-sync";

export async function PATCH(
  req: Request,
  { params }: { params: { id: string } },
) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const admin = await isAdmin();
  if (!admin) return NextResponse.json({ error: "Forbidden" }, { status: 403 });

  const { status } = await req.json();
  if (!["approved", "rejected"].includes(status))
    return NextResponse.json({ error: "status must be approved or rejected" }, { status: 400 });

  const { data, error } = await supabaseAdmin
    .from("testimonials")
    .update({ status })
    .eq("id", params.id)
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data);
}

/** Admin-only: list all testimonials (any status). */
export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const admin = await isAdmin();
  if (!admin) return NextResponse.json({ error: "Forbidden" }, { status: 403 });

  const { data, error } = await supabaseAdmin
    .from("testimonials")
    .select("*")
    .order("created_at", { ascending: false });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data ?? []);
}
