"use client";

/**
 * Trade Management — matches the user mental model:
 *  1. Set target R:R (single number, your TP if not trailing)
 *  2. Decide: trail or not
 *  3. If trail — pick HOW
 */

export type TrailMode  = "none" | "candle" | "atr" | "pips" | "swing";
export type TrailStart = "immediate" | "after_target";

export type TradeMgmt = {
  target_r:         number;
  target_close_pct: number;        // 0..1 — fraction of position to close at target_r
  trail_mode:       TrailMode;
  trail_start:      TrailStart;
  trail_params:     Record<string, any>;
};

const TRAIL_MODE_LABELS: Record<TrailMode, string> = {
  none:    "No trail — exit fully at target R",
  candle:  "Trail behind each candle's wick",
  atr:     "Trail by ATR (volatility-adjusted)",
  pips:    "Trail by a fixed pip distance",
  swing:   "Trail behind the last swing low / high",
};

const TRAIL_DESCRIPTIONS: Record<TrailMode, string> = {
  none:    "Closes the full position when price reaches your target R.",
  candle:  "After trailing kicks in, SL moves to each new candle's low (bull) / high (bear) plus a buffer.",
  atr:     "SL trails behind the current close by ATR × multiplier. Adapts to volatility — wider stops in chop, tighter in calm.",
  pips:    "SL trails behind the current close by a fixed pip distance. Predictable and simple.",
  swing:   "SL jumps to the most recent swing low (bull) or swing high (bear). SMC-style structural trailing.",
};

