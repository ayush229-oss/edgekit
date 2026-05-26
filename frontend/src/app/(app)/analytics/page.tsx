import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { supabaseAdmin } from "@/lib/supabase-server";
import { AnalyticsTable } from "./AnalyticsTable";

type SavedResult = {
  id:            string;
  name:          string;
  strategy_name: string | null;
  symbol:        string | null;
  timeframe:     string | null;
  bars:          number | null;
  metrics:       {
    trades:        number;
    wr:            number;
    ev:            number;
    total_r:       number;
    profit_factor: number;
    max_dd:        number;
  };
  equity_curve: number[] | null;
  created_at:   string;
};

async function getData(userId: string) {
  const [resultsRes, strategiesRes] = await Promise.all([
    supabaseAdmin
      .from("saved_results")
      .select("id, name, strategy_name, symbol, timeframe, bars, metrics, equity_curve, created_at")
      .eq("user_id", userId)
      .order("created_at", { ascending: false }),
    supabaseAdmin
      .from("saved_strategies")
      .select("id", { count: "exact", head: true })
      .eq("user_id", userId),
  ]);

  const results   = (resultsRes.data ?? []) as SavedResult[];
  const stratCount = strategiesRes.count ?? 0;

  const wrValues   = results.map((r) => r.metrics?.wr).filter((v): v is number => typeof v === "number");
  const bestWR     = wrValues.length > 0 ? Math.max(...wrValues) : null;
  const bestResult = bestWR != null ? results.find((r) => r.metrics?.wr === bestWR) : null;

  return { results, stratCount, bestWR, bestResult };
}

export default async function AnalyticsPage() {
  const { userId } = await auth();
  const { results, stratCount, bestWR } = userId
    ? await getData(userId)
    : { results: [] as SavedResult[], stratCount: 0, bestWR: null };

  const statCards = [
    { label: "Saved results",     value: String(results.length), note: results.length ? "Click a row to compare" : "Save from Builder" },
    { label: "Strategies saved",  value: String(stratCount),     note: stratCount ? "Load in Builder" : "Save a strategy" },
    { label: "Best win rate",     value: bestWR != null ? `${bestWR.toFixed(1)}%` : "—", note: bestWR ? "Your top result" : "No data yet" },
    { label: "Best total R",
      value: results.length
        ? `${Math.max(...results.map((r) => r.metrics?.total_r ?? -Infinity)).toFixed(1)}R`
        : "—",
      note: results.length ? "Net R across all trades" : "No data yet",
    },
  ];

  return (
    <div className="space-y-8">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div>
        <p className="text-[11px] uppercase tracking-[0.25em] text-money font-semibold mb-2">Your performance</p>
        <h1 className="text-[32px] font-bold tracking-tight text-ink">Analytics</h1>
        <p className="text-muted mt-2 text-[15px]">
          Track what you've built, what works, and how you've grown as a trader.
        </p>
      </div>

      {/* ── Stats row ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((s) => (
          <div key={s.label} className="card p-5">
            <div className="text-[11px] uppercase tracking-widest text-muted">{s.label}</div>
            <div className="text-[26px] font-bold text-ink num mt-1">{s.value}</div>
            <div className="text-[11px] text-muted mt-0.5">{s.note}</div>
          </div>
        ))}
      </div>

      {/* ── Saved results table ────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-[18px] font-semibold">Saved results</h2>
          <Link href="/builder?template=blank" className="text-[12px] text-money hover:underline font-medium">
            + New backtest
          </Link>
        </div>

        {results.length === 0 ? (
          <div className="card p-12 text-center">
            <div className="text-4xl mb-4">📈</div>
            <h3 className="font-semibold text-[16px] mb-2">No saved results yet</h3>
            <p className="text-[13px] text-muted max-w-md mx-auto mb-6 leading-relaxed">
              After running a backtest in the Builder, click <strong>Save result</strong> to
              track it here. Compare across runs, spot improvements.
            </p>
            <Link href="/strategies" className="btn-primary text-[13px]">
              Run your first backtest →
            </Link>
          </div>
        ) : (
          <AnalyticsTable results={results} />
        )}
      </div>

      {/* ── Coming soon ────────────────────────────────────────────────────── */}
      <div className="card p-6">
        <h3 className="font-medium text-[11px] mb-4 text-muted uppercase tracking-widest">Coming soon</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[
            { icon: "📊", title: "Equity curve comparison", body: "Plot multiple saved results on the same chart." },
            { icon: "🎯", title: "Parameter heatmap",        body: "See which ranges produce the best results." },
            { icon: "📅", title: "Performance by period",    body: "Break down win rate and R by month or session." },
          ].map((f) => (
            <div key={f.title} className="flex gap-3 opacity-60">
              <div className="text-xl shrink-0">{f.icon}</div>
              <div>
                <h4 className="font-medium text-[13px]">{f.title}</h4>
                <p className="text-[12px] text-muted mt-0.5">{f.body}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
