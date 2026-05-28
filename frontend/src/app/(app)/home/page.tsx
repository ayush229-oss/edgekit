import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { supabaseAdmin } from "@/lib/supabase-server";

const FEATURES = [
  {
    icon: "⚡",
    title: "Backtests in seconds",
    body: "Run years of market data in under 2 seconds. Change a parameter, instantly see new results.",
  },
  {
    icon: "🎛️",
    title: "Tune with sliders, not code",
    body: "Every strategy parameter is an adjustable knob. Drag and see results update. No code. No Python. No Pine.",
  },
  {
    icon: "🧩",
    title: "Visual node builder",
    body: "Wire trading logic like Lego. Signal nodes, filter nodes, risk nodes — snap them together, run the backtest.",
  },
  {
    icon: "📤",
    title: "Export to TradingView",
    body: "When your strategy works on paper, export as Pine Script v6 in one click and take it live.",
  },
];

async function getUserStats(userId: string) {
  const [backtestsRes, resultsRes, strategiesRes, profileRes] = await Promise.all([
    supabaseAdmin
      .from("backtests")
      .select("id", { count: "exact", head: true })
      .eq("user_id", userId),
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
      .select("created_at")
      .eq("id", userId)
      .single(),
  ]);

  const results = resultsRes.data ?? [];
  const wrValues = results
    .map((r: any) => r.metrics?.wr as number | undefined)
    .filter((v): v is number => typeof v === "number");

  const joinedAt = profileRes.data?.created_at
    ? new Date(profileRes.data.created_at)
    : null;
  const daysSince = joinedAt
    ? Math.floor((Date.now() - joinedAt.getTime()) / 86_400_000)
    : 0;

  return {
    backtestsRun:    backtestsRes.count ?? 0,
    strategiesSaved: strategiesRes.count ?? 0,
    bestWinRate:     wrValues.length > 0 ? Math.max(...wrValues) : null,
    daysSince,
  };
}

export default async function AppHome() {
  const { userId } = await auth();
  const stats = userId ? await getUserStats(userId) : null;

  const statCards = [
    {
      label: "Backtests run",
      value: stats ? String(stats.backtestsRun) : "0",
      hint:  stats?.backtestsRun ? "Keep iterating" : "Run your first →",
    },
    {
      label: "Strategies saved",
      value: stats ? String(stats.strategiesSaved) : "0",
      hint:  stats?.strategiesSaved ? "Load one from Builder" : "Save a strategy to track it",
    },
    {
      label: "Best win rate",
      value: stats?.bestWinRate != null ? `${stats.bestWinRate.toFixed(1)}%` : "—",
      hint:  stats?.bestWinRate != null ? "Across all saved results" : "Run a backtest to see",
    },
    {
      label: "Days building",
      value: stats ? String(stats.daysSince || "< 1") : "0",
      hint:  "Keep compounding your edge",
    },
  ];

  return (
    <div className="space-y-10">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div>
        <p className="text-[11px] uppercase tracking-[0.25em] text-money font-semibold mb-2">Dashboard</p>
        <h1 className="text-[32px] font-bold tracking-tight text-ink">Good to have you here.</h1>
        <p className="text-muted mt-2 text-[15px]">
          Edgekit helps you find strategies that actually work — before you risk a single rupee.
        </p>
      </div>

      {/* ── Stats ──────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((s) => (
          <div key={s.label} className="card p-5">
            <div className="text-[11px] uppercase tracking-widest text-muted">{s.label}</div>
            <div className="text-[28px] font-bold text-ink num mt-1">{s.value}</div>
            <div className="text-[11px] text-muted mt-1">{s.hint}</div>
          </div>
        ))}
      </div>

      {/* ── Start strategy ─────────────────────────────────────────────────── */}
      <Link
        href="/strategies"
        className="card-hover p-8 group flex flex-col sm:flex-row sm:items-center gap-6 sm:gap-8"
      >
        <div className="text-5xl shrink-0">🧩</div>
        <div className="flex-1">
          <h2 className="font-semibold text-[20px] text-ink group-hover:text-money transition-colors mb-2">
            Start a strategy
          </h2>
          <p className="text-[13.5px] text-muted leading-relaxed">
            Open a proven node graph — Donchian, Ichimoku, SMC, RSI+Bollinger, EMA Cross, and more —
            or start with a blank canvas. Tune, re-run, make it yours.
          </p>
        </div>
        <div className="text-[13px] text-money font-medium shrink-0">Browse templates →</div>
      </Link>

      {/* ── What Edgekit does ──────────────────────────────────────────────── */}
      <div className="card p-8">
        <h2 className="text-[18px] font-semibold mb-6">What Edgekit does</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {FEATURES.map((f) => (
            <div key={f.title} className="flex gap-4">
              <div className="text-2xl shrink-0">{f.icon}</div>
              <div>
                <h3 className="font-medium text-[14px] mb-1">{f.title}</h3>
                <p className="text-[13px] text-muted leading-relaxed">{f.body}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Quick links ────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-3">
        <Link href="/resources"    className="btn-ghost text-[13px]">🔌 Connect broker or AI →</Link>
        <Link href="/analytics"    className="btn-ghost text-[13px]">📈 View analytics →</Link>
        <Link href="/testimonials" className="btn-ghost text-[13px]">💬 Community stories →</Link>
      </div>
    </div>
  );
}
