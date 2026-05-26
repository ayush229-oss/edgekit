"use client";

/**
 * Reads the current backtest result + graph and suggests concrete next tunes.
 * Rules are heuristics keyed off result metrics — same logic any trader would
 * apply after a backtest run.
 */
import type { BacktestResponse, V2GraphNode } from "@/lib/api";


type Suggestion = {
  severity: "green" | "amber" | "red";
  title:    string;
  body:     string;
};


function buildSuggestions(
  result: BacktestResponse,
  nodes:  V2GraphNode[],
): Suggestion[] {
  const m = result.metrics;
  const out: Suggestion[] = [];

  // ── Trade count diagnostics ─────────────────────────────────────────
  if (m.trades < 20) {
    out.push({
      severity: "amber",
      title:    "Sample size is low",
      body:     `Only ${m.trades} trades. Statistically thin — results aren't reliable yet. Loosen your tightest filter: try lowering the Liquidity sweep's count / min_pierce_pips, widening the session window, or shortening the cooldown.`,
    });
  } else if (m.trades > 200) {
    out.push({
      severity: "amber",
      title:    "Overtrading",
      body:     `${m.trades} trades over the sample — probably more noise than edge. Add or tighten a Filter (cooldown bars, ATR floor), or raise the alpha signal's quality threshold.`,
    });
  } else {
    out.push({
      severity: "green",
      title:    "Trade count looks reasonable",
      body:     `${m.trades} trades is a workable sample size.`,
    });
  }

  // ── Profit factor / total R ─────────────────────────────────────────
  if (m.total_r < 0 || m.profit_factor < 1.0) {
    out.push({
      severity: "red",
      title:    "Strategy bleeds money on current params",
      body:     `Total: ${m.total_r.toFixed(1)}R · PF ${m.profit_factor.toFixed(2)}. Either the entry is wrong (loosen / tighten the alpha) OR the exit math is bad (widen target_r, tighten initial stop, or change trail mode). Try toggling trail_mode between 'candle' and 'atr' first — exits are often the biggest lever.`,
    });
  } else if (m.profit_factor < 1.2) {
    out.push({
      severity: "amber",
      title:    "Edge is marginal",
      body:     `PF ${m.profit_factor.toFixed(2)} — barely positive. To strengthen: (1) tighten filters so only top-quality setups pass, (2) raise target_r for bigger winners, (3) check if drawdown is hiding the real risk.`,
    });
  } else {
    out.push({
      severity: "green",
      title:    "Profit factor is healthy",
      body:     `PF ${m.profit_factor.toFixed(2)} on ${m.trades} trades. Validate on a different timeframe or symbol before trusting it.`,
    });
  }

  // ── Win rate vs avg-win/avg-loss ratio ──────────────────────────────
  const rr = m.avg_loss !== 0 ? Math.abs(m.avg_win / m.avg_loss) : 0;
  if (m.wr < 30 && rr < 2.5) {
    out.push({
      severity: "amber",
      title:    "Low WR without compensating R-multiples",
      body:     `WR ${m.wr.toFixed(1)}% with avg-win/avg-loss ${rr.toFixed(2)}x. Either (a) widen the initial stop (risk.atr_stop mult ↑ or risk.structure_stop buf_pips ↑) so fewer trades stop out at -1R, OR (b) raise target_r so winners pay for the losers.`,
    });
  } else if (m.wr > 60 && m.profit_factor < 1.3) {
    out.push({
      severity: "amber",
      title:    "WR is high but R-per-win is small",
      body:     `WR ${m.wr.toFixed(1)}% but PF ${m.profit_factor.toFixed(2)} — winners are small. Raise target_r or lower close_pct on the exit node so more of the position rides the trail.`,
    });
  }

  // ── Drawdown ─────────────────────────────────────────────────────────
  if (Math.abs(m.max_dd) > 30) {
    out.push({
      severity: "amber",
      title:    "Drawdown is heavy",
      body:     `Max DD ${m.max_dd.toFixed(1)}R. Either lower sizing.risk_pct (smaller per-trade bet) or add exit.breakeven_at_r to lock in 'no loss' early. Wide stops + concentrated losing streaks usually drive this.`,
    });
  }

  // ── Exit-type breakdown — too many SLs means signal/stop mismatch ───
  const exits = m.exit_counts || {};
  const sl    = exits["SL"]    || 0;
  const trail = exits["Trail"] || 0;
  const tp1   = exits["TP1"]   || 0;
  const be    = exits["BE"]    || 0;
  const timex = exits["TimeExit"] || 0;
  const total = sl + trail + tp1 + be + timex;
  if (total > 0) {
    const slPct = sl / total;
    if (slPct > 0.70) {
      out.push({
        severity: "red",
        title:    "Stops are getting hit too often",
        body:     `${sl} of ${total} exits are SL (${(slPct*100).toFixed(0)}%). Your stop placement is too tight relative to the entry's natural noise. Try: raise risk.structure_stop buf_pips, or switch risk type to ATR-based with mult 2.0–2.5.`,
      });
    }
    if (trail === 0 && tp1 > 0) {
      out.push({
        severity: "amber",
        title:    "Trail never activates",
        body:     `${tp1} target hits, zero trail exits. Either lower close_pct (so position remains after target) or trail_mode is 'none'. Check the Exit node.`,
      });
    }
    if (timex > total * 0.30) {
      out.push({
        severity: "amber",
        title:    "Lots of time-stop exits",
        body:     `${timex} time-exits (${(timex/total*100).toFixed(0)}%). Trades are dragging without target or trail firing. Either widen the time exit window, or rethink whether the signal actually leads to follow-through.`,
      });
    }
  }

  // ── Unresolved orders ───────────────────────────────────────────────
  if (m.n_unresolved > m.trades * 0.5) {
    out.push({
      severity: "amber",
      title:    "Many setups expire unfilled",
      body:     `${m.n_unresolved} of ${m.n_setups} setups never filled. If using limit_at, increase execution.expiry_bars, OR raise the OB entry_ratio (fills higher in the OB so closer to market).`,
    });
  }

  return out;
}


export function NextStepsPanel({
  result, nodes,
}: {
  result: BacktestResponse | null;
  nodes:  V2GraphNode[];
}) {
  if (!result) return null;
  const suggestions = buildSuggestions(result, nodes);

  return (
    <div className="rounded-xl border border-border bg-cream2 p-4">
      <div className="flex items-center gap-2 mb-3">
        <span>🎯</span>
        <h3 className="text-sm font-semibold">Next steps</h3>
        <span className="text-[10px] text-muted">— what to try next</span>
      </div>
      <ul className="space-y-2.5">
        {suggestions.map((s, i) => (
          <li key={i} className="flex gap-2 text-xs leading-relaxed">
            <span className={
              s.severity === "red"   ? "text-terra" :
              s.severity === "amber" ? "text-amber-900" :
                                       "text-sage"
            }>
              {s.severity === "red" ? "▲" : s.severity === "amber" ? "◆" : "✓"}
            </span>
            <div>
              <div className="font-medium text-ink">{s.title}</div>
              <div className="text-muted leading-snug mt-0.5">{s.body}</div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
