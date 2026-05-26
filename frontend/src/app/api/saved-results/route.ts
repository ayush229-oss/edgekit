import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { supabaseAdmin } from "@/lib/supabase-server";

export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { data, error } = await supabaseAdmin
    .from("saved_results")
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data ?? []);
}

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const { name, strategy_name, symbol, timeframe, bars, metrics, equity_curve, graph } = body;

  if (!name?.trim()) return NextResponse.json({ error: "name is required" }, { status: 400 });
  if (!metrics)       return NextResponse.json({ error: "metrics is required" }, { status: 400 });

  const { data, error } = await supabaseAdmin
    .from("saved_results")
    .insert({
      user_id: userId,
      name: name.trim(),
      strategy_name,
      symbol,
      timeframe,
      bars,
      metrics,
      equity_curve,
      graph,
    })
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data, { status: 201 });
}
