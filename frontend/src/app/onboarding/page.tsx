"use client";
import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { LogoMark } from "@/components/LogoMark";

// ── Step 1 options ────────────────────────────────────────────────────────────
const TRADER_TYPES = [
  {
    id:    "gut",
    label: "I trade on feel — setups I see, patterns I notice",
    sub:   "You take trades but can't fully explain why every time",
    icon:  "🎲",
  },
  {
    id:    "rules",
    label: "I have some rules but I don't follow them consistently",
    sub:   "You know what you should do, but discretion creeps in",
    icon:  "📝",
  },
  {
    id:    "prop",
    label: "I'm trying to pass a prop firm challenge",
    sub:   "FTMO, TFT, MyForexFunds — you need a repeatable edge, fast",
    icon:  "🏆",
  },
];

// ── Step 3 template options ───────────────────────────────────────────────────
const TEMPLATES = [
  {
    id:          "ema_cross",
    name:        "EMA Crossover",
    description: "Buy when the fast EMA crosses above the slow EMA. Classic trend-follower — simple rules, easy to understand.",
    difficulty:  "Beginner",
    style:       "Trend following",
    badge:       "Start here",
    badgeColor:  "bg-money/15 text-money",
  },
  {
    id:          "rsi_mr",
    name:        "RSI Mean Reversion",
    description: "Enter when RSI bounces out of oversold/overbought extremes. Suits lower-volatility sessions.",
    difficulty:  "Intermediate",
    style:       "Mean reversion",
    badge:       "Popular",
    badgeColor:  "bg-sky-100 text-sky-800",
  },
  {
    id:          "ob_fvg_liq",
    name:        "OB + FVG + Liquidity Sweep",
    description: "Smart Money Concepts — sweep equal highs/lows, confirm a Fair Value Gap, enter on the Order Block retrace.",
    difficulty:  "Advanced",
    style:       "SMC / ICT",
    badge:       "Pro setup",
    badgeColor:  "bg-purple-100 text-purple-800",
  },
];

// ── Step 2 copy keyed by trader type ─────────────────────────────────────────
const REALITY: Record<string, { headline: string; points: string[]; stat: { label: string; value: string; sub: string }[] }> = {
  gut: {
    headline: "Gut feel looks like skill — until it isn't.",
    points: [
      "Without a backtest, you have no idea if your edge is real or just recent luck.",
      "Most gut-feel traders have a win rate between 35–45% — they just don't know it.",
      "Prop firms expose this instantly. You get 10 bad trades in a row and you're blown.",
    ],
    stat: [
      { label: "Avg win rate (untested trader)", value: "38%", sub: "based on industry studies" },
      { label: "What you need to be profitable", value: "> 45%", sub: "with 1:2 R:R minimum" },
    ],
  },
  rules: {
    headline: "Inconsistency is the same as having no system.",
    points: [
      "A rule you break when it 'feels wrong' is not a rule — it's a suggestion.",
      "Your backtest results mean nothing if your live execution doesn't match them.",
      "A system you can backtest forces you to define every rule explicitly — no vagueness.",
    ],
    stat: [
      { label: "Performance drop (rules vs discretion)", value: "−23%", sub: "avg across retail traders" },
      { label: "Traders who stick to rules", value: "< 20%", sub: "in live conditions under pressure" },
    ],
  },
  prop: {
    headline: "Most challenges are failed in the first 3 days.",
    points: [
      "The daily loss limit is the killer — one bad session and you're reset.",
      "Prop firms don't care about your best trade. They care about your worst day.",
      "A backtest shows your max daily drawdown before you pay a dollar for the challenge.",
    ],
    stat: [
      { label: "Challenge pass rate (industry avg)", value: "< 10%", sub: "across all prop firms" },
      { label: "Trades lost to daily loss limit", value: "~60%", sub: "of failed challenges" },
    ],
  },
};