export function TradeManagement({
  mgmt, onChange,
}: {
  mgmt: TradeMgmt;
  onChange: (next: TradeMgmt) => void;
}) {
  const set  = <K extends keyof TradeMgmt>(k: K, v: TradeMgmt[K]) => onChange({ ...mgmt, [k]: v });
  const setP = (k: string, v: any) =>
    onChange({ ...mgmt, trail_params: { ...mgmt.trail_params, [k]: v } });

  return (
    <div className="rounded-xl bg-cream2 border border-border p-4 space-y-5">
      <h3 className="text-xs uppercase tracking-widest text-muted">Trade Management</h3>

      {/* ── Step 1: target R ──────────────────────────────────────────── */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-sm">
          <label className="font-medium">1. Target R:R</label>
          <span className="font-mono text-sage">{mgmt.target_r.toFixed(1)}R</span>
        </div>
        <input
          type="range" min={1} max={10} step={0.5}
          value={mgmt.target_r}
          onChange={(e) => set("target_r", parseFloat(e.target.value))}
          className="w-full accent-sage"
        />
        <p className="text-[11px] italic text-muted">
          Your take-profit. {mgmt.trail_mode === "none"
            ? "Trade closes here."
            : (mgmt.trail_start === "after_target"
              ? "Trailing kicks in after price reaches this level."
              : "Trailing starts immediately — this target becomes informational.")}
        </p>
      </div>

      {/* ── Step 1b: partial close at target (only when trailing after target) ── */}
      {mgmt.trail_mode !== "none" && mgmt.trail_start === "after_target" && (
        <div className="space-y-1.5 pl-3 border-l-2 border-sage/30">
          <div className="flex items-center justify-between text-sm">
            <label className="font-medium">Close at target</label>
            <span className="font-mono text-sage text-xs">
              {Math.round(mgmt.target_close_pct * 100)}%
            </span>
          </div>
          <input
            type="range" min={0} max={1} step={0.05}
            value={mgmt.target_close_pct}
            onChange={(e) => set("target_close_pct", parseFloat(e.target.value))}
            className="w-full accent-sage"
          />
          <p className="text-[11px] italic text-muted leading-snug">
            {mgmt.target_close_pct >= 0.999
              ? "Full exit at target. Trail never activates (effectively the same as 'No trail')."
              : mgmt.target_close_pct <= 0.001
                ? "Ride the full position via trail — target is just the trigger."
                : `Take ${Math.round(mgmt.target_close_pct * 100)}% off at target, trail the remaining ${Math.round((1 - mgmt.target_close_pct) * 100)}%.`}
          </p>
        </div>
      )}

      {/* ── Step 2: trail or not ─────────────────────────────────────── */}
      <div className="space-y-1.5">
        <label className="text-sm font-medium block">2. Trail mode</label>
        <select
          value={mgmt.trail_mode}
          onChange={(e) => set("trail_mode", e.target.value as TrailMode)}
          className="w-full rounded-md bg-cream border border-border px-2 py-2 text-sm"
        >
          {(Object.keys(TRAIL_MODE_LABELS) as TrailMode[]).map((m) => (
            <option key={m} value={m}>{TRAIL_MODE_LABELS[m]}</option>
          ))}
        </select>
        <p className="text-[11px] italic text-muted">{TRAIL_DESCRIPTIONS[mgmt.trail_mode]}</p>
      </div>

      {/* ── Step 3: when does trail start (only if trailing) ─────────── */}
      {mgmt.trail_mode !== "none" && (
        <div className="space-y-1.5">
          <label className="text-sm font-medium block">3. Start trailing</label>
          <div className="grid grid-cols-2 gap-2">
            <label className={`rounded-md border px-3 py-2 cursor-pointer text-sm text-center
                ${mgmt.trail_start === "immediate"
                  ? "border-sage bg-sage/10 text-sage"
                  : "border-border bg-cream"}`}>
              <input type="radio" name="trail_start" className="hidden"
                checked={mgmt.trail_start === "immediate"}
                onChange={() => set("trail_start", "immediate")} />
              Immediately from entry
            </label>
            <label className={`rounded-md border px-3 py-2 cursor-pointer text-sm text-center
                ${mgmt.trail_start === "after_target"
                  ? "border-sage bg-sage/10 text-sage"
                  : "border-border bg-cream"}`}>
              <input type="radio" name="trail_start" className="hidden"
                checked={mgmt.trail_start === "after_target"}
                onChange={() => set("trail_start", "after_target")} />
              After target R is hit
            </label>
          </div>
        </div>
      )}

      {/* ── Step 4: mode-specific params ──────────────────────────────── */}
      {mgmt.trail_mode === "candle" && (
        <NumberKnob label="Buffer pips behind wick" value={mgmt.trail_params.buf_pips ?? 1}
                    min={0} max={20} step={1} desc="How far behind each candle's wick the SL sits."
                    onChange={(v) => setP("buf_pips", v)} />
      )}
      {mgmt.trail_mode === "atr" && (
        <>
          <NumberKnob label="ATR multiplier" value={mgmt.trail_params.atr_mult ?? 1.5}
                      min={0.5} max={5} step={0.1}
                      desc="Higher = wider trailing distance. Adapts to volatility."
                      onChange={(v) => setP("atr_mult", v)} />
          <NumberKnob label="ATR period" value={mgmt.trail_params.atr_period ?? 14}
                      min={5} max={50} step={1}
                      desc="Lookback for ATR calculation."
                      onChange={(v) => setP("atr_period", v)} />
        </>
      )}
      {mgmt.trail_mode === "pips" && (
        <NumberKnob label="Trail distance (pips)" value={mgmt.trail_params.trail_pips ?? 20}
                    min={1} max={200} step={1}
                    desc="Fixed pip distance the SL trails behind price."
                    onChange={(v) => setP("trail_pips", v)} />
      )}
      {mgmt.trail_mode === "swing" && (
        <>
          <NumberKnob label="Swing length" value={mgmt.trail_params.swing_len ?? 3}
                      min={2} max={10} step={1}
                      desc="Bars on each side to qualify as a swing point. Lower = more reactive."
                      onChange={(v) => setP("swing_len", v)} />
          <NumberKnob label="Buffer pips" value={mgmt.trail_params.buf_pips ?? 1}
                      min={0} max={20} step={1}
                      desc="Distance behind the swing point."
                      onChange={(v) => setP("buf_pips", v)} />
        </>
      )}
    </div>
  );
}


function NumberKnob({
  label, value, min, max, step, desc, onChange,
}: {
  label: string; value: number; min: number; max: number; step: number;
  desc: string; onChange: (v: number) => void;
}) {
  return (
    <div className="space-y-1.5 pl-3 border-l-2 border-sage/30">
      <div className="flex items-center justify-between text-sm">
        <label className="font-medium">{label}</label>
        <span className="font-mono text-sage text-xs">{value}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full accent-sage"
      />
      <p className="text-[11px] italic text-muted leading-snug">{desc}</p>
    </div>
  );
}
