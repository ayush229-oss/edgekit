"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useState } from "react";

// ── count-up hook ─────────────────────────────────────────────────────────────
function useCountUp(target: number, durationMs = 1400) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    setVal(0);
    const steps = 50;
    const stepDelay = durationMs / steps;
    const stepVal = target / steps;
    let cur = 0;
    const id = setInterval(() => {
      cur += stepVal;
      if (cur >= target) { setVal(target); clearInterval(id); }
      else setVal(Math.floor(cur));
    }, stepDelay);
    return () => clearInterval(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return val;
}

// ── Mock node card — matches NodeCardV2 exactly ───────────────────────────────
interface MockNodeProps {
  label: string;
  lane: string;
  laneColor: string;
  chipClass: string;
  params?: string;
  inputDot?: string;   // port color hex
  outputDot?: string;  // port color hex
  delay: number;
}

function MockNode({ label, lane, laneColor, chipClass, params, inputDot, outputDot, delay }: MockNodeProps) {
  return (
    <motion.div
      className="rounded-xl border-2 bg-surface shadow-soft select-none"
      style={{ borderColor: laneColor, minWidth: 150 }}
      initial={{ opacity: 0, y: 14, scale: 0.85 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay, type: "spring", stiffness: 300, damping: 24 }}
    >
      {/* Lane stripe */}
      <div className="h-1.5 rounded-t-[10px]" style={{ background: laneColor }} />
      {/* Body */}
      <div className="px-3 py-2">
        <span className={`inline-block text-[9px] uppercase tracking-widest px-1.5 py-0.5 rounded font-semibold ${chipClass}`}>
          {lane}
        </span>
        <div className="font-medium text-[13px] mt-1 leading-tight text-ink">{label}</div>
        {params && (
          <div className="font-mono text-[10px] text-muted mt-1 truncate">{params}</div>
        )}
      </div>
      {/* Port row */}
      <div className="px-3 pb-2 pt-0.5 flex justify-between items-center">
        {inputDot
          ? <div className="w-2.5 h-2.5 rounded-full border-2" style={{ background: inputDot, borderColor: inputDot }} />
          : <div />}
        {outputDot
          ? <div className="w-2.5 h-2.5 rounded-full border-2" style={{ background: outputDot, borderColor: outputDot }} />
          : <div />}
      </div>
    </motion.div>
  );
}

// Animated edge line between two nodes (matches ReactFlow animated edge look)
function AnimatedEdge({ x1, y1, x2, y2, delay }: { x1: number; y1: number; x2: number; y2: number; delay: number }) {
  return (
    <motion.line
      x1={`${x1}%`} y1={`${y1}%`} x2={`${x2}%`} y2={`${y2}%`}
      stroke="#6B9B7A" strokeWidth="1.8" strokeDasharray="5 3"
      initial={{ opacity: 0 }}
      animate={{ opacity: 0.8, strokeDashoffset: [0, -24] }}
      transition={{
        opacity: { delay, duration: 0.2 },
        strokeDashoffset: { delay, duration: 0.6, repeat: Infinity, ease: "linear" },
      }}
    />
  );
}

// ── Step 01: Builder Canvas ───────────────────────────────────────────────────

const CANVAS_NODES: MockNodeProps[] = [
  { label: "EMA Cross",   lane: "Indicator", laneColor: "#5A8DEE", chipClass: "bg-sky-100 text-sky-800",          params: "period=20",      inputDot: "#5A8DEE", outputDot: "#5A8DEE", delay: 0.15 },
  { label: "RSI Filter",  lane: "Filter",    laneColor: "#E6C84D", chipClass: "bg-yellow-100 text-yellow-800",    params: "threshold=40",   inputDot: "#5A8DEE", outputDot: "#E6C84D", delay: 0.40 },
  { label: "Long Entry",  lane: "Alpha",     laneColor: "#D4A574", chipClass: "bg-amber-100 text-amber-800",      params: undefined,        inputDot: "#E6C84D", outputDot: "#D4A574", delay: 0.65 },
];

