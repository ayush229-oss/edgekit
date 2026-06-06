"use client";
import React from "react";

/**
 * User Settings — persisted to localStorage (browser-local).
 * Covers: default risk %, preferred instruments, execution cost defaults,
 * default timeframe, and theme preference.
 *
 * These values are read by the builder to pre-fill backtest parameters.
 */
import { useState, useEffect } from "react";

const SETTINGS_KEY = "edgekit.settings.v1";

export type UserSettings = {
  risk_pct:         number;   // 0.01 = 1%
  max_risk_usd:     number;
  default_symbol:   string;
  default_tf:       string;
  spread_pips:      number;
  commission:       number;   // USD round-trip
  slippage_pips:    number;
  swap_long_pips:   number;
  swap_short_pips:  number;
  default_bars:     number;
  max_concurrent:   number;
};

const DEFAULTS: UserSettings = {
  risk_pct:        0.01,
  max_risk_usd:    600,
  default_symbol:  "XAUUSD",
  default_tf:      "M15",
  spread_pips:     0,
  commission:      0,
  slippage_pips:   0,
  swap_long_pips:  0,
  swap_short_pips: 0,
  default_bars:    5000,
  max_concurrent:  1,
};

export function loadSettings(): UserSettings {
  if (typeof window === "undefined") return DEFAULTS;
  try {
    const raw = window.localStorage.getItem(SETTINGS_KEY);
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS;
  } catch { return DEFAULTS; }
}

function saveSettings(s: UserSettings) {
  window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
}

const TIMEFRAMES = ["M1","M5","M15","M30","H1","H4","D1"];
const SYMBOLS    = ["XAUUSD","EURUSD","GBPUSD","USDJPY","GBPJPY","BTCUSD","US500","NAS100","USOIL"];

export default function SettingsPage() {
  const [s, setS]     = useState<UserSettings>(DEFAULTS);
  const [saved, setSaved] = useState(false);

  useEffect(() => { setS(loadSettings()); }, []);

  function upd(patch: Partial<UserSettings>) {
    setS((prev) => ({ ...prev, ...patch }));
    setSaved(false);
  }

  function save() {
    saveSettings(s);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  const Row = ({ label, sub, children }: { label: string; sub?: string; children: React.ReactNode }) => (
    <div className="flex items-start justify-between gap-4 py-4 border-b border-border last:border-0">
      <div>
        <div className="text-[13.5px] font-medium text-ink">{label}</div>
        {sub && <div className="text-[11.5px] text-muted mt-0.5">{sub}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );

  const Num = ({ field, min, max, step = 0.1 }: { field: keyof UserSettings; min: number; max: number; step?: number }) => (
    <input
      type="number" min={min} max={max} step={step}
      value={s[field] as number}
      onChange={(e) => upd({ [field]: parseFloat(e.target.value) || 0 } as any)}
      className="w-24 rounded-lg bg-paper border border-border px-2 py-1.5 text-[13px] text-right
                 focus:outline-none focus:ring-1 focus:ring-money"
    />
  );

  return (
    <div className="max-w-2xl mx-auto px-4 py-10 space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-ink">Settings</h1>
        <p className="text-muted text-sm mt-1">Default values used across the strategy builder. Saved locally in your browser.</p>
      </div>

      {/* Sizing */}
      <section className="rounded-2xl border border-border bg-surface p-6">
        <h2 className="text-[13px] uppercase tracking-widest text-muted font-semibold mb-2">Position Sizing</h2>
        <Row label="Risk per trade" sub="Fraction of equity risked on each trade">
          <div className="flex items-center gap-2">
            <Num field="risk_pct" min={0.001} max={0.1} step={0.001} />
            <span className="text-[12px] text-muted">{(s.risk_pct * 100).toFixed(1)}%</span>
          </div>
        </Row>
        <Row label="Max risk USD" sub="Hard cap regardless of equity (e.g. $600)">
          <Num field="max_risk_usd" min={10} max={100000} step={10} />
        </Row>
        <Row label="Max concurrent trades" sub="How many positions can be open at once">
          <input
            type="number" min={1} max={10}
            value={s.max_concurrent}
            onChange={(e) => upd({ max_concurrent: parseInt(e.target.value) || 1 })}
            className="w-20 rounded-lg bg-paper border border-border px-2 py-1.5 text-[13px] text-right
                       focus:outline-none focus:ring-1 focus:ring-money"
          />
        </Row>
      </section>

      {/* Defaults */}
      <section className="rounded-2xl border border-border bg-surface p-6">
        <h2 className="text-[13px] uppercase tracking-widest text-muted font-semibold mb-2">Data Defaults</h2>
        <Row label="Default symbol">
          <select value={s.default_symbol} onChange={(e) => upd({ default_symbol: e.target.value })}
            className="rounded-lg bg-paper border border-border px-2 py-1.5 text-[13px] focus:outline-none focus:ring-1 focus:ring-money">
            {SYMBOLS.map((sym) => <option key={sym} value={sym}>{sym}</option>)}
          </select>
        </Row>
        <Row label="Default timeframe">
          <select value={s.default_tf} onChange={(e) => upd({ default_tf: e.target.value })}
            className="rounded-lg bg-paper border border-border px-2 py-1.5 text-[13px] focus:outline-none focus:ring-1 focus:ring-money">
            {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
          </select>
        </Row>
        <Row label="Default bars" sub="Number of bars to load per backtest">
          <input type="number" min={500} max={50000} step={500}
            value={s.default_bars}
            onChange={(e) => upd({ default_bars: parseInt(e.target.value) || 5000 })}
            className="w-24 rounded-lg bg-paper border border-border px-2 py-1.5 text-[13px] text-right
                       focus:outline-none focus:ring-1 focus:ring-money" />
        </Row>
      </section>

      {/* Execution costs */}
      <section className="rounded-2xl border border-border bg-surface p-6">
        <h2 className="text-[13px] uppercase tracking-widest text-muted font-semibold mb-2">Execution Costs</h2>
        <p className="text-[11.5px] text-muted mb-4">Applied to every backtest. Set realistic values for your broker to get accurate results.</p>
        <Row label="Spread (pips)" sub="Half applied to each side of entry">
          <Num field="spread_pips" min={0} max={50} step={0.1} />
        </Row>
        <Row label="Commission (USD)" sub="Round-trip commission per trade">
          <Num field="commission" min={0} max={100} step={0.5} />
        </Row>
        <Row label="Slippage (pips)" sub="Worst-case market-exit slippage">
          <Num field="slippage_pips" min={0} max={20} step={0.1} />
        </Row>
        <Row label="Swap long (pips/day)" sub="Overnight carry cost for long positions">
          <Num field="swap_long_pips" min={-20} max={20} step={0.01} />
        </Row>
        <Row label="Swap short (pips/day)" sub="Overnight carry cost for short positions">
          <Num field="swap_short_pips" min={-20} max={20} step={0.01} />
        </Row>
      </section>

      <div className="flex items-center gap-3">
        <button
          onClick={save}
          className="px-5 py-2 rounded-lg bg-money text-white text-[13.5px] font-medium hover:bg-moneyDark transition-colors"
        >
          Save settings
        </button>
        {saved && <span className="text-[12.5px] text-sage">✓ Saved</span>}
        <button
          onClick={() => { setS(DEFAULTS); setSaved(false); }}
          className="text-[12.5px] text-muted hover:text-ink ml-auto"
        >
          Reset to defaults
        </button>
      </div>
    </div>
  );
}
