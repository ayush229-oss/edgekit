// Coaching dictionary — per (node.type, param.key), what does raising
// or lowering this parameter actually do to the strategy's behavior?
//
// Keyed as "node.type:param.key". Lookups fall back to a generic message
// if no entry exists. Add more entries as nodes are added — this is the
// single source of truth for "what will this change do" guidance.

export type Effect = { higher: string; lower: string };

export const COACHING: Record<string, Effect> = {
  // ── Indicators ───────────────────────────────────────────────────────
  "indicator.ema:period": {
    higher: "Smoother, slower EMA. Fewer crossover signals, less noise — but also lags.",
    lower:  "More reactive EMA. More crossovers, more noise — catches turns earlier.",
  },
  "indicator.sma:period": {
    higher: "Smoother trend reference. Filters out smaller swings.",
    lower:  "Reactive but choppy. Treats short-term wiggles as trend.",
  },
  "indicator.atr:period": {
    higher: "Smoother volatility estimate; sizing & stops adapt slowly to regime changes.",
    lower:  "Reactive ATR — sizing/stops adjust quickly but bounce around in chop.",
  },
  "indicator.rsi:period": {
    higher: "Smoother RSI. Crosses 30/70 less often — only at real extremes.",
    lower:  "Choppier RSI. More 30/70 crosses, more false signals.",
  },
  "indicator.donchian:period": {
    higher: "Longer-term breakout. Fewer signals; bigger moves expected when they fire.",
    lower:  "Reactive breakout. More signals, more false breakouts in chop.",
  },
  "indicator.bollinger:period": {
    higher: "Wider, smoother bands. Breakouts mean more.",
    lower:  "Bands hug price; more touches but less signal.",
  },
  "indicator.bollinger:mult": {
    higher: "Bands wider apart. Only big moves break through — fewer but stronger signals.",
    lower:  "Bands tight to price. Lots of breaks, low quality.",
  },
  "indicator.adx:period": {
    higher: "Slower trend strength gauge. Lags but filters noise.",
    lower:  "Reactive ADX. Flips quickly between trending and ranging readings.",
  },
  "indicator.order_block:scan_min": {
    higher: "Skip the most recent few candles when looking for the OB — fresher 'reaction' candles are excluded as possible institutional fills.",
    lower:  "Allow OBs from the very recent bars (1-2 back). May pick the reaction candle instead of the institutional one.",
  },
  "indicator.order_block:scan_max": {
    higher: "Allow older OBs to remain valid. May reference stale levels.",
    lower:  "Only fresh OBs (last few bars). Misses good levels in extended moves.",
  },
  "indicator.order_block:entry_ratio": {
    higher: "Limit fills higher in the OB (closer to top). More fills, smaller MFE before SL touch, looser entry.",
    lower:  "Limit fills lower in the OB (closer to bottom / deeper discount). Fewer fills but tighter stop in R-terms — better risk-reward when filled.",
  },

  // ── Alpha ────────────────────────────────────────────────────────────
  "alpha.crossover:direction": {
    higher: "Switching direction changes which side trades. 'both' = long+short, 'long' = longs only.",
    lower:  "Switching direction changes which side trades. 'both' = long+short, 'short' = shorts only.",
  },
  "alpha.threshold:long_level": {
    higher: "Long signal needs a deeper cross — fewer but more committed entries.",
    lower:  "Long fires earlier in the move; more entries, more false starts.",
  },
  "alpha.threshold:short_level": {
    higher: "Short fires later (price more overbought before triggering); fewer entries.",
    lower:  "Short fires earlier; more entries including premature shorts.",
  },
  "alpha.liquidity_sweep:lookback": {
    higher: "Looks further back for equal levels — finds bigger / more 'historic' liquidity pools.",
    lower:  "Only recent liquidity counts. More signals but smaller pools.",
  },
  "alpha.liquidity_sweep:count": {
    higher: "Demands more equal levels to qualify as a real pool. Far fewer but higher-quality sweeps.",
    lower:  "Loose definition — even 2 close highs/lows count. Many signals, lots of noise.",
  },
  "alpha.liquidity_sweep:tolerance_pips": {
    higher: "Wider tolerance — levels within larger range count as 'equal'. More signals.",
    lower:  "Strict — levels must be tightly aligned. Fewer but cleaner setups.",
  },
  "alpha.liquidity_sweep:min_pierce_pips": {
    higher: "Deeper sweep required — more committed reversal needed. Far fewer but stronger signals.",
    lower:  "Shallow wicks count as sweeps. Many setups but lots are noise.",
  },
  "alpha.fvg:min_pips": {
    higher: "Only larger imbalances count. Far fewer FVG signals but each one represents real displacement.",
    lower:  "Tiny gaps count. Many setups, most are insignificant.",
  },

  // ── Filter ───────────────────────────────────────────────────────────
  "filter.session:start_hour": {
    higher: "Start trading later. Skips the early session — usually means avoiding Asia/London open volatility.",
    lower:  "Start earlier. Includes Asian session or pre-market hours; quality typically worse.",
  },
  "filter.session:end_hour": {
    higher: "Trade later. Includes US close — volatility but also chop.",
    lower:  "Cut off earlier. NY-only finish; avoids late-day fatigue moves.",
  },
  "filter.threshold:min": {
    higher: "Tighter floor — fewer signals pass but each has stronger underlying value (e.g. higher ATR).",
    lower:  "Looser — more signals pass, lower quality bar.",
  },
  "filter.threshold:max": {
    higher: "Wider ceiling — almost no filtering on the upper side.",
    lower:  "Tight ceiling — only modest values pass. (Useful for avoiding extreme over-extended states.)",
  },
  "filter.cooldown:bars": {
    higher: "Longer pause between trades. Fewer overlapping setups; misses clustered opportunities.",
    lower:  "Tight cooldown — may stack trades on the same move.",
  },

  // ── Sizing ───────────────────────────────────────────────────────────
  "sizing.fixed_pct:risk_pct": {
    higher: "Bigger position per trade — faster gains, faster losses. Higher drawdowns.",
    lower:  "Smaller position per trade — slower growth, smaller drawdowns. Safer.",
  },
  "sizing.atr_target:risk_pct": {
    higher: "More risk per trade overall — proportionally bigger positions on every setup.",
    lower:  "Less per-trade risk. Compounds slower but draws down less.",
  },
  "sizing.atr_target:atr_mult": {
    higher: "Treats the SL distance as wider for sizing purposes → smaller positions. More conservative.",
    lower:  "Tighter SL assumption → larger positions per trade. More aggressive.",
  },

  // ── Risk (initial stop) ──────────────────────────────────────────────
  "risk.fixed_pips:pips": {
    higher: "Wider SL — fewer SL-outs, higher WR, but bigger dollar loss when stopped.",
    lower:  "Tighter SL — more SL-outs, lower WR, smaller individual losses.",
  },
  "risk.atr_stop:mult": {
    higher: "Wider stop in ATR units. Survives bigger noise but losses are bigger when they happen.",
    lower:  "Tight stop — many SLs from noise, lower WR. Only winners that take off survive.",
  },
  "risk.structure_stop:buf_pips": {
    higher: "More slack beyond the structural level. Less noise sensitivity but late invalidation.",
    lower:  "Tight to structure. Fast invalidation but stopped by minor wicks.",
  },

  // ── Exit ─────────────────────────────────────────────────────────────
  "exit.target_and_trail:target_r": {
    higher: "Demands bigger move before partial-close fires. Fewer winners hit it, but those that do are big.",
    lower:  "Hits target sooner — more 'wins' but each is smaller. Lower R-per-win.",
  },
  "exit.target_and_trail:close_pct": {
    higher: "Take more profit at target (more security). Less position left to ride the trail.",
    lower:  "Take less at target — more position rides the trail. Higher upside on home runs, more give-back on reversals.",
  },
  "exit.target_and_trail:trail_buf": {
    higher: "Trail SL further from price. Survives noise but gives back more when reversal hits.",
    lower:  "Trail tight to price. Locks in gains but gets stopped on small pullbacks.",
  },
  "exit.breakeven_at_r:be_at_r": {
    higher: "Wait longer before moving SL to break-even. More room for the trade to develop; smaller chance of premature BE stop.",
    lower:  "Move to BE sooner. Locks in 'no loss' quickly but kills more trades on retests.",
  },
  "exit.time_exit:bars": {
    higher: "Trades can run longer before forced exit. Lets winners run; ties up capital longer.",
    lower:  "Quick force-close. Prevents drag in chop but cuts winners early.",
  },

  // ── Execution ────────────────────────────────────────────────────────
  "execution.market:expiry_bars": {
    higher: "Pending order valid longer. More fills but possibly stale signals.",
    lower:  "Tight expiry. Only acts on fresh signals; misses retraces.",
  },
  "execution.limit_at:expiry_bars": {
    higher: "Wait longer for the retrace. More fills overall, some on stale ideas.",
    lower:  "Strict — if retrace doesn't happen quickly, cancel. Fewer fills but always fresh.",
  },
};

export function effectFor(nodeType: string, paramKey: string): Effect | null {
  return COACHING[`${nodeType}:${paramKey}`] ?? null;
}