function BuilderCanvasVisual() {
  return (
    <div
      className="relative h-52 rounded-2xl border border-border overflow-hidden"
      style={{ background: "#FAFAFA" }}
    >
      {/* ReactFlow dot-grid background */}
      <div
        className="absolute inset-0 opacity-40"
        style={{
          backgroundImage: "radial-gradient(circle, #C8C8C8 1px, transparent 1px)",
          backgroundSize: "20px 20px",
        }}
      />
      {/* Top bar mimicking builder top bar */}
      <div className="absolute top-0 left-0 right-0 h-8 bg-surface border-b border-border flex items-center px-3 gap-3 z-10">
        <span className="text-[10px] font-mono text-muted">EMA Cross Strategy</span>
        <span className="ml-auto text-[10px] px-2 py-0.5 rounded bg-money text-white font-medium">▶ Run</span>
      </div>

      {/* Animated edges — drawn between node centres */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none" style={{ zIndex: 1 }}>
        <AnimatedEdge x1={34} y1={62} x2={44} y2={62} delay={0.55} />
        <AnimatedEdge x1={67} y1={62} x2={77} y2={62} delay={0.80} />
      </svg>

      {/* Nodes */}
      <div className="absolute inset-0 flex items-center justify-around px-4 pt-8" style={{ zIndex: 2 }}>
        {CANVAS_NODES.map((n) => (
          <MockNode key={n.label} {...n} />
        ))}
      </div>
    </div>
  );
}

// ── Step 02: Metrics Panel ────────────────────────────────────────────────────

interface MetricCardProps {
  label: string;
  value: string;
  tone?: "sage" | "terra" | "ink";
  delay: number;
}

function MetricCard({ label, value, tone = "ink", delay }: MetricCardProps) {
  const valueClass =
    tone === "sage"  ? "text-sage"  :
    tone === "terra" ? "text-terra" :
    "text-ink";
  return (
    <motion.div
      className="rounded-xl bg-surface2 border border-border p-3"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
    >
      <div className="text-[10px] uppercase tracking-widest text-muted">{label}</div>
      <div className={`text-[20px] font-semibold mt-0.5 num ${valueClass}`}>{value}</div>
    </motion.div>
  );
}

function MetricsPanelVisual() {
  const wr     = useCountUp(54, 1400);
  const trades = useCountUp(127, 1600);
  const evInt  = useCountUp(21, 1300);  // displayed as evInt/10
  const dd     = useCountUp(84, 1500);  // displayed as dd/10

  return (
    <div className="h-52 bg-surface rounded-2xl border border-border shadow-soft overflow-hidden flex flex-col justify-between p-4">
      {/* Header bar */}
      <motion.div
        className="text-[11px] text-muted font-mono mb-2"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2 }}
      >
        2,847 bars · pip = 0.0001 · {trades} setups detected
      </motion.div>

      {/* Progress bar */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-[10px] text-muted shrink-0">Running</span>
        <div className="flex-1 h-1 rounded-full bg-surface2 overflow-hidden">
          <motion.div
            className="h-full rounded-full bg-sage"
            initial={{ width: "0%" }}
            animate={{ width: "100%" }}
            transition={{ duration: 0.9, ease: "easeOut" }}
          />
        </div>
        <span className="text-[10px] font-mono text-sage shrink-0">2.1s</span>
      </div>

      {/* 4 metric cards */}
      <div className="grid grid-cols-4 gap-2 flex-1">
        <MetricCard label="Trades"    value={`${trades}`}             tone="ink"   delay={0.75} />
        <MetricCard label="Win rate"  value={`${wr}%`}                tone="sage"  delay={0.88} />
        <MetricCard label="EV/trade"  value={`${(evInt/10).toFixed(1)}R`} tone="sage"  delay={1.01} />
        <MetricCard label="Max DD"    value={`-${(dd/10).toFixed(1)}%`}   tone="terra" delay={1.14} />
      </div>
    </div>
  );
}

// ── Step 03: Equity Chart ─────────────────────────────────────────────────────

