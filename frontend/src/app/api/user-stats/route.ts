import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { supabaseAdmin } from "@/lib/supabase-server";

export type UserStats = {
  backtests_run:      number;
  strategies_saved:   number;
  best_win_rate:      number | null;
  best_total_r:       number | null;
  first_seen_at:      string | null;
  last_seen_at:       string | null;
};

export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  // Run queries in parallel
  const [resultsRes, strategiesRes, profileRes] = await Promise.all([
    supabaseAdmin
      .from("saved_results")
      .select("metrics")
      .eq("user_id", userId),
    supabaseAdmin
      .from("saved_strategies")
      .select("id", { count: "exact", head: true })
      .eq("user_id", userId),
    supabaseAdmin
      .from("profiles")
      .select("created_at, last_seen_at")
      .eq("id", userId)
      .single(),
  ]);

  const results     = resultsRes.data ?? [];
  const stratCount  = strategiesRes.count ?? 0;
  const profile     = profileRes.data;

  const backtests   = results.length;
  const winRates    = results
    .map((r: any) => r.metrics?.wr as number | undefined)
    .filter((v): v is number => typeof v === "number");
  const totalRs     = results
    .map((r: any) => r.metrics?.total_r as number | undefined)
    .filter((v): v is number => typeof v === "number");

  const stats: UserStats = {
    backtests_run:    backtests,
    strategies_saved: stratCount,
    best_win_rate:    winRates.length > 0 ? Math.max(...winRates) : null,
    best_total_r:     totalRs.length > 0  ? Math.max(...totalRs)  : null,
    first_seen_at:    profile?.created_at  ?? null,
    last_seen_at:     profile?.last_seen_at ?? null,
  };

  return NextResponse.json(stats);
}
