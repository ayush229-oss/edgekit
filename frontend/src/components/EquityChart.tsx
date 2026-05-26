"use client";

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

export function EquityChart({ curve }: { curve: number[] }) {
  const data = curve.map((v, i) => ({ i, equity: Math.max(v, 0.01) }));

  return (
    <div className="rounded-xl bg-cream2 border border-border p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium">Equity curve</h3>
        <span className="text-xs text-muted">log scale · $100 start · 1% risk</span>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E0D9C7" />
          <XAxis dataKey="i" tick={{ fill: "#8A8071", fontSize: 11 }} />
          <YAxis
            scale="log" domain={["auto", "auto"]}
            tick={{ fill: "#8A8071", fontSize: 11 }}
            tickFormatter={(v) => `$${Math.round(v).toLocaleString()}`}
          />
          <Tooltip
            contentStyle={{ background: "#FAF7EE", border: "1px solid #D4CCB8", borderRadius: 8 }}
            labelStyle={{ color: "#8A8071" }}
            formatter={(v: any) => [`$${Math.round(v).toLocaleString()}`, "Equity"]}
          />
          <Line type="monotone" dataKey="equity" stroke="#6B9B7A" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
