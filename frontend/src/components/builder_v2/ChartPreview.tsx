"use client";

/**
 * Chart preview — TradingView-style candlestick view of the strategy's
 * backtest, powered by `lightweight-charts` (TradingView's OSS lib).
 *
 * Visualization philosophy: clean by default, layered on demand.
 *   • Default: small entry/exit dots only — zero clutter, scales to 500+ trades.
 *   • Click any trade → reveals that trade's Entry / SL / TP price lines and
 *     zooms the chart to it.
 *   • [R/R zones] toggle → draws Entry / SL / TP segments for ALL trades
 *     (only while each trade is live, so segments don't run forever).
 *   • [Position ribbon] toggle → adds a histogram at the bottom showing
 *     when the strategy was long (sage), short (terra), or flat.
 *
 * Numbers match Edgekit's backtest exactly — same simulator, same bars.
 */
import { useEffect, useRef, useState } from "react";
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  createSeriesMarkers,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type IPriceLine,
  type UTCTimestamp,
  type Time,
  type SeriesMarkerShape,
  type SeriesMarkerBarPosition,
  type ISeriesMarkersPluginApi,
} from "lightweight-charts";
import { v2ChartPreview, type ChartPreview as CP, type ChartTrade } from "@/lib/api";
import type { V2Graph } from "@/lib/api";
import type { TradeMgmt } from "@/components/TradeManagement";


// ── Palette (matches the cream/sage/terra app theme) ──────────────────────
const C = {
  sage:   "#6B9B7A",
  sageF:  "#6B9B7A55",   // faded for ribbon
  terra:  "#C97B63",
  terraF: "#C97B6355",
  amber:  "#D4A574",
  muted:  "#8A8071",
  cream:  "#FAF7EE",
  border: "#D4CCB8",
  ink:    "#2C3E2D",
  grid:   "#EAE5D8",
};


// Compute target price from entry / sl / direction / target_r
function tpPrice(tr: ChartTrade, targetR: number) {
  const r1 = Math.abs(tr.entry - tr.sl);
  return tr.direction === "Bull" ? tr.entry + r1 * targetR : tr.entry - r1 * targetR;
}

function tradeColor(tr: ChartTrade) {
  if (tr.result === "Win")  return C.sage;
  if (tr.result === "Loss") return C.terra;
  return C.muted;
}

// True if bar `i` is inside trade `tr`'s live window
function activeAt(tr: ChartTrade, i: number) {
  const s = tr.fill_idx ?? tr.signal_idx;
  const e = tr.exit_idx ?? s + 200;
  return i >= s && i <= e;
}


