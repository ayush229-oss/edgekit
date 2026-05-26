"use client";

/**
 * Top-corner gauge: green/amber/red based on the complexity_score
 * returned by /graph/v2/complexity. Updates whenever the graph changes.
 */
import type { V2Complexity } from "@/lib/api";

const COLORS: Record<V2Complexity["level"], { bg: string; text: string; label: string; tip: string }> = {
  green: {
    bg: "bg-sage/20", text: "text-sage",
    label: "Simple — robust",
    tip: "Few params + few alphas. A simple strategy is harder to over-tune to the past, so it's more likely to keep working in the future.",
  },
  amber: {
    bg: "bg-amber/30", text: "text-amber-900",
    label: "Getting complex",
    tip: "Moderate number of knobs. Watch out — more params = easier to accidentally curve-fit to this one symbol/timeframe.",
  },
  red:   {
    bg: "bg-terra/20", text: "text-terra",
    label: "Too many knobs",
    tip: "Lots of parameters across multiple alphas. Risk: you've made the strategy look great on this exact history, but it'll break on live data. Try removing filters or merging similar nodes.",
  },
};


export function ComplexityMeter({ c }: { c: V2Complexity | null }) {
  if (!c) return null;
  const s = COLORS[c.level];
  return (
    <div className={`rounded-md ${s.bg} px-3 py-1.5 flex items-center gap-2 text-xs`}
         title={`${s.label} — ${s.tip}\n\nScore: ${c.score} · ${c.params} tunable params · ${c.alpha_count} alpha signal(s)`}>
      <div className={`font-mono font-semibold ${s.text}`}>{c.score}</div>
      <div className={`text-[10px] ${s.text}`}>
        <div className="font-semibold flex items-center gap-1">{s.label} <span className="text-muted">ⓘ</span></div>
        <div className="text-muted">{c.params} params · {c.alpha_count} alpha</div>
      </div>
    </div>
  );
}
