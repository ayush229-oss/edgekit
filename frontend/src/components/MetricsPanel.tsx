"use client";
import React from "react";
import type { BacktestMetrics } from "@/lib/api";

export function MetricsPanel({
  m, bars, pip,
}: {
  m: BacktestMetrics; bars: number; pip: number;
}) {
  const Card = ({ label, value, sub, tone = "ink" }: { label: string; value: React.ReactNode; sub?: string; tone?: "ink" | "sage" | "terra" }) => (
    <div className="rounded-xl bg-cream2 border border-border p-4">
      <div className="text-[11px] uppercase tracking-widest text-muted">{label}</div>
      <div className={`text-2xl font-semibold mt-1
        ${tone === "sage"  ? "text-sage"  : ""}
        ${tone === "terra" ? "text-terra" : ""}`}>{value}</div>
      {sub && <div className="text-xs text-muted mt-1">{sub}</div>}
    </div>
  );

  const evTone   = m.ev > 0 ? "sage" : "terra";
  const ddTone   = m.max_dd < -20 ? "terra" : "ink";

  return (
    <div className="space-y-4">
      <div className="text-xs text-muted">
        {bars.toLocaleString()} bars · pip = {pip} · {m.n_setups} setups detected
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card label="Trades"        value={m.trades.toLocaleString()} />
        <Card label="Win rate"      value={`${m.wr.toFixed(1)}%`} tone={m.wr > 50 ? "sage" : "ink"} />
        <Card label="EV / trade"    value={`${m.ev.toFixed(2)}R`} tone={evTone} />
        <Card label="Total"         value={`${m.total_r.toFixed(0)}R`} tone={m.total_r > 0 ? "sage" : "terra"} />
        <Card label="Profit factor" value={m.profit_factor.toFixed(2)} tone={m.profit_factor > 1.5 ? "sage" : "ink"} />
        <Card label="Max DD"        value={`${m.max_dd.toFixed(1)}%`} tone={ddTone} />
        <Card label="Avg win"       value={`${m.avg_win.toFixed(2)}R`} tone="sage" />
        <Card label="Avg loss"      value={`${m.avg_loss.toFixed(2)}R`} tone="terra" />
      </div>

      <div className="rounded-xl bg-cream2 border border-border p-4">
        <div className="text-[11px] uppercase tracking-widest text-muted mb-2">Exit breakdown</div>
        <div className="flex flex-wrap gap-2">
          {Object.entries(m.exit_counts).map(([k, v]) => (
            <span key={k} className="px-3 py-1.5 rounded-full bg-cream3 text-xs">
              <span className="font-mono">{k}</span> · {v}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
