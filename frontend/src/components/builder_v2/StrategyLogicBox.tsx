"use client";

/**
 * Strategy Logic Box — reads the current graph and renders an English
 * description of what the strategy does, lane by lane. Also surfaces
 * **structural problems** (missing inputs, unused outputs, no sinks, etc.)
 * so the user knows whether the graph will run.
 *
 * Updates live as the user wires/edits. Pure client-side — no backend call.
 */
import type { V2NodeSpec, V2GraphNode, V2GraphEdge } from "@/lib/api";


// Per-node English renderer. Falls back to a generic line for unknown types.
function describeNode(n: V2GraphNode, spec: V2NodeSpec): string {
  const p = n.params;
  switch (n.type) {
    // ── Universe ────────────────────────────────────────────────────────
    case "universe.single_asset":
      return `Trades **${p.ticker}** on **${p.timeframe}**.`;

    // ── Indicators ──────────────────────────────────────────────────────
    case "indicator.ema":         return `Tracks the **${p.period}-period EMA** of close.`;
    case "indicator.atr":         return `Measures volatility via **${p.period}-period ATR**.`;
    case "indicator.donchian":    return `Watches the **${p.period}-bar Donchian channel** (highest high / lowest low, excluding current).`;
    case "indicator.rsi":         return `Tracks momentum via **${p.period}-period RSI**.`;
    case "indicator.macd":        return `Computes **MACD(${p.fast}, ${p.slow}, ${p.signal})**.`;
    case "indicator.bollinger":   return `Watches **Bollinger Bands(${p.period}, ${p.mult}σ)**.`;
    case "indicator.adx":         return `Measures trend strength via **${p.period}-period ADX**.`;
    case "indicator.stochastic":  return `Tracks **Stochastic(%K=${p.k_period}, %D=${p.d_period})**.`;
    case "indicator.vwap":        return `Tracks **VWAP** (volume-weighted average price).`;
    case "indicator.swing_high":  return `Tracks the **highest high of the last ${p.period} bars** (rolling swing high).`;
    case "indicator.swing_low":   return `Tracks the **lowest low of the last ${p.period} bars** (rolling swing low).`;
    case "indicator.price":       return `Exposes raw **${p.source}** price as a wire.`;
    case "indicator.sma":         return `Tracks the **${p.period}-period SMA** of close.`;
    case "indicator.supertrend":  return `Computes **SuperTrend** (period=${p.period}, mult=${p.mult}).`;
    case "indicator.cci":         return `Tracks the **${p.period}-period CCI** (Commodity Channel Index).`;
    case "indicator.williams_r":  return `Tracks the **${p.period}-period Williams %R**.`;
    case "indicator.roc":         return `Tracks **${p.period}-bar rate of change**.`;
    case "indicator.order_block":
      return `Locates the most recent **${p.direction === "long" ? "bearish" : "bullish"} candle** in the last ${p.scan_min}-${p.scan_max} bars (the **${p.direction === "long" ? "Bull" : "Bear"} Order Block**). Outputs high, low, midpoint — wire the midpoint into a limit entry, the low/high into a structure stop.`;
    case "indicator.ichimoku":
      return `Computes the **Ichimoku** system (Tenkan=${p.tenkan_period}, Kijun=${p.kijun_period}, Senkou B=${p.senkou_b_period}). Outputs Tenkan, Kijun, Senkou A, Senkou B.`;

    // ── Alpha ───────────────────────────────────────────────────────────
    case "alpha.crossover":
      return `Fires a **${p.direction === "both" ? "Long/Short" : p.direction}** signal when input A crosses input B.`;
    case "alpha.channel_break":
      return `Fires **Long** when close breaks above the upper line, **Short** when it breaks below the lower line.${p.direction !== "both" ? ` (Direction limited to ${p.direction}.)` : ""}`;
    case "alpha.threshold":
      return `Fires **Long** when the input crosses up through **${p.long_level}**, **Short** when it crosses down through **${p.short_level}**.${p.direction !== "both" ? ` (Direction limited to ${p.direction}.)` : ""}`;
    case "alpha.engulfing":
      return `Fires on **engulfing candle patterns** (bullish or bearish body covers the prior bar).`;
    case "alpha.fvg":
      return `Fires when a **Fair Value Gap** of at least **${p.min_pips} pips** appears between bar n-2 and current.`;
    case "alpha.liquidity_sweep":
      return `Fires when **${p.count}+ equal highs/lows** form within ${p.lookback} bars, then a candle **wicks past them** (≥${p.min_pierce_pips} pips) and **closes back inside** — the SMC liquidity grab signal.${p.direction !== "both" ? ` (Direction limited to ${p.direction}.)` : ""}`;
    case "alpha.combine_and":
      return `Fires **only when both** wired insights agree (same direction, same bar).`;
    case "alpha.combine_or":
      return `Fires when **either** wired insight fires.`;

    // ── Filter ──────────────────────────────────────────────────────────
    case "filter.session":
      return `Blocks insights outside hours **${p.start_hour}:00 – ${p.end_hour}:00** (server local time).`;
    case "filter.threshold":
      return `Pass-through only when the wired value is **between ${p.min} and ${p.max}**.`;
    case "filter.cooldown":
      return `Blocks new insights for **${p.bars} bars** after one fires.`;

    // ── Sizing ──────────────────────────────────────────────────────────
    case "sizing.fixed_pct":
      return `Risks **${p.risk_pct}%** of equity per trade.`;
    case "sizing.atr_target":
      return `Sizes so a **${p.atr_mult}×ATR** move equals **${p.risk_pct}%** of equity (volatility-normalized).`;
    case "sizing.vol_parity":
      return `Sizes to target **${p.target_vol_pct}% annualized vol**, scaling down in volatile regimes.`;

    // ── Risk ────────────────────────────────────────────────────────────
    case "risk.fixed_pips":
      return `Initial stop **${p.pips} pips** from entry.`;
    case "risk.atr_stop":
      return `Initial stop **${p.mult}×ATR** from entry.`;
    case "risk.structure_stop":
      return `Initial stop **just beyond the wired swing point** (buffer ${p.buf_pips} pips).`;

    // ── Exit ────────────────────────────────────────────────────────────
    case "exit.target_and_trail":
      return `At **${p.target_r}R**, close **${Math.round(p.close_pct * 100)}%** of the position. ` +
             `${p.trail_mode === "none" ? "No trailing." : `Trail the rest using **${p.trail_mode}** mode (buffer ${p.trail_buf} pips).`}`;
    case "exit.breakeven_at_r":
      return `Move stop to **break-even** when price reaches **${p.be_at_r}R** in favor.`;
    case "exit.time_exit":
      return `Force close the trade after **${p.bars} bars** in trade.`;

    // ── Execution ───────────────────────────────────────────────────────
    case "execution.market":
      return `Submit as a **market/limit order** at the entry price (expires after ${p.expiry_bars} bars).`;
    case "execution.limit_at":
      return `Place a **limit at the wired price** (expires after ${p.expiry_bars} bars).`;
    case "execution.costs":
      return `Apply real execution costs: **${p.slippage_pips} pip slippage** on exits, ` +
             `**${p.spread_pips} pip spread** on entries, **$${p.commission}/trade** commission.`;
  }
  return `**${spec.label}**.`;
}


