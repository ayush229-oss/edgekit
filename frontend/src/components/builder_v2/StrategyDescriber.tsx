"use client";

/**
 * Plain-English → starter graph.
 *
 * Modal opened from the toolbar's "Describe strategy" button. User types
 * a free-form description; we match keywords against the catalog of starter
 * templates, then preview the best match with bullet-point explanations of
 * each node and WHY it's there. User clicks "Use this graph" to load it.
 *
 * v1 is heuristic — small library of templates, keyword scoring.
 * v2 can plug in an LLM behind the same interface.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import { v2GetTemplate, v2FromText, hasUserAIKey, type V2Graph } from "@/lib/api";


// Each template has a list of keywords + the bullet explanation that runs
// after a match. Keywords are matched case-insensitively against the user's
// description. Higher hit count wins; ties go to declaration order.
type TemplateMatch = {
  templateId:  string;
  name:        string;
  keywords:    string[];
  why:         string;          // 1-line "why we picked this"
  bullets:     { node: string; explanation: string }[];
};

const MATCHES: TemplateMatch[] = [
  {
    templateId: "donchian_breakout_v2",
    name:       "Donchian breakout",
    keywords:   ["donchian", "channel", "breakout", "n-day high", "n-bar high", "20 day high",
                 "highest high", "trend follow", "trend-follow", "turtle", "break out"],
    why:        "Your description mentions a price break above (or below) recent highs/lows — that's a Donchian channel breakout.",
    bullets: [
      { node: "Universe — Single asset (XAUUSD)",   explanation: "We're trading one instrument on M15. Change later if you want a different symbol or timeframe." },
      { node: "Indicator — Donchian channel (20)",  explanation: "Tracks the highest high and lowest low over the last 20 bars, excluding the current bar. This is your breakout level." },
      { node: "Indicator — ATR (14)",               explanation: "Average True Range — used by Sizing (how big) and Risk (where the SL goes). One ATR feeds both downstream lanes." },
      { node: "Alpha — Channel break",              explanation: "Fires Long when close crosses above the upper line, Short when it crosses the lower line. This is the trade idea." },
      { node: "Sizing — ATR target (1% / 2×ATR)",   explanation: "Sizes the position so a 2-ATR move equals 1% of your equity. Bigger ATR = smaller position. This normalizes risk across volatile vs calm markets." },
      { node: "Risk — ATR stop (×2)",               explanation: "Initial stop is placed 2×ATR away from entry. Same multiplier as sizing keeps the math clean." },
      { node: "Exit — Target + trail (3R / 50% / candle)", explanation: "When price reaches 3×risk, take 50% off the table. The remaining 50% trails behind each candle's low — letting winners run." },
      { node: "Execution — Market",                 explanation: "Submit as a limit at the current close. The simulator fills when price touches." },
    ],
  },
  {
    templateId: "ema_cross_v2",
    name:       "EMA crossover",
    keywords:   ["ema", "moving average", "ma cross", "ema cross", "20 50", "fast slow",
                 "golden cross", "death cross", "sma", "crossover"],
    why:        "Your description sounds like a moving-average crossover — that's the simplest trend-following setup.",
    bullets: [
      { node: "Universe — Single asset (XAUUSD)",   explanation: "One instrument, M15 timeframe. Adjustable." },
      { node: "Indicator — EMA (20)",               explanation: "Fast moving average. Reacts quickly to price." },
      { node: "Indicator — EMA (50)",               explanation: "Slow moving average. Smooth, lagging." },
      { node: "Alpha — Crossover",                  explanation: "Long when fast crosses above slow, Short when fast crosses below. This is the entry trigger." },
      { node: "Sizing — Fixed % (1%)",              explanation: "Each trade risks 1% of equity. Simpler than ATR-based — same dollar risk every trade." },
      { node: "Risk — Fixed pips (30)",             explanation: "Initial SL is 30 pips from entry. You can wire an indicator here later if you want adaptive stops." },
      { node: "Exit — Target + trail",              explanation: "Hit 3R → close half, trail the rest behind candle wicks." },
      { node: "Execution — Market",                 explanation: "Fills at the next bar that touches the entry price." },
    ],
  },
  {
    templateId: "turtle_system_1",
    name:       "Turtle Trading (System 1)",
    keywords:   ["turtle", "turtles", "richard dennis", "curtis faith", "system 1",
                 "20-day breakout", "20 day breakout", "trend following classic"],
    why:        "Turtle / Dennis / 20-day breakout in your description — Curtis Faith's System 1, the textbook trend-following rules.",
    bullets: [
      { node: "Universe — Single asset (XAUUSD H1)",        explanation: "Turtles ran across many futures markets; we apply the same rules to one symbol. H1 is a reasonable analog for daily on intraday data." },
      { node: "Indicator — Donchian channel (20)",          explanation: "20-bar high / 20-bar low channel. The breakout is the signal." },
      { node: "Indicator — ATR (20)",                       explanation: "Turtles called this 'N' — the unit of volatility. Used by both sizing and stops." },
      { node: "Alpha — Channel break",                      explanation: "Enter Long on close above the 20-bar high; Short below the 20-bar low. No filters, no confirmation — pure breakout." },
      { node: "Sizing — ATR target (1% / 2N)",              explanation: "Position size = (1% of equity) / (2N). Volatile markets get smaller positions, calm markets get larger ones — risk normalized." },
      { node: "Risk — ATR stop (2N)",                       explanation: "Initial stop is 2N (2 × ATR) away from entry. Same N used for sizing keeps the math consistent: a stopped-out trade always loses exactly 1%." },
      { node: "Exit — Target 8R / 0% close / candle trail", explanation: "Turtles exited on a 10-bar opposite-channel break. We approximate with a candle-based trail (rides until a real reversal). Effectively no fixed target — let winners run." },
      { node: "Execution — Market",                         explanation: "Submit on the breakout bar." },
    ],
  },
  {
    templateId: "livermore_pivot",
    name:       "Livermore Pivot break",
    keywords:   ["livermore", "jesse livermore", "pivot", "pivotal point", "reminiscences",
                 "tape reading", "tape", "stock operator"],
    why:        "Livermore / pivotal points / tape reading — buy when price breaks above a recent high, sell when it breaks below a recent low. The original swing-trading formula.",
    bullets: [
      { node: "Universe — Single asset (XAUUSD H1)",   explanation: "Livermore traded daily; H1 is the modern intraday equivalent." },
      { node: "Indicator — Price (close)",             explanation: "Exposes raw close as a wire so we can compare it to the pivot levels." },
      { node: "Indicator — Swing high (20)",           explanation: "Rolling 20-bar high — the resistance / 'pivotal point' to break for a long." },
      { node: "Indicator — Swing low (20)",            explanation: "Rolling 20-bar low — the support pivot for a short." },
      { node: "Alpha — Crossover (close vs swing high, long only)", explanation: "Fires Long when close crosses above the 20-bar high. 'Buy strength.'" },
      { node: "Alpha — Crossover (close vs swing low, short only)", explanation: "Fires Short when close crosses below the 20-bar low. 'Sell weakness.'" },
      { node: "Alpha — Combine (OR)",                  explanation: "Either side firing triggers a trade. Both alphas can't fire on the same bar, so no conflict." },
      { node: "Indicator — ATR (14)",                  explanation: "Volatility unit for sizing + stops." },
      { node: "Sizing — ATR target (0.75% / 1.5N)",    explanation: "Slightly more conservative than Turtle defaults — Livermore was disciplined about position size." },
      { node: "Risk — ATR stop (1.5N)",                explanation: "Initial stop at 1.5 ATR. Tighter than Turtles because pivot breaks should follow through quickly." },
      { node: "Exit — 3R / 50% / candle trail",        explanation: "Take half off at 3R, trail the rest. Livermore: 'the big money is made in the sitting'." },
      { node: "Execution — Market",                    explanation: "Enter on the break bar." },
    ],
  },
  {
    templateId: "ichimoku_tk_cross",
    name:       "Ichimoku TK Cross",
    keywords:   ["ichimoku", "tk cross", "tenkan", "kijun", "kumo", "cloud",
                 "kinko hyo", "peloille"],
    why:        "Ichimoku / Tenkan / Kijun / Kumo — the classical Japanese 5-line system. The simplest entry is the TK cross.",
    bullets: [
      { node: "Universe — Single asset (XAUUSD H1)",         explanation: "Ichimoku works best on H1+ timeframes." },
      { node: "Indicator — Ichimoku (9 / 26 / 52)",          explanation: "Standard parameters. Outputs Tenkan (fast), Kijun (slow), Senkou A & B (the cloud boundaries)." },
      { node: "Alpha — Crossover (Tenkan vs Kijun)",         explanation: "Fires Long when Tenkan crosses above Kijun, Short when it crosses below. The TK cross — Ichimoku's most reliable signal." },
      { node: "Indicator — ATR (14) + Sizing + Risk",        explanation: "Volatility-normalized sizing and 1.5N stop. Cleaner than pip-based stops in a system this systematic." },
      { node: "Exit — 3R / 50% / candle trail",              explanation: "Standard exit. Kijun is sometimes used as a trailing reference — could replace with structure_stop wired to the Kijun for more orthodox Ichimoku exits." },
      { node: "Execution — Market",                          explanation: "Enter on TK cross bar." },
    ],
  },
  {
    templateId: "smc_fvg_v2",
    name:       "SMC: Sweep + Order Block (long + short)",
    keywords:   ["smc", "smart money", "fvg", "fair value gap", "order block", "ob",
                 "liquidity", "sweep", "imbalance", "structure", "bos", "choch",
                 "displacement", "premium", "discount", "stop hunt", "liquidity grab",
                 "equal highs", "equal lows", "poi", "point of interest"],
    why:        "SMC / liquidity / order block — the real playbook in BOTH directions. Liquidity must be SWEPT first, then enter into the order block that caused the move. Each direction has its own OB + SL + exit chain because the OB is direction-specific (last bearish candle = Bull OB; last bullish candle = Bear OB).",
    bullets: [
      { node: "Shared — Universe (XAUUSD M15) + ATR (14)",          explanation: "Both long and short chains share the same data and volatility reference. Saves recomputing ATR twice." },
      // Long chain
      { node: "LONG — Order Block (long, scan 3–15 bars)",          explanation: "Finds the most recent BEARISH candle in the last 3–15 bars (the Bull OB). High/low/midpoint feed downstream." },
      { node: "LONG — Liquidity sweep (long, equal lows)",          explanation: "Fires when 2+ equal lows form within 30 bars, then a candle wicks BELOW them but closes BACK ABOVE. The bull liquidity grab." },
      { node: "LONG — Session + ATR floor filters",                 explanation: "Only allow long setups in London/NY (07-17) when ATR > 0.2 — real displacement, not chop." },
      { node: "LONG — Sizing 1% + Risk (SL below OB low + 3 pips)", explanation: "Risk 1% of equity. SL goes below the Bull OB's low — if violated, the order block is dead." },
      { node: "LONG — Stacked exits (3R/50% + BE@1R + 40-bar timeout)", explanation: "Half off at 3R then trail behind candle lows. Move to break-even at 1R. Force-close after 40 bars in trade." },
      { node: "LONG — LIMIT at Bull OB midpoint (10-bar expiry)",   explanation: "Place limit at the OB midpoint and wait for retrace. If price doesn't return in 10 bars, the setup expires unfilled — no harm." },
      // Short chain
      { node: "SHORT — Order Block (short, scan 3–15 bars)",        explanation: "Finds the most recent BULLISH candle in the last 3–15 bars (the Bear OB). This is a different OB — its HIGH is the structural reference for the short's SL." },
      { node: "SHORT — Liquidity sweep (short, equal highs)",       explanation: "Fires when 2+ equal highs form within 30 bars, then a candle wicks ABOVE them but closes BACK BELOW. The bear liquidity grab." },
      { node: "SHORT — Session + ATR floor filters",                explanation: "Same gates as the long chain — separate filter nodes because each chain handles its own insight independently." },
      { node: "SHORT — Sizing 1% + Risk (SL above OB high + 3 pips)", explanation: "Risk 1%. SL goes ABOVE the Bear OB's high — the mirror image of the long-side stop." },
      { node: "SHORT — Stacked exits + LIMIT at Bear OB midpoint",  explanation: "Mirrored exit stack. Limit entry at the Bear OB midpoint, expires in 10 bars." },
    ],
  },
  {
    templateId: "rsi_bb_rich",
    name:       "RSI mean-reversion (filtered)",
    keywords:   ["rsi", "oversold", "overbought", "mean revers", "mean-revers", "reversion",
                 "bounce", "exhaustion", "bollinger", "bb"],
    why:        "RSI / oversold / mean-reversion in your description — buy weakness, sell strength, but only when the trend is alive.",
    bullets: [
      { node: "Universe — Single asset",            explanation: "XAUUSD M15 by default." },
      { node: "Indicator — RSI (14)",               explanation: "0–100 momentum oscillator. <30 = oversold, >70 = overbought." },
      { node: "Indicator — ADX (14)",               explanation: "Trend strength. We'll use this to skip flat markets where mean-reversion gets chopped up." },
      { node: "Indicator — Swing low (10)",         explanation: "Lowest low of the last 10 bars. Used as the structural stop." },
      { node: "Alpha — Threshold cross",            explanation: "Long when RSI crosses up through 30 (oversold bounce)." },
      { node: "Filter — ADX > 20",                  explanation: "Block setups when ADX is below 20 (sideways market). Mean-reversion works best in mild trends." },
      { node: "Filter — Cooldown (20 bars)",        explanation: "Block new setups for 20 bars after the last one. Prevents stacking trades in a noisy zone." },
      { node: "Risk — Structure stop",              explanation: "SL goes below the most recent swing low — uses real price structure instead of an arbitrary distance." },
      { node: "Exit — Target + trail + BE + time",  explanation: "Stacked exits: 2.5R partial → break-even at 1R MFE → force close after 60 bars if neither has fired." },
      { node: "Execution — Market",                 explanation: "Fast fill." },
    ],
  },
];


export function StrategyDescriber({
  open, onClose, onLoadGraph, symbol = "XAUUSD", timeframe = "M15",
}: {
  open:        boolean;
  onClose:     () => void;
  onLoadGraph: (g: V2Graph, name: string) => void;
  symbol?:     string;
  timeframe?:  string;
}) {
  const [text, setText]       = useState("");
  const [image, setImage]     = useState<string | null>(null);   // data URL of a reference image
  const [match, setMatch]     = useState<TemplateMatch | null>(null);
  const [busy, setBusy]       = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [usedAI, setUsedAI]   = useState(false);
  const [noMatch, setNoMatch] = useState(false);
  const [hasKey, setHasKey]   = useState(false);

  useEffect(() => {
    if (open) setHasKey(hasUserAIKey());
  }, [open]);

  if (!open) return null;

  // Read a dropped/pasted/selected image File into a base64 data URL.
  function readImage(file: File | null | undefined) {
    if (!file || !file.type.startsWith("image/")) return;
    if (file.size > 5 * 1024 * 1024) { setAiError("Reference image too large (max 5 MB)."); return; }
    const reader = new FileReader();
    reader.onload = () => setImage(reader.result as string);
    reader.readAsDataURL(file);
  }

  function fallbackKeywordMatch(): TemplateMatch | null {
    const lc = text.toLowerCase();
    let best: TemplateMatch | null = null;
    let bestScore = 0;
    for (const t of MATCHES) {
      const hits = t.keywords.filter((kw) => lc.includes(kw)).length;
      if (hits > bestScore) { best = t; bestScore = hits; }
    }
    return best;
  }

  // Primary path: ask the AI to build a custom graph from the user's words.
  // Fallback: keyword match against the starter templates (so the feature still
  // works locally if ANTHROPIC_API_KEY isn't configured on the server).
  async function describe() {
    if (!text.trim() && !image) return;
    setBusy(true); setAiError(null); setMatch(null); setUsedAI(false); setNoMatch(false);
    try {
      const g = await v2FromText({ description: text, symbol, timeframe, image: image ?? undefined });
      onLoadGraph(g, g.name || "AI strategy");
      setUsedAI(true);
      onClose();
    } catch (e: any) {
      // AI unavailable — show the keyword-matched template instead, so the user
      // still gets something useful. If no template keyword matches either,
      // surface that clearly so the modal isn't dead.
      setAiError(e?.message ?? String(e));
      const km = fallbackKeywordMatch();
      if (km) setMatch(km);
      else    setNoMatch(true);
    } finally {
      setBusy(false);
    }
  }

  async function useGraph() {
    if (!match) return;
    setBusy(true);
    try {
      const g = await v2GetTemplate(match.templateId);
      onLoadGraph(g, match.name);
      onClose();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-cream/95 backdrop-blur-sm flex items-center justify-center p-6">
      <div className="bg-cream2 border border-border rounded-2xl p-6 max-w-3xl w-full shadow-xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between mb-2">
          <div>
            <h2 className="text-xl font-semibold">✨ Describe your strategy</h2>
            <p className="text-xs text-muted mt-1">
              Write your idea in plain English — and optionally attach a chart screenshot
              as reference. AI builds a custom node graph for you, then you fine-tune on the canvas.
            </p>
          </div>
          <button onClick={onClose} className="text-muted hover:text-ink text-xl leading-none">×</button>
        </div>

        {!hasKey && (
          <div className="mt-3 rounded-md bg-amber/10 border border-amber/40 p-3 text-xs">
            <div className="font-semibold text-amber-900 mb-1">⚠ AI not configured — limited mode</div>
            <p className="text-muted leading-snug">
              Without an AI key, only descriptions matching one of the 7 starter templates will work
              (Donchian, EMA cross, Ichimoku, SMC, RSI+Bollinger, Turtle, Livermore). Novel ideas will fail.
            </p>
            <p className="text-muted leading-snug mt-1.5">
              Add your key (Gemini, Claude, OpenAI, Groq…) under{" "}
              <Link href="/resources" className="text-money underline font-medium" onClick={onClose}>
                Resources → AI Model
              </Link>
              {" "}to unlock custom graph generation for anything.
            </p>
          </div>
        )}

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onPaste={(e) => {
            const item = Array.from(e.clipboardData.items).find((i) => i.type.startsWith("image/"));
            if (item) { const f = item.getAsFile(); if (f) { readImage(f); } }
          }}
          placeholder={`e.g. "Buy when RSI crosses up through 30 in a strong trend, exit at 2R or trail behind structure."

Or: "Donchian channel breakout on 20-day high, ATR-based stops."

Tip: attach a chart screenshot (or paste one) as a reference — the AI will read it.`}
          className="w-full h-32 mt-3 rounded-md bg-cream border border-border px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-sage"
        />

        {/* Reference image: attach a chart screenshot / hand-drawn setup. */}
        <div className="mt-2 flex items-center gap-3">
          {image ? (
            <div className="relative">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={image} alt="reference" className="h-16 w-auto rounded-md border border-border object-cover" />
              <button
                onClick={() => setImage(null)}
                title="Remove image"
                className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-ink text-cream2 text-xs leading-none flex items-center justify-center shadow">
                ×
              </button>
            </div>
          ) : (
            <label className="text-xs px-3 py-1.5 rounded-md border border-border bg-cream hover:bg-cream2 cursor-pointer text-muted">
              🖼 Attach chart image
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                onChange={(e) => { readImage(e.target.files?.[0]); e.currentTarget.value = ""; }}
              />
            </label>
          )}
          <span className="text-[11px] text-muted">
            {image ? "Reference attached — the AI will read it." : "Optional — paste or upload a screenshot (max 5 MB)."}
          </span>
        </div>

        <div className="flex justify-end gap-2 mt-3">
          <button onClick={describe} disabled={(!text.trim() && !image) || busy}
            className="text-sm px-4 py-1.5 rounded-md bg-sage text-cream2 font-medium hover:bg-sageMid disabled:opacity-50">
            {busy ? "Generating with AI…" : "✨ Build my graph"}
          </button>
        </div>

        {aiError && match && (
          <div className="mt-4 rounded-md bg-amber/10 border border-amber/40 p-3 text-xs text-amber-900">
            <div className="font-semibold mb-1">AI unavailable — matched a template instead.</div>
            <div className="text-muted text-[11px]">{aiError}</div>
          </div>
        )}

        {noMatch && (
          <div className="mt-4 rounded-md bg-down/5 border border-down/30 p-4 text-xs">
            <div className="font-semibold text-down mb-1.5">❌ Couldn't build a graph from this description</div>
            <p className="text-muted leading-relaxed mb-2">
              The AI is disabled (no Gemini API key on the server) so we fell back to keyword matching —
              but your description didn't mention any indicators or strategies we recognize.
            </p>
            <div className="text-muted leading-relaxed">
              <strong className="text-ink">Two ways to fix this:</strong>
              <ul className="list-disc list-inside mt-1.5 space-y-0.5">
                <li>
                  Add a free Gemini API key under{" "}
                  <Link href="/resources" className="text-money underline font-medium" onClick={onClose}>
                    Resources → AI Model
                  </Link>
                  {" "}— unlocks any description
                </li>
                <li>
                  Or rephrase using template keywords: <em>donchian, EMA cross, RSI, Bollinger,
                  Ichimoku, SMC / order block, turtle, Livermore pivot</em>
                </li>
              </ul>
            </div>
            <div className="mt-2 pt-2 border-t border-down/20 text-[11px] text-muted font-mono">
              Server said: {aiError}
            </div>
          </div>
        )}

        {match && (
          <div className="mt-5">
            <div className="rounded-md bg-sage/10 border border-sage/30 p-3 mb-3">
              <div className="text-[10px] uppercase tracking-widest text-sage mb-1">Matched</div>
              <div className="font-semibold">{match.name}</div>
              <p className="text-xs text-muted mt-1 italic">{match.why}</p>
            </div>

            <div className="text-[10px] uppercase tracking-widest text-muted mb-2">
              How this graph is wired
            </div>
            <ol className="space-y-2.5">
              {match.bullets.map((b, i) => (
                <li key={i} className="flex gap-3 text-sm">
                  <span className="shrink-0 w-5 h-5 rounded-full bg-cream border border-border text-[10px] flex items-center justify-center font-mono text-muted mt-0.5">
                    {i + 1}
                  </span>
                  <div>
                    <div className="font-medium text-sm">{b.node}</div>
                    <div className="text-xs text-muted leading-snug mt-0.5">{b.explanation}</div>
                  </div>
                </li>
              ))}
            </ol>

            <div className="flex justify-end gap-2 mt-5">
              <button onClick={() => setMatch(null)}
                className="text-xs px-3 py-1.5 rounded border border-border hover:bg-cream">
                Try again
              </button>
              <button onClick={useGraph} disabled={busy}
                className="text-sm px-4 py-1.5 rounded-md bg-sage text-cream2 font-medium hover:bg-sageMid disabled:opacity-50">
                {busy ? "Loading…" : "Use this graph"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
