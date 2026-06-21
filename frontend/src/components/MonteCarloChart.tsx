"use client";

import {
  AreaChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer,
} from "recharts";

export function MonteCarloChart({
  percentiles, nSims, nTrades,
}: {
  percentiles: Record<string, number[]>;
  nSims: number;
  nTrades: number;
}) {
  const len = percentiles.p50?.length ?? 0;
  // Stacked-area trick: an invisible base (p5 / p25) + a visible delta on top
  // (p95-p5 / p75-p25) gives a true "fill between two curves" band in recharts.
  const data = Array.from({ length: len }, (_, i) => ({
    i,
    p5:  percentiles.p5[i],
    p25: percentiles.p25[i],
    p50: percentiles.p50[i],
    p75: percentiles.p75[i],
    p95: percentiles.p95[i],
    bandOuter: percentiles.p95[i] - percentiles.p5[i],
    bandInner: percentiles.p75[i] - percentiles.p25[i],
  }));

  return (
    <div className="rounded-xl bg-cream2 border border-border p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium">Monte Carlo — equity percentile bands</h3>
        <span className="text-xs text-muted">
          {nSims} shuffles · {nTrades} trades resampled
        </span>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <AreaChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E0D9C7" />
          <XAxis dataKey="i" tick={{ fill: "#8A8071", fontSize: 11 }} />
          <YAxis
            tick={{ fill: "#8A8071", fontSize: 11 }}
            tickFormatter={(v) => `$${Math.round(v).toLocaleString()}`}
          />
          <Tooltip
            contentStyle={{ background: "#FAF7EE", border: "1px solid #D4CCB8", borderRadius: 8 }}
            labelStyle={{ color: "#8A8071" }}
            formatter={(value: any, key: string) => {
              const labels: Record<string, string> = {
                p5: "5th pct", p25: "25th pct", p50: "Median", p75: "75th pct", p95: "95th pct",
              };
              if (!(key in labels)) return null as any;
              return [`$${Math.round(value).toLocaleString()}`, labels[key]];
            }}
          />
          <ReferenceLine y={100} stroke="#8A8071" strokeDasharray="4 4" />

          {/* Outer band: 5th–95th percentile */}
          <Area dataKey="p5"        stackId="outer" stroke="none" fill="transparent" />
          <Area dataKey="bandOuter" stackId="outer" stroke="none" fill="#6B9B7A" fillOpacity={0.12} />

          {/* Inner band: 25th–75th percentile */}
          <Area dataKey="p25"       stackId="inner" stroke="none" fill="transparent" />
          <Area dataKey="bandInner" stackId="inner" stroke="none" fill="#6B9B7A" fillOpacity={0.30} />

          <Line type="monotone" dataKey="p50" stroke="#3F6B4C" strokeWidth={2} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
      <p className="text-[11px] text-muted mt-2">
        Same trades, every possible order. The band shows how much your result depends on
        sequencing luck — a strategy whose median still ends above $100 with a narrow band is
        more robust than one that only "worked" because of a lucky trade order.
      </p>
    </div>
  );
}
