"use client";

import { useState } from "react";
import dynamic from "next/dynamic";

const EquityChart = dynamic(
  () => import("@/components/EquityChart").then((m) => ({ default: m.EquityChart })),
  { ssr: false, loading: () => <div className="h-32 animate-pulse bg-surface2 rounded-lg" /> }
);

type SavedResult = {
  id:            string;
  name:          string;
  strategy_name: string | null;
  symbol:        string | null;
  timeframe:     string | null;
  bars:          number | null;
  metrics: {
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

function fmt(n: number | null | undefined, decimals = 1) {
  return n == null ? "—" : n.toFixed(decimals);
}

export function AnalyticsTable({ results }: { results: SavedResult[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  function toggle(id: string) {
    setExpanded((prev) => (prev === id ? null : id));
  }

  return (
    <div className="card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-border bg-surface2">
              <th className="text-left px-4 py-3 font-medium text-muted text-[11px] uppercase tracking-widest">Name</th>
              <th className="text-left px-4 py-3 font-medium text-muted text-[11px] uppercase tracking-widest">Symbol · TF</th>
              <th className="text-right px-4 py-3 font-medium text-muted text-[11px] uppercase tracking-widest">Trades</th>
              <th className="text-right px-4 py-3 font-medium text-muted text-[11px] uppercase tracking-widest">Win %</th>
              <th className="text-right px-4 py-3 font-medium text-muted text-[11px] uppercase tracking-widest">Total R</th>
              <th className="text-right px-4 py-3 font-medium text-muted text-[11px] uppercase tracking-widest">PF</th>
              <th className="text-right px-4 py-3 font-medium text-muted text-[11px] uppercase tracking-widest">Max DD</th>
              <th className="text-right px-4 py-3 font-medium text-muted text-[11px] uppercase tracking-widest">Saved</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r, i) => {
              const isUp   = (r.metrics?.total_r ?? 0) >= 0;
              const isOpen = expanded === r.id;
              const hasCurve = Array.isArray(r.equity_curve) && r.equity_curve.length > 0;
              return (
                <>
                  <tr
                    key={r.id}
                    onClick={() => hasCurve && toggle(r.id)}
                    className={`border-b border-border last:border-0 transition-colors
                      ${i % 2 === 0 ? "" : "bg-paper/50"}
                      ${hasCurve ? "cursor-pointer hover:bg-money/5" : "hover:bg-surface2/50"}`}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        {hasCurve && (
                          <span className={`text-[10px] text-money transition-transform inline-block ${isOpen ? "rotate-90" : ""}`}>▶</span>
                        )}
                        <div>
                          <div className="font-medium text-ink">{r.name}</div>
                          {r.strategy_name && (
                            <div className="text-[11px] text-muted">{r.strategy_name}</div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted font-mono text-[12px]">
                      {r.symbol ?? "—"}{r.timeframe ? ` · ${r.timeframe}` : ""}
                    </td>
                    <td className="px-4 py-3 text-right font-mono">{r.metrics?.trades ?? "—"}</td>
                    <td className="px-4 py-3 text-right font-mono">{fmt(r.metrics?.wr)}%</td>
                    <td className={`px-4 py-3 text-right font-mono font-semibold ${isUp ? "text-up" : "text-down"}`}>
                      {isUp ? "+" : ""}{fmt(r.metrics?.total_r)}R
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-muted">
                      {r.metrics?.profit_factor === 99 ? "∞" : fmt(r.metrics?.profit_factor, 2)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-muted">{fmt(r.metrics?.max_dd)}R</td>
                    <td className="px-4 py-3 text-right text-muted text-[11px]">
                      {new Date(r.created_at).toLocaleDateString("en-IN", { day: "2-digit", month: "short" })}
                    </td>
                  </tr>
                  {isOpen && hasCurve && (
                    <tr key={`${r.id}-curve`} className="border-b border-border bg-paper/30">
                      <td colSpan={8} className="px-4 py-4">
                        <p className="text-[11px] text-muted mb-2 font-medium uppercase tracking-widest">Equity curve — {r.name}</p>
                        <div className="h-40">
                          <EquityChart curve={r.equity_curve!} />
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="px-4 py-2 border-t border-border bg-surface2/50">
        <p className="text-[11px] text-muted">Click any row to expand its equity curve.</p>
      </div>
    </div>
  );
}
