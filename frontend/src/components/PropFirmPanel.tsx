"use client";
import React, { useState } from "react";
import type { ChallengeParams, ChallengeResult } from "@/lib/api";

const PRESETS: { label: string; params: ChallengeParams }[] = [
  {
    label: "FTMO $10k",
    params: { account_size: 10000, daily_loss_limit_pct: 5, max_drawdown_pct: 10, profit_target_pct: 10, min_trading_days: 4 },
  },
  {
    label: "FTMO $25k",
    params: { account_size: 25000, daily_loss_limit_pct: 5, max_drawdown_pct: 10, profit_target_pct: 10, min_trading_days: 4 },
  },
  {
    label: "TFT $10k",
    params: { account_size: 10000, daily_loss_limit_pct: 4, max_drawdown_pct: 8,  profit_target_pct: 8,  min_trading_days: 5 },
  },
];

export function PropFirmPanel({
  enabled, params, result,
  onToggle, onChange,
}: {
  enabled:  boolean;
  params:   ChallengeParams;
  result?:  ChallengeResult;
  onToggle: () => void;
  onChange: (p: ChallengeParams) => void;
}) {
  const [open, setOpen] = useState(false);

  const set = (k: keyof ChallengeParams, v: number) =>
    onChange({ ...params, [k]: v });

  return (
    <div className="border-t border-border">
      {/* Header row */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-cream transition-colors"
      >
        <span className="text-[10px] uppercase tracking-widest text-muted font-semibold flex-1">
          Prop Firm Challenge
        </span>
        <label
          onClick={(e) => { e.stopPropagation(); onToggle(); }}
          className="flex items-center gap-1.5 cursor-pointer"
        >
          <div className={`w-7 h-4 rounded-full transition-colors relative ${enabled ? "bg-money" : "bg-border"}`}>
            <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform ${enabled ? "translate-x-3.5" : "translate-x-0.5"}`} />
          </div>
        </label>
        <span className="text-muted text-[10px]">{open ? "▴" : "▾"}</span>
      </button>

      {/* Verdict banner — always visible when there's a result */}
      {enabled && result && (
        <div className={`mx-3 mb-2 px-3 py-2 rounded-lg text-[12px] font-medium flex items-center gap-2
          ${result.passed ? "bg-up/15 text-up" : "bg-down/15 text-down"}`}>
          <span>{result.passed ? "✓" : "✕"}</span>
          <span className="flex-1 leading-snug">{result.verdict}</span>
        </div>
      )}

      {open && (
        <div className="px-3 pb-3 space-y-3">
          {/* Presets */}
          <div className="flex flex-wrap gap-1.5">
            {PRESETS.map((p) => (
              <button
                key={p.label}
                onClick={() => onChange(p.params)}
                className="text-[10px] px-2 py-0.5 rounded-full border border-border bg-cream hover:bg-cream2 transition-colors"
              >
                {p.label}
              </button>
            ))}
          </div>

          {/* Params */}
          <Row label="Account size ($)" value={params.account_size}
            min={1000} max={200000} step={1000}
            onChange={(v) => set("account_size", v)} format="$" />
          <Row label="Daily loss limit (%)" value={params.daily_loss_limit_pct}
            min={1} max={10} step={0.5}
            onChange={(v) => set("daily_loss_limit_pct", v)} format="%" />
          <Row label="Max drawdown (%)" value={params.max_drawdown_pct}
            min={2} max={20} step={0.5}
            onChange={(v) => set("max_drawdown_pct", v)} format="%" />
          <Row label="Profit target (%)" value={params.profit_target_pct}
            min={2} max={20} step={0.5}
            onChange={(v) => set("profit_target_pct", v)} format="%" />
          <Row label="Min trading days" value={params.min_trading_days}
            min={1} max={30} step={1}
            onChange={(v) => set("min_trading_days", v)} format="d" />

          {/* Day-by-day table */}
          {enabled && result && result.daily.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-widest text-muted mb-1.5">Day-by-day</div>
              <div className="rounded-lg border border-border overflow-hidden">
                <table className="w-full text-[11px]">
                  <thead>
                    <tr className="bg-cream3 text-muted">
                      <th className="text-left px-2 py-1 font-medium">Date</th>
                      <th className="text-right px-2 py-1 font-medium">P&L</th>
                      <th className="text-right px-2 py-1 font-medium">Equity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.daily.map((d) => (
                      <tr key={d.date}
                        className={`border-t border-border ${
                          d.status === "fail"       ? "bg-down/10"      :
                          d.status === "target_hit" ? "bg-up/10"        : ""
                        }`}>
                        <td className="px-2 py-1 font-mono text-muted">{d.date.slice(5)}</td>
                        <td className={`px-2 py-1 text-right font-mono ${d.pnl_usd >= 0 ? "text-up" : "text-down"}`}>
                          {d.pnl_usd >= 0 ? "+" : ""}${d.pnl_usd.toFixed(0)}
                        </td>
                        <td className="px-2 py-1 text-right font-mono">${d.equity.toFixed(0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ label, value, min, max, step, onChange, format }: {
  label: string; value: number; min: number; max: number; step: number;
  onChange: (v: number) => void; format: string;
}) {
  return (
    <div>
      <div className="flex justify-between text-[11px] mb-1">
        <span className="text-muted">{label}</span>
        <span className="font-mono text-ink">
          {format === "$" ? `$${value.toLocaleString()}` : `${value}${format}`}
        </span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full accent-money h-1" />
    </div>
  );
}
