"use client";

/**
 * Forward (paper) testing dashboard.
 *
 * Each card compares the ORIGINAL backtest (baseline) against live forward
 * results that accumulate on bars the strategy never saw — the trust check.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  forwardList, forwardRefresh, forwardStop,
  type ForwardTest, type ForwardMetrics,
} from "@/lib/api";

function fmtPct(v?: number) { return v == null ? "—" : `${v.toFixed(1)}%`; }
function fmtR(v?: number)   { return v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}R`; }
function fmtPF(v?: number)  { return v == null ? "—" : (v === 99 ? "∞" : v.toFixed(2)); }
function when(iso?: string) {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  return d.toLocaleString();
}

function Row({ label, base, fwd, kind }: {
  label: string; base?: number; fwd?: number;
  kind: "pct" | "r" | "pf" | "num";
}) {
  const f = kind === "pct" ? fmtPct : kind === "r" ? fmtR : kind === "pf" ? fmtPF : (v?: number) => (v == null ? "—" : String(v));
  const good = (fwd ?? 0) >= 0;
  const fwdColor = kind === "r" || kind === "pct" ? (good ? "text-emerald-600" : "text-rose-600") : "text-ink";
  return (
    <div className="grid grid-cols-3 gap-2 py-1 text-[13px] border-b border-border/50 last:border-0">
      <span className="text-muted">{label}</span>
      <span className="text-right font-mono text-ink/70">{f(base)}</span>
      <span className={`text-right font-mono font-semibold ${fwdColor}`}>{f(fwd)}</span>
    </div>
  );
}

export default function ForwardPage() {
  const [tests, setTests] = useState<ForwardTest[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    try { setTests(await forwardList()); }
    catch (e: any) { setErr(e?.message ?? String(e)); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);

  async function refresh(id: number) {
    setBusyId(id);
    try {
      const updated = await forwardRefresh(id);
      setTests((ts) => ts.map((t) => (t.id === id ? updated : t)));
    } catch (e: any) { setErr(e?.message ?? String(e)); }
    finally { setBusyId(null); }
  }
  async function stop(id: number) {
    setBusyId(id);
    try {
      const updated = await forwardStop(id);
      setTests((ts) => ts.map((t) => (t.id === id ? updated : t)));
    } catch (e: any) { setErr(e?.message ?? String(e)); }
    finally { setBusyId(null); }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-ink">Forward tests</h1>
        <p className="text-sm text-muted mt-1 max-w-2xl">
          A backtest can be overfit. A <strong>forward test</strong> runs your strategy on
          bars it never saw, accumulating in real time — the honest proof it actually works.
          Start one from any strategy's <Link href="/builder" className="text-money underline">backtest results</Link>.
        </p>
      </div>

      {err && <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{err}</div>}

      {loading ? (
        <div className="text-sm text-muted">Loading…</div>
      ) : tests.length === 0 ? (
        <div className="rounded-xl border border-border bg-surface p-8 text-center">
          <div className="text-3xl mb-2">🧪</div>
          <div className="text-ink font-medium">No forward tests yet</div>
          <div className="text-sm text-muted mt-1">
            Build a strategy, run a backtest, then click <strong>“Forward test”</strong> to start tracking it live.
          </div>
          <Link href="/builder" className="inline-block mt-4 text-sm px-4 py-2 rounded-lg bg-money text-white font-medium">
            Go to the builder →
          </Link>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {tests.map((t) => {
            const base = (t.baseline ?? {}) as Partial<ForwardMetrics>;
            const fwd  = t.latest?.metrics;
            const seen = t.latest?.bars_seen ?? 0;
            const noTrades = (fwd?.trades ?? 0) === 0;
            const ds = t.latest?.data_source?.label;
            const isLive = t.mode === "live_demo";
            const costs = t.latest?.costs;
            return (
              <div key={t.id} className="rounded-xl border border-border bg-surface p-4">
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div>
                    <div className="font-semibold text-ink">{t.name}</div>
                    <div className="text-[11px] text-muted">
                      {t.symbol} · {t.timeframe}
                      {ds ? <> · <span className={t.latest?.data_source?.provider === "mt5" ? "text-emerald-600" : "text-amber-600"}>{ds}</span></> : null}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                      isLive ? "bg-emerald-100 text-emerald-700" : "bg-sky-100 text-sky-700"}`}>
                      {isLive ? "🔴 live demo" : "🧪 paper"}
                    </span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                      t.status === "active" ? "bg-emerald-100 text-emerald-700" : "bg-surface2 text-muted"}`}>
                      {t.status}
                    </span>
                  </div>
                </div>

                <div className="text-[11px] text-muted mb-2">
                  Tracking since {when(t.started_at)} · {seen} bars seen · updated {when(t.latest?.last_run)}
                </div>

                {t.latest?.error ? (
                  <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-800 mb-2">
                    Last run had an issue: {t.latest.error}
                  </div>
                ) : null}

                <div className="rounded-lg border border-border bg-paper px-3 py-2">
                  <div className="grid grid-cols-3 gap-2 text-[10px] uppercase tracking-wide text-muted pb-1 border-b border-border">
                    <span>Metric</span><span className="text-right">Backtest</span><span className="text-right">Forward</span>
                  </div>
                  <Row label="Trades"   base={base.trades} fwd={fwd?.trades} kind="num" />
                  <Row label="Win rate" base={base.wr}     fwd={fwd?.wr}     kind="pct" />
                  {isLive ? (
                    <Row label="Net profit ($)" base={undefined} fwd={fwd?.total_profit} kind="r" />
                  ) : (
                    <>
                      <Row label="Total R"       base={base.total_r}       fwd={fwd?.total_r}       kind="r" />
                      <Row label="Profit factor" base={base.profit_factor} fwd={fwd?.profit_factor} kind="pf" />
                      <Row label="Max drawdown"  base={base.max_dd}        fwd={fwd?.max_dd}        kind="r" />
                    </>
                  )}
                </div>

                {isLive && costs && (
                  <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
                    <span className="font-medium">Real costs paid</span> — the part backtests ignore:
                    spread <span className="font-mono">${(costs.total_spread ?? 0).toFixed(2)}</span>,
                    slippage <span className="font-mono">${(costs.total_slippage ?? 0).toFixed(2)}</span>
                    {(fwd?.open_positions ?? 0) > 0 ? <> · <span className="font-mono">{fwd?.open_positions} open</span></> : null}
                  </div>
                )}

                {noTrades && (
                  <div className="text-[12px] text-muted italic mt-2">
                    {isLive
                      ? "No live trades yet — the executor opens a demo order when your strategy next signals (MT5 host must be running)."
                      : "No forward trades yet — results appear as new bars form and the strategy triggers."}
                  </div>
                )}

                <div className="flex items-center gap-2 mt-3">
                  <button onClick={() => refresh(t.id)} disabled={busyId === t.id}
                    className="text-xs px-3 py-1.5 rounded border border-border hover:bg-surface2 disabled:opacity-50">
                    {busyId === t.id ? "Refreshing…" : "↻ Refresh now"}
                  </button>
                  {t.status === "active" && (
                    <button onClick={() => stop(t.id)} disabled={busyId === t.id}
                      className="text-xs px-3 py-1.5 rounded border border-border text-muted hover:text-ink hover:bg-surface2 disabled:opacity-50">
                      Stop
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