// Structural problems we can detect with the current graph alone.
type Issue = { severity: "error" | "warn" | "info"; text: string };

function findIssues(
  nodes: V2GraphNode[],
  edges: V2GraphEdge[],
  library: V2NodeSpec[],
): Issue[] {
  const specByType = Object.fromEntries(library.map((s) => [s.type, s]));
  const out: Issue[] = [];

  if (nodes.length === 0) return [{ severity: "info", text: "Canvas is empty — drop some nodes from the palette." }];

  // 1) Required inputs that aren't wired
  const wiredInputs = new Set(edges.map((e) => `${e.to}::${e.to_port}`));
  for (const n of nodes) {
    const spec = specByType[n.type];
    if (!spec) continue;
    for (const inp of spec.inputs) {
      if (!wiredInputs.has(`${n.id}::${inp.name}`)) {
        out.push({
          severity: "error",
          text: `**${spec.label}** is missing its required input \`${inp.name}\` (${inp.type}). The strategy can't run until this is wired.`,
        });
      }
    }
  }

  // 2) No execution sink
  const sinks = nodes.filter((n) => specByType[n.type]?.lane === "execution");
  if (sinks.length === 0) {
    out.push({ severity: "error", text: "No **Execution** node. Add one (e.g., Market order) so trades can actually fire." });
  }

  // 3) No alpha node
  const alphas = nodes.filter((n) => specByType[n.type]?.lane === "alpha");
  if (alphas.length === 0) {
    out.push({ severity: "error", text: "No **Alpha** node. You need at least one signal source to know when to enter." });
  }

  // 4) Indicators that nobody is reading
  const usedSources = new Set(edges.map((e) => e.from));
  for (const n of nodes) {
    const spec = specByType[n.type];
    if (spec?.lane === "indicator" && !usedSources.has(n.id)) {
      out.push({
        severity: "warn",
        text: `**${spec.label}** isn't wired into anything — it computes but no other node consumes it.`,
      });
    }
  }

  // 5) Multiple alphas without a combiner — might be intentional but worth flagging
  const alphaIds = new Set(alphas.map((a) => a.id));
  const alphaConsumers = edges.filter((e) => alphaIds.has(e.from)).map((e) => e.to);
  const combineIds = new Set(
    nodes.filter((n) => n.type === "alpha.combine_and" || n.type === "alpha.combine_or").map((n) => n.id)
  );
  if (alphas.length > 1 && !alphaConsumers.some((id) => combineIds.has(id))) {
    out.push({
      severity: "warn",
      text: "You have multiple **Alpha** nodes but no Combine (AND/OR) joining them. Each will fire independently — that's fine if intended, but often you want them combined.",
    });
  }

  if (out.length === 0) {
    out.push({ severity: "info", text: "Looks structurally sound. Hit **Run backtest** to see how it performs." });
  }
  return out;
}


