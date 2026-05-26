import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { supabaseAdmin } from "@/lib/supabase-server";

export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { data, error } = await supabaseAdmin
    .from("saved_strategies")
    .select("id, name, symbol, timeframe, created_at, updated_at")
    .eq("user_id", userId)
    .order("updated_at", { ascending: false });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data ?? []);
}

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const { name, graph, symbol, timeframe } = body;

  if (!name?.trim()) return NextResponse.json({ error: "name is required" }, { status: 400 });
  if (!graph)        return NextResponse.json({ error: "graph is required" }, { status: 400 });

  const { data, error } = await supabaseAdmin
    .from("saved_strategies")
    .insert({ user_id: userId, name: name.trim(), graph, symbol, timeframe })
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data, { status: 201 });
}
