/**
 * POST /api/backtests — records every backtest run (not just saved ones).
 * Called fire-and-forget from the Builder after a successful run.
 * Powers the "Backtests run" stat on the home page.
 */
import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { supabaseAdmin } from "@/lib/supabase-server";

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const { graph_snapshot, symbol, timeframe, n_bars, metrics, duration_ms, strategy_id } = body;

  const { data, error } = await supabaseAdmin
    .from("backtests")
    .insert({
      user_id:        userId,
      graph_snapshot: graph_snapshot ?? {},
      symbol:         symbol         ?? null,
      timeframe:      timeframe      ?? null,
      n_bars:         n_bars         ?? null,
      metrics:        metrics        ?? null,
      duration_ms:    duration_ms    ?? null,
      strategy_id:    strategy_id    ?? null,
    })
    .select("id")
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ id: data.id }, { status: 201 });
}

/** GET /api/backtests — count of backtests for the current user. */
export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { count, error } = await supabaseAdmin
    .from("backtests")
    .select("id", { count: "exact", head: true })
    .eq("user_id", userId);

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ count: count ?? 0 });
}