const EQ_PATH = "M 8 105 C 32 98, 50 88, 70 76 C 84 68, 89 80, 108 68 C 126 57, 140 44, 159 36 C 176 28, 180 42, 199 32 C 218 22, 238 13, 262 9";
const EQ_FILL = `${EQ_PATH} L 262 112 L 8 112 Z`;

const ITER_RUNS = [
  { n: "Run #1",  wr: "41%", clr: "text-terra" },
  { n: "Run #8",  wr: "49%", clr: "text-muted" },
  { n: "Run #14", wr: "54%", clr: "text-sage"  },
];

function EquityChartVisual() {
  return (
    <div className="h-52 bg-surface rounded-2xl border border-border shadow-soft overflow-hidden flex">
      {/* Chart area — matches EquityChart component */}
      <div className="flex-1 p-4 flex flex-col min-w-0">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[13px] font-medium text-ink">Equity curve</span>
          <span className="text-[10px] text-muted">log scale · $100 start · 1% risk</span>
        </div>
        <svg viewBox="0 0 272 116" className="flex-1 w-full" preserveAspectRatio="none">
          <defs>
            <linearGradient id="eqFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#6B9B7A" stopOpacity="0.28" />
              <stop offset="100%" stopColor="#6B9B7A" stopOpacity="0"    />
            </linearGradient>
          </defs>
          {/* Grid — matches recharts CartesianGrid */}
          {[30, 58, 86].map((y) => (
            <line key={y} x1="0" y1={y} x2="272" y2={y} stroke="#E0D9C7" strokeWidth="1" strokeDasharray="3 3" />
          ))}
          {/* Fill */}
          <motion.path d={EQ_FILL} fill="url(#eqFill)"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            transition={{ delay: 0.5, duration: 0.9 }} />
          {/* Line — stroke matches EquityChart: #6B9B7A */}
          <motion.path d={EQ_PATH} fill="none"
            stroke="#6B9B7A" strokeWidth="2.2" strokeLinecap="round"
            initial={{ pathLength: 0 }} animate={{ pathLength: 1 }}
            transition={{ duration: 1.8, ease: "easeOut" }} />
        </svg>
      </div>
      {/* Iteration log */}
      <div className="w-28 shrink-0 border-l border-border flex flex-col justify-center gap-4 px-4">
        <div className="text-[9px] text-muted uppercase tracking-widest font-mono">Iterations</div>
        {ITER_RUNS.map((r, i) => (
          <motion.div key={r.n}
            initial={{ opacity: 0, x: 8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.25 + i * 0.3 }}>
            <div className="text-[10px] text-muted">{r.n}</div>
            <div className={`text-[15px] font-bold num ${r.clr}`}>{r.wr}</div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

// ── Step 04: Forward Test ─────────────────────────────────────────────────────

const FWD_CHECKS = [
  { label: "Out-of-sample return", value: "+18.4%", delay: 0.20 },
  { label: "Max drawdown",         value: "-6.2%",  delay: 0.55 },
  { label: "Months profitable",    value: "3 / 4",  delay: 0.90 },
];

function ForwardTestVisual() {
  return (
    <div className="h-52 bg-surface rounded-2xl border border-border shadow-soft overflow-hidden p-5 flex flex-col justify-center gap-4">
      {/* header mimics MetricsPanel sub-section */}
      <motion.div
        className="text-[10px] uppercase tracking-widest text-muted font-mono"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.1 }}>
        Paper · out-of-sample · 480 bars
      </motion.div>

      {FWD_CHECKS.map(({ label, value, delay }) => (
        <motion.div key={label}
          className="flex items-center gap-3"
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay }}>
          <motion.div
            className="w-5 h-5 rounded-full flex items-center justify-center shrink-0"
            style={{ background: "rgba(107,155,122,0.15)", border: "1.5px solid #6B9B7A" }}
            initial={{ scale: 0, rotate: -90 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ delay: delay + 0.08, type: "spring", stiffness: 400, damping: 20 }}>
            <span style={{ color: "#6B9B7A", fontSize: 10, fontWeight: 700, lineHeight: 1 }}>✓</span>
          </motion.div>
          <span className="text-[13px] text-muted flex-1">{label}</span>
          <span className="text-[16px] font-semibold num text-sage">{value}</span>
        </motion.div>
      ))}

      <motion.div
        className="self-start inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-[12px] font-semibold"
        style={{ background: "rgba(11,110,79,0.08)", border: "1px solid rgba(11,110,79,0.25)", color: "#0B6E4F" }}
        initial={{ opacity: 0, y: 6, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ delay: 1.4 }}>
        <span className="w-1.5 h-1.5 rounded-full bg-money animate-pulse" />
        Ready to fund
      </motion.div>
    </div>
  );
}

// ── Journey config ────────────────────────────────────────────────────────────

interface StepConfig {
  n: string;
  title: string;
  body: string;
  Visual: () => React.JSX.Element;
}

const JOURNEY: StepConfig[] = [
  {
    n: "01",
    title: "Define your rules",
    body: "Drag nodes onto the canvas — entry signal, filter, stop loss, take profit. Make every rule explicit. If you can't wire it, it's not a rule.",
    Visual: BuilderCanvasVisual,
  },
  {
    n: "02",
    title: "Backtest on real data",
    body: "Hit Run. Years of forex data processed in under 2 seconds. Real fills. No lookahead. The truth about your strategy — not what you hoped.",
    Visual: MetricsPanelVisual,
  },
  {
    n: "03",
    title: "Iterate until it holds up",
    body: "Tune one parameter, re-run, watch the equity curve react. Repeat until you have positive expectancy and drawdown you can actually stomach.",
    Visual: EquityChartVisual,
  },
  {
    n: "04",
    title: "Forward test before you fund",
    body: "Run on unseen bars in paper mode. Confirm it holds up outside the data you optimised on. Only then put money behind it.",
    Visual: ForwardTestVisual,
  },
];

const STEP_MS = 4500;

// ── Main component ────────────────────────────────────────────────────────────

export function JourneyAnimation() {
  const [step, setStep] = useState(0);
  const [tick, setTick] = useState(0);

  function goTo(i: number) {
    setStep(i);
    setTick((t) => t + 1);
  }

  useEffect(() => {
    const id = setTimeout(() => {
      setStep((s) => (s + 1) % JOURNEY.length);
      setTick((t) => t + 1);
    }, STEP_MS);
    return () => clearTimeout(id);
  }, [tick]);

  const Visual = JOURNEY[step].Visual;

  return (
    <div className="w-full max-w-3xl mx-auto">
      {/* Step tabs */}
      <div className="grid grid-cols-4 gap-1.5 mb-5">
        {JOURNEY.map((s, i) => (
          <button
            key={s.n}
            onClick={() => goTo(i)}
            className={[
              "text-left px-3 py-2.5 rounded-xl border transition-all text-[11.5px] font-medium",
              i === step
                ? "bg-money/8 border-money/30 text-money"
                : i < step
                ? "bg-surface border-border text-muted"
                : "bg-surface2 border-transparent text-muted/60",
            ].join(" ")}
          >
            <div className="font-mono text-[10px] mb-0.5 opacity-70">{s.n}</div>
            <div className="leading-tight hidden sm:block">{s.title}</div>
          </button>
        ))}
      </div>

      {/* Progress bar */}
      <div className="h-0.5 rounded-full bg-border mb-5 overflow-hidden">
        <motion.div
          key={tick}
          className="h-full rounded-full bg-money"
          initial={{ width: "0%" }}
          animate={{ width: "100%" }}
          transition={{ duration: STEP_MS / 1000, ease: "linear" }}
        />
      </div>

      {/* Visual */}
      <AnimatePresence mode="wait">
        <motion.div
          key={`v-${tick}`}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.25 }}
        >
          <Visual />
        </motion.div>
      </AnimatePresence>

      {/* Text */}
      <AnimatePresence mode="wait">
        <motion.div
          key={`t-${tick}`}
          className="mt-5"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <h3 className="font-semibold text-[17px] text-ink mb-1">{JOURNEY[step].title}</h3>
          <p className="text-[13.5px] text-muted leading-relaxed">{JOURNEY[step].body}</p>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