export default function OnboardingPage() {
  const router = useRouter();
  const [step,         setStep]         = useState(1);
  const [traderType,   setTraderType]   = useState<string | null>(null);
  const [chosenTpl,    setChosenTpl]    = useState<string | null>(null);

  function finish(templateId: string) {
    if (typeof window !== "undefined") {
      localStorage.setItem("edgekit_onboarded", "1");
    }
    router.push(`/builder?template=${templateId}`);
  }

  function skip() {
    if (typeof window !== "undefined") {
      localStorage.setItem("edgekit_onboarded", "1");
    }
    router.push("/home");
  }

  const reality = traderType ? REALITY[traderType] : null;

  return (
    <div className="min-h-screen bg-paper flex flex-col">
      {/* Nav */}
      <header className="border-b border-border px-6 h-14 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <LogoMark size={24} />
          <span className="font-semibold tracking-tight text-[15px]">Edgekit</span>
        </div>
        <button onClick={skip} className="text-[12px] text-muted hover:text-ink transition-colors">
          Skip setup →
        </button>
      </header>

      {/* Progress dots */}
      <div className="flex items-center justify-center gap-2 pt-8 pb-2">
        {[1, 2, 3, 4].map((s) => (
          <div key={s} className={`h-1.5 rounded-full transition-all ${
            s === step ? "w-6 bg-money" : s < step ? "w-6 bg-money/40" : "w-2 bg-border"
          }`} />
        ))}
      </div>

      <main className="flex-1 flex flex-col items-center justify-center px-6 py-12">

        {/* ── Step 1: Who are you? ────────────────────────────────────── */}
        {step === 1 && (
          <div className="w-full max-w-xl animate-in fade-in slide-in-from-bottom-2 duration-300">
            <p className="text-[11px] uppercase tracking-[0.25em] text-money font-semibold mb-3 text-center">Step 1 of 4</p>
            <h1 className="text-[28px] font-bold tracking-tight text-ink text-center mb-2">
              How do you trade right now?
            </h1>
            <p className="text-muted text-center text-[14px] mb-8">
              Be honest — this helps us show you the right starting point.
            </p>
            <div className="space-y-3">
              {TRADER_TYPES.map((t) => (
                <button
                  key={t.id}
                  onClick={() => { setTraderType(t.id); setStep(2); }}
                  className="w-full text-left p-4 rounded-xl border border-border bg-surface hover:border-money hover:bg-money/5 transition-all group"
                >
                  <div className="flex items-start gap-3">
                    <span className="text-2xl shrink-0">{t.icon}</span>
                    <div>
                      <div className="font-medium text-[14px] text-ink group-hover:text-money transition-colors">{t.label}</div>
                      <div className="text-[12px] text-muted mt-0.5">{t.sub}</div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Step 2: The reality ─────────────────────────────────────── */}
        {step === 2 && reality && (
          <div className="w-full max-w-xl animate-in fade-in slide-in-from-bottom-2 duration-300">
            <p className="text-[11px] uppercase tracking-[0.25em] text-money font-semibold mb-3 text-center">Step 2 of 4</p>
            <h1 className="text-[26px] font-bold tracking-tight text-ink text-center mb-8">
              {reality.headline}
            </h1>

            <div className="space-y-3 mb-6">
              {reality.points.map((p) => (
                <div key={p} className="flex items-start gap-3 p-3 rounded-xl bg-surface border border-border">
                  <span className="text-down shrink-0 mt-0.5">✕</span>
                  <span className="text-[13.5px] text-ink2 leading-snug">{p}</span>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-3 mb-8">
              {reality.stat.map((s) => (
                <div key={s.label} className="rounded-xl border border-border bg-surface p-4 text-center">
                  <div className="text-[28px] font-bold text-ink num">{s.value}</div>
                  <div className="text-[11px] text-muted mt-1">{s.label}</div>
                  <div className="text-[10px] text-muted/70 mt-0.5 italic">{s.sub}</div>
                </div>
              ))}
            </div>

            <div className="rounded-xl border border-money/30 bg-money/5 p-4 mb-8 text-center">
              <p className="text-[14px] text-ink font-medium">Edgekit gives you one thing:</p>
              <p className="text-[13px] text-muted mt-1">
                An honest answer about whether your strategy has an edge — before you trade it live.
              </p>
            </div>

            <button
              onClick={() => setStep(3)}
              className="w-full btn-primary py-3 text-[15px]"
            >
              Show me how →
            </button>
          </div>
        )}

        {/* ── Step 3: Pick a template ─────────────────────────────────── */}
        {step === 3 && (
          <div className="w-full max-w-2xl animate-in fade-in slide-in-from-bottom-2 duration-300">
            <p className="text-[11px] uppercase tracking-[0.25em] text-money font-semibold mb-3 text-center">Step 3 of 4</p>
            <h1 className="text-[26px] font-bold tracking-tight text-ink text-center mb-2">
              Pick your first strategy to test.
            </h1>
            <p className="text-muted text-center text-[14px] mb-8">
              These are complete, rule-based systems — not signals. Pick one. We'll backtest it together.
            </p>
            <div className="space-y-3">
              {TEMPLATES.map((t) => (
                <button
                  key={t.id}
                  onClick={() => { setChosenTpl(t.id); setStep(4); }}
                  className={`w-full text-left p-5 rounded-xl border transition-all group
                    ${chosenTpl === t.id
                      ? "border-money bg-money/5"
                      : "border-border bg-surface hover:border-money hover:bg-money/5"}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-semibold text-[15px] text-ink group-hover:text-money transition-colors">{t.name}</span>
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${t.badgeColor}`}>{t.badge}</span>
                      </div>
                      <p className="text-[12.5px] text-muted leading-relaxed">{t.description}</p>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="text-[10px] text-muted">{t.difficulty}</div>
                      <div className="text-[10px] text-muted">{t.style}</div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Step 4: Ready ───────────────────────────────────────────── */}
        {step === 4 && chosenTpl && (
          <div className="w-full max-w-xl text-center animate-in fade-in slide-in-from-bottom-2 duration-300">
            <p className="text-[11px] uppercase tracking-[0.25em] text-money font-semibold mb-3">Step 4 of 4</p>
            <div className="text-5xl mb-4">🎯</div>
            <h1 className="text-[28px] font-bold tracking-tight text-ink mb-3">
              You're ready to run your first backtest.
            </h1>
            <p className="text-muted text-[14px] mb-8 max-w-md mx-auto leading-relaxed">
              We'll open the <strong className="text-ink">{TEMPLATES.find(t => t.id === chosenTpl)?.name}</strong> strategy
              in the builder. Hit <strong className="text-ink">Run backtest</strong> — results come back in under 2 seconds.
            </p>

            <div className="rounded-xl border border-border bg-surface p-5 text-left space-y-3 mb-8">
              <div className="text-[12px] text-muted font-medium uppercase tracking-wider">What happens next</div>
              {[
                "The strategy opens pre-wired — entry, filter, stop loss, take profit",
                "Click Run backtest — years of real market data, 2 seconds",
                "See your actual win rate, expectancy, and max drawdown",
                "Tweak a parameter, re-run, compare",
              ].map((s, i) => (
                <div key={s} className="flex items-start gap-3 text-[13px]">
                  <span className="w-5 h-5 rounded-full bg-money/15 text-money flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5">{i + 1}</span>
                  <span className="text-ink2">{s}</span>
                </div>
              ))}
            </div>

            <button
              onClick={() => finish(chosenTpl)}
              className="w-full btn-primary py-3.5 text-[15px] shadow-lift mb-3"
            >
              Open the builder →
            </button>
            <button onClick={skip} className="text-[12px] text-muted hover:text-ink transition-colors">
              Skip and go to dashboard
            </button>
          </div>
        )}

      </main>
    </div>
  );
}
