/**
 * DELETE /api/ai-keys/:provider  — removes the stored key for this provider.
 */
import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { supabaseAdmin } from "@/lib/supabase-server";

export async function DELETE(
  _req: Request,
  { params }: { params: { provider: string } },
) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { error } = await supabaseAdmin
    .from("api_keys")
    .delete()
    .eq("user_id", userId)
    .eq("provider", params.provider);

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true });
}
