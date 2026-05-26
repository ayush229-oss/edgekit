import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { supabaseAdmin } from "@/lib/supabase-server";

export async function GET(
  _req: Request,
  { params }: { params: { id: string } },
) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { data, error } = await supabaseAdmin
    .from("saved_strategies")
    .select("*")
    .eq("id", params.id)
    .eq("user_id", userId)
    .single();

  if (error) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json(data);
}

export async function PUT(
  req: Request,
  { params }: { params: { id: string } },
) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const { name, graph, symbol, timeframe } = body;

  const { data, error } = await supabaseAdmin
    .from("saved_strategies")
    .update({
      ...(name  && { name: name.trim() }),
      ...(graph && { graph }),
      ...(symbol    && { symbol }),
      ...(timeframe && { timeframe }),
      updated_at: new Date().toISOString(),
    })
    .eq("id", params.id)
    .eq("user_id", userId)
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data);
}

export async function DELETE(
  _req: Request,
  { params }: { params: { id: string } },
) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { error } = await supabaseAdmin
    .from("saved_strategies")
    .delete()
    .eq("id", params.id)
    .eq("user_id", userId);

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true });
}