export function StrategyLogicBox({
  nodes, edges, library, collapsed, onToggle,
}: {
  nodes:     V2GraphNode[];
  edges:     V2GraphEdge[];
  library:   V2NodeSpec[];
  collapsed: boolean;
  onToggle:  () => void;
}) {
  const specByType = Object.fromEntries(library.map((s) => [s.type, s]));

  // Order nodes by lane order, so the description reads top-to-bottom
  const laneOrder = ["universe", "indicator", "alpha", "filter", "sizing", "risk", "exit", "execution"];
  const sorted = [...nodes].sort((a, b) => {
    const la = laneOrder.indexOf(specByType[a.type]?.lane ?? "z");
    const lb = laneOrder.indexOf(specByType[b.type]?.lane ?? "z");
    return la - lb;
  });

  const issues = findIssues(nodes, edges, library);
  const hasErrors = issues.some((i) => i.severity === "error");

  return (
    <div className="rounded-xl border border-border bg-cream2 overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-cream transition-colors"
      >
        <span className="text-sage">📖</span>
        <span className="text-sm font-semibold">Strategy logic</span>
        <span className="text-[10px] text-muted">— what your graph actually does</span>
        {hasErrors && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-terra/15 text-terra font-medium">
            {issues.filter((i) => i.severity === "error").length} problem{issues.filter((i) => i.severity === "error").length === 1 ? "" : "s"}
          </span>
        )}
        <div className="flex-1" />
        <span className="text-muted text-xs">{collapsed ? "▾ Show" : "▴ Hide"}</span>
      </button>

      {!collapsed && (
        <div className="px-4 pb-4 border-t border-border">
          {/* English description */}
          <div className="mt-3">
            <div className="text-[10px] uppercase tracking-widest text-muted mb-2">In plain English</div>
            {sorted.length === 0 ? (
              <p className="text-xs text-muted italic">No nodes yet.</p>
            ) : (
              <ol className="space-y-1.5">
                {sorted.map((n, idx) => {
                  const spec = specByType[n.type];
                  if (!spec) return null;
                  return (
                    <li key={n.id} className="flex gap-2 text-xs leading-relaxed">
                      <span className="shrink-0 w-4 h-4 rounded-full bg-cream border border-border text-[9px] flex items-center justify-center font-mono text-muted mt-0.5">
                        {idx + 1}
                      </span>
                      <span
                        dangerouslySetInnerHTML={{
                          __html: describeNode(n, spec).replace(
                            /\*\*(.+?)\*\*/g,
                            '<strong class="text-ink">$1</strong>'
                          ),
                        }}
                      />
                    </li>
                  );
                })}
              </ol>
            )}
          </div>

          {/* Issues */}
          <div className="mt-4">
            <div className="text-[10px] uppercase tracking-widest text-muted mb-2">Validation</div>
            <ul className="space-y-1.5">
              {issues.map((iss, i) => (
                <li key={i} className="flex gap-2 text-xs leading-relaxed">
                  <span className={
                    iss.severity === "error" ? "text-terra" :
                    iss.severity === "warn"  ? "text-amber-900" :
                                               "text-sage"
                  }>
                    {iss.severity === "error" ? "✗" : iss.severity === "warn" ? "⚠" : "✓"}
                  </span>
                  <span
                    dangerouslySetInnerHTML={{
                      __html: iss.text.replace(/\*\*(.+?)\*\*/g, '<strong class="text-ink">$1</strong>')
                                       .replace(/`(.+?)`/g, '<code class="font-mono text-[11px] bg-cream px-1 rounded">$1</code>'),
                    }}
                  />
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