export function ChartPreview({
  open, onClose, graph, mgmt, symbol, timeframe, defaultBars = 5000,
}: {
  open:        boolean;
  onClose:     () => void;
  graph:       V2Graph | null;
  mgmt:        TradeMgmt;
  symbol:      string;
  timeframe:   string;
  defaultBars?: number;     // inherits from the top-bar Bars input
}) {
  // ── Refs ──────────────────────────────────────────────────────────────
  const containerRef  = useRef<HTMLDivElement>(null);
  const chartRef      = useRef<IChartApi | null>(null);
  const candlesRef    = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const markersRef    = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  // Optional overlay series — created/destroyed when toggles flip
  const zoneEntryRef  = useRef<ISeriesApi<"Line">      | null>(null);
  const zoneSLRef     = useRef<ISeriesApi<"Line">      | null>(null);
  const zoneTPRef     = useRef<ISeriesApi<"Line">      | null>(null);
  const ribbonRef     = useRef<ISeriesApi<"Histogram"> | null>(null);

  // Strategy indicator lines (EMA, Donchian, Bollinger, etc.) — rebuilt with the chart
  const indicatorRefs = useRef<ISeriesApi<"Line">[]>([]);

  // Per-selection price lines (cleared on each new selection)
  const selPriceLinesRef = useRef<IPriceLine[]>([]);

  // ── State ─────────────────────────────────────────────────────────────
  const [data,    setData]    = useState<CP | null>(null);
  const [busy,    setBusy]    = useState(false);
  const [err,     setErr]     = useState<string | null>(null);
  const [nBars,   setNBars]   = useState(defaultBars);
  const [localTf, setLocalTf] = useState(timeframe);
  // Re-sync when the top-bar value changes while modal is closed
  useEffect(() => { if (!open) { setNBars(defaultBars); setLocalTf(timeframe); } }, [defaultBars, timeframe, open]);
  const [selIdx, setSelIdx] = useState<number | null>(null);
  const [showZones,      setShowZones]      = useState(true);
  const [showRibbon,     setShowRibbon]     = useState(false);
  const [showIndicators, setShowIndicators] = useState(true);

  const TF_OPTIONS = ["M5", "M15", "M30", "H1", "H4", "D1"];

  // ── Fetch on open / param change ──────────────────────────────────────
  useEffect(() => {
    if (!open || !graph || graph.nodes.length === 0) return;
    setBusy(true); setErr(null); setData(null); setSelIdx(null);
    v2ChartPreview({
      graph, symbol, timeframe: localTf, n_bars: nBars,
      target_r:         mgmt.target_r,
      target_close_pct: mgmt.target_close_pct,
      trail_mode:       mgmt.trail_mode,
      trail_start:      mgmt.trail_start,
      trail_params:     mgmt.trail_params,
    })
      .then(setData)
      .catch((e) => setErr(e.message ?? String(e)))
      .finally(() => setBusy(false));
  }, [open, graph, mgmt, symbol, localTf, nBars]);    // eslint-disable-line react-hooks/exhaustive-deps


  // ── Build chart when data arrives ─────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || !data || data.bars.length === 0) return;

    if (chartRef.current) { chartRef.current.remove(); chartRef.current = null; }
    const el = containerRef.current;

    const chart = createChart(el, {
      layout: {
        background: { color: C.cream },
        textColor:  C.muted,
      },
      grid: {
        vertLines: { color: C.grid },
        horzLines: { color: C.grid },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor:  C.border,
        scaleMargins: { top: 0.08, bottom: 0.18 },   // leave room for ribbon
      },
      timeScale: {
        borderColor:    C.border,
        timeVisible:    true,
        secondsVisible: false,
        rightOffset:    8,
        minBarSpacing:  2,
      },
      handleScroll: true,
      handleScale:  true,
    });
    chartRef.current = chart;

    // Candles
    const candles = chart.addSeries(CandlestickSeries, {
      upColor:         C.sage,
      downColor:       C.terra,
      borderUpColor:   C.sage,
      borderDownColor: C.terra,
      wickUpColor:     C.sage,
      wickDownColor:   C.terra,
    });
    candles.setData(
      data.bars.map((b) => ({
        time:  b.t as UTCTimestamp,
        open:  b.o, high: b.h, low: b.l, close: b.c,
      }))
    );
    candlesRef.current = candles;

    // ── Markers: small dots only — NO text labels (those go on selection) ──
    type M = {
      time:     UTCTimestamp;
      position: SeriesMarkerBarPosition;
      shape:    SeriesMarkerShape;
      color:    string;
      size?:    number;
    };
    const markers: M[] = [];
    data.trades.forEach((tr) => {
      const isBull = tr.direction === "Bull";

      // Signal bar — where the condition fired (small dot above/below)
      if (tr.signal_idx !== null && tr.fill_idx !== null && tr.signal_idx !== tr.fill_idx) {
        const sb = data.bars[tr.signal_idx];
        if (sb) {
          markers.push({
            time:     sb.t as UTCTimestamp,
            position: (isBull ? "belowBar" : "aboveBar") as SeriesMarkerBarPosition,
            color:    (isBull ? C.sage : C.terra) + "88",
            shape:    "circle",
            size:     0.4,
          });
        }
      }

      // Entry fill — large arrow showing direction
      const fi = tr.fill_idx ?? tr.signal_idx;
      const fb = data.bars[fi];
      if (fb) {
        markers.push({
          time:     fb.t as UTCTimestamp,
          position: (isBull ? "belowBar" : "aboveBar") as SeriesMarkerBarPosition,
          color:    isBull ? C.sage : C.terra,
          shape:    (isBull ? "arrowUp" : "arrowDown") as SeriesMarkerShape,
          size:     1.5,
        });
      }

      // Exit marker — X shape
      if (tr.exit_idx !== null) {
        const eb = data.bars[tr.exit_idx];
        if (eb) {
          markers.push({
            time:     eb.t as UTCTimestamp,
            position: (isBull ? "aboveBar" : "belowBar") as SeriesMarkerBarPosition,
            color:    tradeColor(tr),
            shape:    "circle",
            size:     0.8,
          });
        }
      }
    });
    markers.sort((a, b) => (a.time as number) - (b.time as number));
    markersRef.current = createSeriesMarkers(candles, markers);

    // ── Resize ────────────────────────────────────────────────────────
    const ro = new ResizeObserver(() => {
      if (el && chartRef.current) {
        chartRef.current.applyOptions({
          width:  el.clientWidth,
          height: el.clientHeight,
        });
      }
    });
    ro.observe(el);
    chart.timeScale().fitContent();

    return () => {
      ro.disconnect();
      markersRef.current?.detach();
      markersRef.current   = null;
      candlesRef.current   = null;
      zoneEntryRef.current = null;
      zoneSLRef.current    = null;
      zoneTPRef.current    = null;
      ribbonRef.current    = null;
      indicatorRefs.current = [];
      selPriceLinesRef.current = [];
      chart.remove();
      chartRef.current = null;
    };
  }, [data]);   // eslint-disable-line react-hooks/exhaustive-deps


  // ── Strategy indicators (EMA / Donchian / Bollinger / VWAP / …) ──────
  // Drawn on top of the candles as line series. Toggle via the legend pill.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !data) return;

    // Tear down existing indicator lines
    for (const s of indicatorRefs.current) {
      try { chart.removeSeries(s); } catch {}
    }
    indicatorRefs.current = [];

    if (!showIndicators || !data.indicators || data.indicators.length === 0) return;

    const styleMap = {
      solid:  LineStyle.Solid,
      dashed: LineStyle.Dashed,
      dotted: LineStyle.Dotted,
    } as const;

    for (const ind of data.indicators) {
      const series = chart.addSeries(LineSeries, {
        color:                  ind.color,
        lineWidth:              ind.line_width as 1 | 2 | 3 | 4,
        lineStyle:              styleMap[ind.line_style] ?? LineStyle.Solid,
        crosshairMarkerVisible: false,
        lastValueVisible:       false,
        priceLineVisible:       false,
        title:                  ind.label,
      });

      // Build sparse points — undefined breaks the line so warmup bars don't
      // get connected by a phantom segment back to bar 0.
      const points: Array<{ time: UTCTimestamp; value?: number }> = [];
      for (let i = 0; i < data.bars.length && i < ind.values.length; i++) {
        const v = ind.values[i];
        const t = data.bars[i].t as UTCTimestamp;
        if (v === null || v === undefined || !Number.isFinite(v)) {
          points.push({ time: t });
        } else {
          points.push({ time: t, value: v });
        }
      }
      series.setData(points as any);
      indicatorRefs.current.push(series);
    }
  }, [data, showIndicators]);


  // ── Toggle 1: R/R zones (Entry / SL / TP segments for ALL trades) ────
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !data) return;

    // Tear down if turned off
    if (!showZones) {
      if (zoneEntryRef.current) { chart.removeSeries(zoneEntryRef.current); zoneEntryRef.current = null; }
      if (zoneSLRef.current)    { chart.removeSeries(zoneSLRef.current);    zoneSLRef.current    = null; }
      if (zoneTPRef.current)    { chart.removeSeries(zoneTPRef.current);    zoneTPRef.current    = null; }
      return;
    }

    // Build three sparse line series — values only present while a trade is
    // active, undefined otherwise → segments don't extend across the chart.
    const entryArr: Array<{ time: UTCTimestamp; value?: number }> = [];
    const slArr:    Array<{ time: UTCTimestamp; value?: number }> = [];
    const tpArr:    Array<{ time: UTCTimestamp; value?: number }> = [];

    data.bars.forEach((b, i) => {
      const active = data.trades.find((tr) => activeAt(tr, i));
      const t = b.t as UTCTimestamp;
      if (active) {
        entryArr.push({ time: t, value: active.entry });
        slArr   .push({ time: t, value: active.sl    });
        tpArr   .push({ time: t, value: tpPrice(active, mgmt.target_r ?? 3) });
      } else {
        entryArr.push({ time: t });
        slArr   .push({ time: t });
        tpArr   .push({ time: t });
      }
    });

    const entryS = chart.addSeries(LineSeries, {
      color: C.ink, lineWidth: 1, lineStyle: LineStyle.Solid,
      crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
    });
    const slS = chart.addSeries(LineSeries, {
      color: C.terra, lineWidth: 1, lineStyle: LineStyle.Dashed,
      crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
    });
    const tpS = chart.addSeries(LineSeries, {
      color: C.sage, lineWidth: 1, lineStyle: LineStyle.Dashed,
      crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
    });
    entryS.setData(entryArr as any);
    slS   .setData(slArr    as any);
    tpS   .setData(tpArr    as any);

    zoneEntryRef.current = entryS;
    zoneSLRef.current    = slS;
    zoneTPRef.current    = tpS;
  }, [showZones, data, mgmt.target_r]);


  // ── Toggle 2: Position ribbon (histogram at the bottom) ──────────────
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !data) return;

    if (!showRibbon) {
      if (ribbonRef.current) { chart.removeSeries(ribbonRef.current); ribbonRef.current = null; }
      return;
    }

    const ribbon = chart.addSeries(HistogramSeries, {
      priceFormat:    { type: "volume" },
      priceScaleId:   "ribbon",     // separate scale, anchored at bottom
      lastValueVisible: false,
      priceLineVisible: false,
    });
    chart.priceScale("ribbon").applyOptions({
      scaleMargins: { top: 0.92, bottom: 0 },   // hug the bottom 8%
    });

    const arr = data.bars.map((b, i) => {
      const active = data.trades.find((tr) => activeAt(tr, i));
      if (!active) return { time: b.t as UTCTimestamp, value: 0,    color: "transparent" };
      return {
        time:  b.t as UTCTimestamp,
        value: 1,
        color: active.direction === "Bull" ? C.sageF : C.terraF,
      };
    });
    ribbon.setData(arr as any);
    ribbonRef.current = ribbon;
  }, [showRibbon, data]);


  // ── Selection: zoom + show Entry/SL/TP price lines for one trade ─────
  useEffect(() => {
    const chart  = chartRef.current;
    const series = candlesRef.current;
    if (!chart || !series || !data) return;

    // Clear previous selection lines
    for (const pl of selPriceLinesRef.current) {
      try { series.removePriceLine(pl); } catch {}
    }
    selPriceLinesRef.current = [];

    if (selIdx === null) return;
    const tr = data.trades[selIdx];
    if (!tr) return;

    // Entry / SL / TP price lines for this trade
    const tp = tpPrice(tr, mgmt.target_r ?? 3);
    const lines: IPriceLine[] = [
      series.createPriceLine({
        price: tr.entry, color: C.ink, lineWidth: 1, lineStyle: LineStyle.Solid,
        axisLabelVisible: true, title: `Entry #${selIdx + 1}`,
      }),
      series.createPriceLine({
        price: tr.sl, color: C.terra, lineWidth: 1, lineStyle: LineStyle.Dashed,
        axisLabelVisible: true, title: "SL",
      }),
      series.createPriceLine({
        price: tp, color: C.sage, lineWidth: 1, lineStyle: LineStyle.Dashed,
        axisLabelVisible: true, title: `TP ${mgmt.target_r ?? 3}R`,
      }),
    ];
    selPriceLinesRef.current = lines;

    // Zoom to the trade with padding
    const s   = tr.fill_idx ?? tr.signal_idx;
    const e   = tr.exit_idx ?? s + 30;
    const pad = Math.max(15, Math.round((e - s) * 0.5));
    const from = data.bars[Math.max(0, s - pad)];
    const to   = data.bars[Math.min(data.bars.length - 1, e + pad)];
    if (from && to) {
      chart.timeScale().setVisibleRange({
        from: from.t as UTCTimestamp,
        to:   to.t   as UTCTimestamp,
      });
    }
  }, [selIdx, data, mgmt.target_r]);


  if (!open) return null;

  const wins   = data?.trades.filter((t) => t.result === "Win").length  ?? 0;
  const losses = data?.trades.filter((t) => t.result === "Loss").length ?? 0;
  const totalR = data?.trades.reduce((s, t) => s + t.pnl_r, 0)         ?? 0;
  const selTrade = selIdx !== null ? data?.trades[selIdx] : null;

  return (
    <div className="fixed inset-0 z-50 bg-cream/95 backdrop-blur-sm flex items-center justify-center p-3">
      <div className="bg-cream2 border border-border rounded-2xl shadow-2xl w-full max-w-[1400px] h-[93vh] flex flex-col overflow-hidden">

        {/* ── Header ─────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-border shrink-0">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="font-semibold text-sm">{symbol}</span>
            {data?.data_source?.label && (
              <span
                title="The data source actually used for this run"
                className={`text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${
                  data.data_source.provider === "mt5"
                    ? "bg-sage/15 border-sage/40 text-sage"
                    : "bg-amber/25 border-amber/50 text-amber-900"
                }`}
              >
                {data.data_source.provider === "mt5" ? "● " : "⚠ "}{data.data_source.label}
              </span>
            )}
            {/* Timeframe switcher */}
            <div className="flex items-center gap-0.5 bg-cream rounded-lg border border-border p-0.5">
              {TF_OPTIONS.map((tf) => (
                <button
                  key={tf}
                  onClick={() => setLocalTf(tf)}
                  disabled={busy}
                  className={`text-[10.5px] px-2 py-0.5 rounded-md font-medium transition-colors ${
                    localTf === tf
                      ? "bg-ink text-cream shadow-sm"
                      : "text-muted hover:text-ink"
                  }`}
                >
                  {tf}
                </button>
              ))}
            </div>
            {data && (
              <>
                <span className="text-muted text-xs">·</span>
                <span className="text-xs text-muted">{data.bars.length} bars</span>
                <span className="text-muted text-xs">·</span>
                <span className="text-xs text-muted">{data.n_setups} setups</span>
                <span className="text-muted text-xs">·</span>
                <span className="text-xs font-semibold">{data.trades.length} trades</span>
                {data.trades.length > 0 && (
                  <>
                    <span className="text-muted text-xs">·</span>
                    <span className="text-xs font-medium text-sage">{wins}W</span>
                    <span className="text-xs font-medium text-terra ml-0.5">{losses}L</span>
                    <span className="text-muted text-xs">·</span>
                    <span className={`text-xs font-semibold font-mono ${totalR >= 0 ? "text-sage" : "text-terra"}`}>
                      {totalR >= 0 ? "+" : ""}{totalR.toFixed(1)}R
                    </span>
                  </>
                )}
              </>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {/* Toggle pills */}
            <button
              onClick={() => setShowIndicators((v) => !v)}
              title="Show the strategy's indicators (EMA, Donchian, Bollinger, VWAP, etc.) on the chart"
              className={`text-[11px] px-2.5 py-1 rounded-full border transition-colors flex items-center gap-1.5
                ${showIndicators ? "bg-sage/15 border-sage/40 text-sage" : "bg-cream border-border text-muted hover:bg-cream2"}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${showIndicators ? "bg-sage" : "bg-muted"}`} />
              Indicators{data?.indicators && data.indicators.length > 0 ? ` (${data.indicators.length})` : ""}
            </button>
            <button
              onClick={() => setShowZones((v) => !v)}
              title="Show Entry / SL / TP segments for every trade (only while live)"
              className={`text-[11px] px-2.5 py-1 rounded-full border transition-colors flex items-center gap-1.5
                ${showZones ? "bg-sage/15 border-sage/40 text-sage" : "bg-cream border-border text-muted hover:bg-cream2"}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${showZones ? "bg-sage" : "bg-muted"}`} />
              R/R zones
            </button>
            <button
              onClick={() => setShowRibbon((v) => !v)}
              title="Show a band at the bottom indicating when the strategy was in a long / short position"
              className={`text-[11px] px-2.5 py-1 rounded-full border transition-colors flex items-center gap-1.5
                ${showRibbon ? "bg-amber/30 border-amber/50 text-amber-900" : "bg-cream border-border text-muted hover:bg-cream2"}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${showRibbon ? "bg-amber" : "bg-muted"}`} />
              Position ribbon
            </button>

            <div className="w-px h-5 bg-border mx-1" />
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-muted uppercase tracking-widest">Bars</span>
              <input
                type="number" value={nBars} min={100} max={20000} step={500}
                onChange={(e) => setNBars(parseInt(e.target.value || String(defaultBars)))}
                className="w-16 text-xs rounded bg-cream border border-border px-2 py-1 focus:outline-none focus:ring-1 focus:ring-sage"
              />
            </div>
            <button onClick={onClose}
              className="w-8 h-8 rounded-full hover:bg-cream flex items-center justify-center text-muted hover:text-ink text-xl leading-none transition-colors">
              ×
            </button>
          </div>
        </div>

        {/* ── Body ────────────────────────────────────────────────────── */}
        <div className="flex-1 flex min-h-0">

          {/* Chart */}
          <div className="flex-1 relative min-w-0">
            {busy && (
              <div className="absolute inset-0 flex flex-col items-center justify-center z-10 bg-cream/80">
                <div className="text-4xl animate-pulse mb-3">📊</div>
                <div className="text-sm text-muted">Loading bars and simulating trades…</div>
              </div>
            )}
            {err && (
              <div className="absolute inset-0 flex items-center justify-center z-10 p-8">
                <div className="bg-cream border border-border rounded-xl px-6 py-4 text-sm text-terra max-w-md text-center shadow-lg">
                  {err}
                </div>
              </div>
            )}
            <div ref={containerRef} className="w-full h-full" />

            {/* Floating overlay: selected trade detail */}
            {selTrade && (
              <div className="absolute top-3 left-3 z-10 bg-cream2 border border-border rounded-lg shadow-md px-3 py-2 text-[11px] max-w-[280px]">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-semibold" style={{ color: selTrade.direction === "Bull" ? C.sage : C.terra }}>
                    #{(selIdx ?? 0) + 1} · {selTrade.direction === "Bull" ? "▲ Long" : "▼ Short"}
                  </span>
                  <span className="ml-auto font-mono font-semibold" style={{ color: tradeColor(selTrade) }}>
                    {selTrade.pnl_r >= 0 ? "+" : ""}{selTrade.pnl_r.toFixed(2)}R
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-muted font-mono">
                  <span>Entry</span><span className="text-ink">{selTrade.entry.toFixed(2)}</span>
                  <span>SL</span>   <span className="text-terra">{selTrade.sl.toFixed(2)}</span>
                  <span>TP {mgmt.target_r ?? 3}R</span><span className="text-sage">{tpPrice(selTrade, mgmt.target_r ?? 3).toFixed(2)}</span>
                  <span>Exit</span> <span className="text-ink">{selTrade.exit_type || selTrade.result}</span>
                </div>
                <button onClick={() => setSelIdx(null)}
                  className="text-[10px] text-muted hover:text-ink underline mt-1">
                  Clear selection
                </button>
              </div>
            )}
          </div>

          {/* Trade list */}
          {data && data.trades.length > 0 && (
            <div className="w-64 shrink-0 border-l border-border flex flex-col">
              <div className="px-4 py-2.5 border-b border-border shrink-0">
                <div className="text-xs font-semibold text-ink">Trade history</div>
                <div className="text-[10px] text-muted mt-0.5">Click any trade to zoom + reveal levels</div>
              </div>

              <div className="flex-1 overflow-y-auto">
                {data.trades.map((tr, i) => {
                  const isSel  = selIdx === i;
                  const col    = tradeColor(tr);
                  const isBull = tr.direction === "Bull";
                  const pnlStr = `${tr.pnl_r >= 0 ? "+" : ""}${tr.pnl_r.toFixed(1)}R`;
                  return (
                    <button key={i}
                      onClick={() => setSelIdx(isSel ? null : i)}
                      className={`w-full text-left px-4 py-2.5 border-b border-border/50 transition-all text-xs hover:bg-cream
                        ${isSel ? "bg-cream border-l-[3px] border-l-sage" : "border-l-[3px] border-l-transparent"}`}
                    >
                      <div className="flex items-center justify-between mb-0.5">
                        <div className="flex items-center gap-1.5">
                          <span className="text-muted font-mono text-[10px]">#{i + 1}</span>
                          <span className="font-semibold text-[11px]"
                            style={{ color: isBull ? C.sage : C.terra }}>
                            {isBull ? "▲" : "▼"} {tr.entry.toFixed(2)}
                          </span>
                        </div>
                        <span className="font-semibold font-mono text-[11px]" style={{ color: col }}>
                          {pnlStr}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-muted">
                        <span>SL <span className="font-mono">{tr.sl.toFixed(2)}</span></span>
                        <span className="px-1.5 py-0.5 rounded-full text-[9px] font-medium"
                          style={{ background: col + "22", color: col }}>
                          {tr.exit_type || tr.result}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>

              <div className="px-4 py-2.5 border-t border-border shrink-0 bg-cream/60">
                <div className="flex justify-between text-[10px] text-muted">
                  <span>Win: <strong className="text-sage">{wins}</strong></span>
                  <span>Loss: <strong className="text-terra">{losses}</strong></span>
                  <span>Net: <strong style={{ color: totalR >= 0 ? C.sage : C.terra }}>
                    {totalR >= 0 ? "+" : ""}{totalR.toFixed(1)}R
                  </strong></span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ── Legend ───────────────────────────────────────────────────── */}
        <div className="px-5 py-2 border-t border-border shrink-0 bg-cream/50 flex flex-wrap items-center gap-x-5 gap-y-1 text-[10px] text-muted">
          <span className="flex items-center gap-1.5">
            <span className="text-[10px]" style={{ color: C.sage }}>▲</span> Long entry
          </span>
          <span className="flex items-center gap-1.5">
            <span className="text-[10px]" style={{ color: C.terra }}>▼</span> Short entry
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-2 h-2 rounded-full" style={{ background: C.sage }} /> Win exit
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-2 h-2 rounded-full" style={{ background: C.terra }} /> Loss exit
          </span>
          {showZones && (
            <>
              <span className="flex items-center gap-1.5">
                <span className="inline-block w-5 border-t" style={{ borderColor: C.ink }} /> Entry
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block w-5 border-t border-dashed" style={{ borderColor: C.terra }} /> SL
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block w-5 border-t border-dashed" style={{ borderColor: C.sage }} /> TP
              </span>
            </>
          )}
          {showIndicators && data?.indicators && data.indicators.map((ind) => (
            <span key={ind.id} className="flex items-center gap-1.5">
              <span
                className="inline-block w-5"
                style={{
                  borderTop:    `${ind.line_width}px ${ind.line_style} ${ind.color}`,
                }}
              />
              {ind.label}
            </span>
          ))}
          <span className="ml-auto italic">Click row → zoom + show levels · Scroll → zoom · Drag → pan</span>
        </div>
      </div>
    </div>
  );
}
