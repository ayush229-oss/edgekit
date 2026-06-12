"use client";

/**
 * Contextual suggestions sidebar for StrategyChat and NodeBuilder.
 * Scans messages for keywords and surfaces clickable quick-prompts.
 */
import { useMemo } from "react";

type Suggestion = { label: string; text: string };

const TOPIC_SUGGESTIONS: { keywords: string[]; suggestions: Suggestion[] }[] = [
  {
    keywords: ["rsi", "relative strength"],
    suggestions: [
      { label: "RSI oversold signal",   text: "Generate Bull signal when RSI drops below 30" },
      { label: "RSI overbought filter", text: "Filter to only pass signals when RSI is not overbought (below 70)" },
      { label: "RSI divergence",        text: "Detect bullish divergence: price makes lower low but RSI makes higher low" },
    ],
  },
  {
    keywords: ["ema", "exponential moving average", "moving average", "ma cross"],
    suggestions: [
      { label: "EMA crossover signal", text: "Go long when fast EMA (8) crosses above slow EMA (21)" },
      { label: "Price vs EMA filter",  text: "Only take long trades when price is above EMA 200" },
      { label: "EMA ribbon",           text: "Use EMA 20 and EMA 50 — trade in the direction they're aligned" },
    ],
  },
  {
    keywords: ["atr", "average true range", "volatility", "stop"],
    suggestions: [
      { label: "ATR stop loss",        text: "Set stop loss at 1.5× ATR below entry for longs" },
      { label: "ATR position sizing",  text: "Risk 1% of equity; size position so 1.5× ATR = 1% loss" },
      { label: "Low volatility filter",text: "Only trade when ATR is below its 20-period average (calm market)" },
    ],
  },
  {
    keywords: ["donchian", "breakout", "channel", "high", "low"],
    suggestions: [
      { label: "Donchian breakout",    text: "Go long when price breaks above the 20-bar Donchian high" },
      { label: "Range filter",         text: "Only trade when daily range (high-low) is larger than ATR" },
    ],
  },
  {
    keywords: ["macd", "momentum"],
    suggestions: [
      { label: "MACD signal cross",    text: "Go long when MACD line crosses above the signal line" },
      { label: "Zero-line filter",     text: "Only take longs when MACD histogram is above zero" },
    ],
  },
  {
    keywords: ["filter", "session", "time", "london", "new york", "hour"],
    suggestions: [
      { label: "London session only",  text: "Only trade during London session hours (08:00–16:00 UTC)" },
      { label: "Avoid news hours",     text: "Filter out trades between 12:30–13:30 UTC (US market open)" },
    ],
  },
  {
    keywords: ["sizing", "position", "risk", "percent", "equity"],
    suggestions: [
      { label: "Fixed 1% risk",        text: "Risk exactly 1% of equity on every trade" },
      { label: "Volatility-scaled",    text: "Risk more when ATR is low (calm), less when ATR is high (volatile)" },
    ],
  },
  {
    keywords: ["exit", "target", "take profit", "trail"],
    suggestions: [
      { label: "Fixed 3R target",      text: "Take profit at 3× the risk distance (3R)" },
      { label: "Volatility-adj exit",  text: "Target 3R in calm markets, 2R in high-volatility conditions" },
    ],
  },
  {
    keywords: ["indicator", "custom", "compute", "value", "series"],
    suggestions: [
      { label: "Hull MA",              text: "Create a Hull Moving Average indicator with a period parameter" },
      { label: "Keltner Channel",      text: "Build a Keltner Channel: EMA ± 2×ATR, output upper and lower bands" },
      { label: "VWAP deviation",       text: "Compute how many standard deviations price is from VWAP" },
    ],
  },
];

const FALLBACK_SUGGESTIONS: Suggestion[] = [
  { label: "Momentum entry",     text: "Go long when a fast EMA crosses above a slow EMA" },
  { label: "Mean reversion",     text: "Buy when RSI drops below 30, sell when it rises above 70" },
  { label: "Volatility breakout",text: "Enter long when price breaks above the 20-bar high with strong ATR" },
  { label: "Trend + momentum",   text: "Only take signals in the direction of the EMA 200 trend" },
];

function extractText(messages: { role: string; content: string }[]): string {
  return messages
    .filter((m) => m.role === "user")
    .map((m) => m.content.toLowerCase())
    .join(" ");
}

export function SuggestionsPanel({
  messages,
  onSuggest,
  label = "Suggestions",
}: {
  messages: { role: string; content: string }[];
  onSuggest: (text: string) => void;
  label?: string;
}) {
  const suggestions = useMemo(() => {
    const text = extractText(messages);
    const matched: Suggestion[] = [];
    for (const group of TOPIC_SUGGESTIONS) {
      if (group.keywords.some((k) => text.includes(k))) {
        matched.push(...group.suggestions);
      }
    }
    return matched.length > 0 ? matched.slice(0, 6) : FALLBACK_SUGGESTIONS;
  }, [messages]);

  return (
    <div className="w-52 shrink-0 border-l border-border flex flex-col bg-cream2/50 overflow-hidden">
      <div className="px-3 py-2.5 border-b border-border">
        <span className="text-[10px] uppercase tracking-widest text-muted font-semibold">
          {label}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {suggestions.map((s, i) => (
          <button
            key={i}
            onClick={() => onSuggest(s.text)}
            title={s.text}
            className="w-full text-left px-2.5 py-2 rounded-lg bg-cream border border-border
                       text-[11px] text-ink hover:border-sage hover:bg-sage/5 transition-all
                       leading-snug"
          >
            <div className="font-medium text-[10.5px] text-sage mb-0.5 truncate">{s.label}</div>
            <div className="text-muted line-clamp-2">{s.text}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
