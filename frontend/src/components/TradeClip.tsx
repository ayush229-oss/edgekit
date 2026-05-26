"use client";

/**
 * Animated mini candlestick chart that re-plays a single trade.
 * Candles reveal one at a time, exit marker flashes, then loop.
 */
import { useEffect, useRef, useState } from "react";

type Bar = { i: number; o: number; h: number; l: number; c: number; t: string };
type TP  = { price: number; qty: number };

export type TradeClipData = {
  direction: "Bull" | "Bear";
  result:    "Win" | "Loss" | string;
  exit_type: string;
  pnl_r:     number;
  entry:     number;
  sl:        number;
  tps:       TP[];
  fill_idx:  number;
  exit_idx:  number;
  bars:      Bar[];
};

const W = 220;
const H = 120;
const PAD_TOP = 8;
const PAD_BOT = 10;
const PAD_X   = 4;

export function TradeClip({ data, label }: { data: TradeClipData; label: "Winner" | "Loser" }) {
  const [step, setStep] = useState(0);          // how many candles revealed
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const isWin   = data.result === "Win";
  const accent  = isWin ? "#6B9B7A" : "#C97B63";
  const bgGlow  = isWin ? "rgba(107,155,122,0.08)" : "rgba(201,123,99,0.08)";

  // Animate: reveal one bar every 140ms; pause 1.2s at end; loop.
  useEffect(() => {
    const total = data.bars.length;
    setStep(1);
    const tick = () => {
      setStep((s) => {
        if (s >= total) { return 0; }   // reset for loop
        return s + 1;
      });
    };
    intervalRef.current = setInterval(tick, 160);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [data]);

  // Y-scale from full bar range + key levels
  const allPrices = [
    ...data.bars.flatMap((b) => [b.h, b.l]),
    data.entry, data.sl,
    ...data.tps.map((t) => t.price),
  ];
  const pMin = Math.min(...allPrices);
  const pMax = Math.max(...allPrices);
  const pRange = (pMax - pMin) || 1;
  const yOf = (p: number) =>
    PAD_TOP + (1 - (p - pMin) / pRange) * (H - PAD_TOP - PAD_BOT);

  const barW = (W - PAD_X * 2) / data.bars.length;
  const xOf  = (i: number) => PAD_X + i * barW + barW / 2;

  const visible    = data.bars.slice(0, step);
  const exitReached = step > (data.exit_idx - data.bars[0].i);

  return (
    <div className="relative rounded-md overflow-hidden border border-border"
         style={{ background: bgGlow }}>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="block">
        {/* Entry line (always shown after fill candle revealed) */}
        {step > (data.fill_idx - data.bars[0].i) && (
          <>
            <line
              x1={PAD_X} x2={W - PAD_X}
              y1={yOf(data.entry)} y2={yOf(data.entry)}
              stroke="#2C3E36" strokeWidth={0.6} strokeDasharray="2 2"
            />
            <line
              x1={PAD_X} x2={W - PAD_X}
              y1={yOf(data.sl)} y2={yOf(data.sl)}
              stroke="#C97B63" strokeWidth={0.6} strokeDasharray="3 2"
            />
            {data.tps.map((tp, i) => (
              <line key={i}
                x1={PAD_X} x2={W - PAD_X}
                y1={yOf(tp.price)} y2={yOf(tp.price)}
                stroke="#6B9B7A" strokeWidth={0.5} strokeDasharray="2 3"
                opacity={0.6 + i * 0.13}
              />
            ))}
          </>
        )}

        {/* Candles */}
        {visible.map((b, idx) => {
          const up   = b.c >= b.o;
          const x    = xOf(idx);
          const top  = yOf(Math.max(b.o, b.c));
          const bot  = yOf(Math.min(b.o, b.c));
          const wickT = yOf(b.h);
          const wickB = yOf(b.l);
          const fill  = up ? "#6B9B7A" : "#C97B63";
          const bodyH = Math.max(0.6, bot - top);
          const bodyW = Math.max(1.0, barW * 0.65);
          return (
            <g key={b.i}>
              <line x1={x} x2={x} y1={wickT} y2={wickB}
                    stroke={fill} strokeWidth={0.7} />
              <rect x={x - bodyW / 2} y={top}
                    width={bodyW} height={bodyH}
                    fill={fill} />
            </g>
          );
        })}

        {/* Exit marker — pulses on the bar where exit happened */}
        {exitReached && (
          <circle
            cx={xOf(data.exit_idx - data.bars[0].i)}
            cy={yOf(isWin ? data.tps[data.tps.length - 1]?.price ?? data.entry : data.sl)}
            r={3.5}
            fill={accent}
            opacity={0.85}
          >
            <animate attributeName="r" values="3.5;5.5;3.5" dur="1s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.85;0.4;0.85" dur="1s" repeatCount="indefinite" />
          </circle>
        )}
      </svg>

      {/* Caption strip */}
      <div className="absolute top-1 left-1.5 flex items-center gap-1 text-[9px] font-medium uppercase tracking-wider"
           style={{ color: accent }}>
        <span>{label}</span>
        <span className="opacity-70 font-mono normal-case tracking-normal">
          {data.exit_type} · {data.pnl_r >= 0 ? "+" : ""}{data.pnl_r.toFixed(1)}R
        </span>
      </div>
      <div className="absolute bottom-0.5 right-1.5 text-[9px] font-mono"
           style={{ color: accent, opacity: 0.7 }}>
        {data.direction.toLowerCase()}
      </div>
    </div>
  );
}

export function TradeClipPair({ strategyId, initialData }: {
  strategyId: string;
  initialData?: any;
}) {
  const [data, setData] = useState<any | null>(initialData ?? null);
  const [err,  setErr]  = useState<string | null>(null);

  useEffect(() => {
    // Server already provided data — no client fetch needed.
    if (initialData) return;

    const controller = new AbortController();
    fetch(`/api/strategies/${strategyId}/preview-trades`, { signal: controller.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return r.json();
      })
      .then(setData)
      .catch((e) => { if (e.name !== "AbortError") setErr(String(e)); });
    return () => controller.abort();
  }, [strategyId, initialData]);

  if (err) {
    return (
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-md border border-border bg-cream h-[120px] flex items-center justify-center text-[10px] text-muted">
          preview unavailable
        </div>
        <div className="rounded-md border border-border bg-cream h-[120px] flex items-center justify-center text-[10px] text-muted">
          preview unavailable
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-md border border-border bg-cream h-[120px] animate-pulse" />
        <div className="rounded-md border border-border bg-cream h-[120px] animate-pulse" />
      </div>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-2">
      {data.winner ? <TradeClip data={data.winner} label="Winner" /> :
        <div className="rounded-md border border-border bg-cream h-[120px] flex items-center justify-center text-[10px] text-muted">no recent winner</div>}
      {data.loser  ? <TradeClip data={data.loser}  label="Loser"  /> :
        <div className="rounded-md border border-border bg-cream h-[120px] flex items-center justify-center text-[10px] text-muted">no recent loser</div>}
    </div>
  );
}
