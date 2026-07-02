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
import { useEffect, useMemo, useRef, useState } from "react";
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
import { loadSettings } from "@/lib/settings";


// ── Palette ───────────────────────────────────────────────────────────────
const C = {
  sage:   "#6B9B7A",
  sageF:  "#6B9B7A55",
  terra:  "#C97B63",
  terraF: "#C97B6355",
  amber:  "#D4A574",
  muted:  "#8A8071",
  cream:  "#FAF7EE",
  border: "#D4CCB8",
  ink:    "#2C3E2D",
  grid:   "#EAE5D8",
};

// Fraction of the chart width to leave blank on the right in the live (non-replay)
// view, so the latest candle has breathing room instead of sitting on the price
// axis. Replay mode reserves its own right margin separately (see futureT below).
const LIVE_RIGHT_BLANK = 0.5;

// Show every bar but pack them into the left (1 - LIVE_RIGHT_BLANK) of the width,
// leaving the rest empty on the right. Falls back to fitContent for tiny series.
function applyLiveView(chart: IChartApi, barCount: number) {
  const ts = chart.timeScale();
  if (barCount < 2) { ts.fitContent(); return; }
  ts.setVisibleLogicalRange({ from: 0, to: (barCount - 1) / (1 - LIVE_RIGHT_BLANK) });
}


// ── Structural-zone primitive ─────────────────────────────────────────────
type ZShape =
  | { type: "rect";  t1: UTCTimestamp; t2: UTCTimestamp; hi: number; lo: number; fill: string; stroke: string }
  | { type: "hline"; t1: UTCTimestamp; t2: UTCTimestamp; price: number; color: string };

class ZonesPrimitive {
  _chart: IChartApi | null = null;
  _series: ISeriesApi<"Candlestick"> | null = null;
  _requestUpdate?: () => void;
  _shapes: ZShape[] = [];
  _paneViews: any[];
  constructor() { this._paneViews = [new ZonesPaneView(this)]; }
  attached(p: any) { this._chart = p.chart; this._series = p.series; this._requestUpdate = p.requestUpdate; }
  detached() { this._chart = null; this._series = null; }
  updateAllViews() {}
  paneViews() { return this._paneViews; }
  setShapes(s: ZShape[]) { this._shapes = s; this._requestUpdate?.(); }
}
class ZonesPaneView {
  constructor(private _src: ZonesPrimitive) {}
  update() {}
  renderer() { return new ZonesRenderer(this._src); }
}
class ZonesRenderer {
  constructor(private _src: ZonesPrimitive) {}
  draw(target: any) {
    const { _chart: chart, _series: series, _shapes: shapes } = this._src;
    if (!chart || !series) return;
    const ts = chart.timeScale();
    target.useBitmapCoordinateSpace((scope: any) => {
      const ctx: CanvasRenderingContext2D = scope.context;
      const hr = scope.horizontalPixelRatio, vr = scope.verticalPixelRatio;
      for (const s of shapes) {
        const x1 = ts.timeToCoordinate(s.t1);
        const x2 = ts.timeToCoordinate(s.t2);
        if (x1 == null || x2 == null) continue;
        if (s.type === "rect") {
          const y1 = series.priceToCoordinate(s.hi);
          const y2 = series.priceToCoordinate(s.lo);
          if (y1 == null || y2 == null) continue;
          const left = Math.min(x1, x2) * hr, right = Math.max(x1, x2) * hr;
          const top  = Math.min(y1, y2) * vr, bot   = Math.max(y1, y2) * vr;
          const h = Math.max(1, bot - top);
          ctx.fillStyle = s.fill;   ctx.fillRect(left, top, right - left, h);
          ctx.strokeStyle = s.stroke; ctx.lineWidth = 1 * hr;
          ctx.strokeRect(left, top, right - left, h);
        } else {
          const y = series.priceToCoordinate(s.price);
          if (y == null) continue;
          ctx.strokeStyle = s.color; ctx.lineWidth = 1.5 * hr;
          ctx.setLineDash([4 * hr, 3 * hr]);
          ctx.beginPath();
          ctx.moveTo(Math.min(x1, x2) * hr, y * vr);
          ctx.lineTo(Math.max(x1, x2) * hr, y * vr);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }
    });
  }
}


// ── Position-box primitive ────────────────────────────────────────────────
type TBox = {
  t1: UTCTimestamp; t2: UTCTimestamp;
  entry: number; sl: number; tp: number;
  isBull: boolean; sel: boolean;
};

class PositionBoxesPrimitive {
  _chart: IChartApi | null = null;
  _series: ISeriesApi<"Candlestick"> | null = null;
  _requestUpdate?: () => void;
  _boxes: TBox[] = [];
  _paneViews: any[];
  constructor() { this._paneViews = [new PositionBoxesPaneView(this)]; }
  attached(p: any) { this._chart = p.chart; this._series = p.series; this._requestUpdate = p.requestUpdate; }
  detached() { this._chart = null; this._series = null; }
  updateAllViews() {}
  paneViews() { return this._paneViews; }
  setBoxes(b: TBox[]) { this._boxes = b; this._requestUpdate?.(); }
}
class PositionBoxesPaneView {
  constructor(private _src: PositionBoxesPrimitive) {}
  update() {}
  renderer() { return new PositionBoxesRenderer(this._src); }
}
class PositionBoxesRenderer {
  constructor(private _src: PositionBoxesPrimitive) {}
  draw(target: any) {
    const { _chart: chart, _series: series, _boxes: boxes } = this._src;
    if (!chart || !series || !boxes.length) return;
    const ts = chart.timeScale();
    target.useBitmapCoordinateSpace((scope: any) => {
      const ctx: CanvasRenderingContext2D = scope.context;
      const hr = scope.horizontalPixelRatio, vr = scope.verticalPixelRatio;

      for (const box of boxes) {
        const x1 = ts.timeToCoordinate(box.t1);
        const x2 = ts.timeToCoordinate(box.t2);
        if (x1 == null || x2 == null) continue;
        const yE = series.priceToCoordinate(box.entry);
        const yS = series.priceToCoordinate(box.sl);
        const yT = series.priceToCoordinate(box.tp);
        if (yE == null || yS == null || yT == null) continue;

        const left  = Math.min(x1, x2) * hr;
        const right = Math.max(x1, x2) * hr;
        const w     = Math.max(2, right - left);
        const a     = box.sel ? 0.26 : 0.12;

        ctx.fillStyle = `rgba(107,155,122,${a})`;
        ctx.fillRect(left, Math.min(yE, yT) * vr, w, Math.abs(yT - yE) * vr);
        ctx.fillStyle = `rgba(201,123,99,${a})`;
        ctx.fillRect(left, Math.min(yE, yS) * vr, w, Math.abs(yS - yE) * vr);

        const lw = (box.sel ? 1.5 : 1) * hr;

        ctx.strokeStyle = box.sel ? "rgba(107,155,122,1.0)" : "rgba(107,155,122,0.65)";
        ctx.lineWidth = lw; ctx.setLineDash([4 * hr, 3 * hr]);
        ctx.beginPath(); ctx.moveTo(left, yT * vr); ctx.lineTo(right, yT * vr); ctx.stroke();

        ctx.strokeStyle = box.sel ? "rgba(201,123,99,1.0)" : "rgba(201,123,99,0.65)";
        ctx.lineWidth = lw;
        ctx.beginPath(); ctx.moveTo(left, yS * vr); ctx.lineTo(right, yS * vr); ctx.stroke();

        ctx.strokeStyle = box.sel ? "rgba(44,62,45,1.0)" : "rgba(44,62,45,0.55)";
        ctx.lineWidth = lw; ctx.setLineDash([]);
        ctx.beginPath(); ctx.moveTo(left, yE * vr); ctx.lineTo(right, yE * vr); ctx.stroke();

        ctx.strokeStyle = box.isBull ? "rgba(107,155,122,0.6)" : "rgba(201,123,99,0.6)";
        ctx.lineWidth = 2 * hr;
        ctx.beginPath();
        ctx.moveTo(x1 * hr, Math.min(yS, yT) * vr);
        ctx.lineTo(x1 * hr, Math.max(yS, yT) * vr);
        ctx.stroke();
      }
    });
  }
}


// ── Replay start-line primitive ───────────────────────────────────────
class ReplayStartLinePrimitive {
  _chart: IChartApi | null = null;
  _series: ISeriesApi<"Candlestick"> | null = null;
  _requestUpdate?: () => void;
  _time: UTCTimestamp | null = null;
  _paneViews: any[];
  constructor() { this._paneViews = [new ReplayStartLinePaneView(this)]; }
  attached(p: any) { this._chart = p.chart; this._series = p.series; this._requestUpdate = p.requestUpdate; }
  detached() { this._chart = null; this._series = null; }
  updateAllViews() {}
  paneViews() { return this._paneViews; }
  setTime(t: UTCTimestamp | null) { this._time = t; this._requestUpdate?.(); }
}
class ReplayStartLinePaneView {
  constructor(private _src: ReplayStartLinePrimitive) {}
  update() {}
  renderer() { return new ReplayStartLineRenderer(this._src); }
}
class ReplayStartLineRenderer {
  constructor(private _src: ReplayStartLinePrimitive) {}
  draw(target: any) {
    const { _chart: chart, _time: time } = this._src;
    if (!chart || time == null) return;
    const ts = chart.timeScale();
    target.useBitmapCoordinateSpace((scope: any) => {
      const ctx: CanvasRenderingContext2D = scope.context;
      const hr = scope.horizontalPixelRatio;
      const x = ts.timeToCoordinate(time);
      if (x == null) return;
      ctx.strokeStyle = "#3B82F6";
      ctx.lineWidth = 1.5 * hr;
      ctx.setLineDash([6 * hr, 4 * hr]);
      ctx.beginPath();
      ctx.moveTo(x * hr, 0);
      ctx.lineTo(x * hr, scope.context.canvas.height);
      ctx.stroke();
      ctx.setLineDash([]);
    });
  }
}


function tpPrice(tr: ChartTrade, targetR: number) {
  const r1 = Math.abs(tr.entry - tr.sl);
  return tr.direction === "Bull" ? tr.entry + r1 * targetR : tr.entry - r1 * targetR;
}

function tradeColor(tr: ChartTrade) {
  if (tr.result === "Win")  return C.sage;
  if (tr.result === "Loss") return C.terra;
  return C.muted;
}

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
  defaultBars?: number;
}) {
  // ── Refs ──────────────────────────────────────────────────────────────
  const containerRef      = useRef<HTMLDivElement>(null);
  const chartRef          = useRef<IChartApi | null>(null);
  const candlesRef        = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const markersRef        = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const allMarkersRef     = useRef<any[]>([]);
  const lastViewCutoffRef = useRef<number | null>(null);
  const posBoxPrimRef     = useRef<PositionBoxesPrimitive | null>(null);
  const startLinePrimRef  = useRef<ReplayStartLinePrimitive | null>(null);
  const replayStartIdxRef = useRef<number | null>(null);
  const ribbonRef         = useRef<ISeriesApi<"Histogram"> | null>(null);
  const indicatorRefs     = useRef<ISeriesApi<"Line">[]>([]);
  const oscSeriesRef      = useRef<ISeriesApi<any>[]>([]);
  const oscPanesRef       = useRef<number[]>([]);
  const zonesPrimRef      = useRef<ZonesPrimitive | null>(null);
  const selPriceLinesRef  = useRef<IPriceLine[]>([]);
  // Stable refs so keyboard/pick handlers don't go stale during fast playback
  const replayIdxRef      = useRef<number | null>(null);
  const dataRef           = useRef<CP | null>(null);

  // ── State ─────────────────────────────────────────────────────────────
  const [data,    setData]    = useState<CP | null>(null);
  const [busy,    setBusy]    = useState(false);
  const [err,     setErr]     = useState<string | null>(null);
  const [nBars,   setNBars]   = useState(defaultBars);
  const [localTf, setLocalTf] = useState(timeframe);
  useEffect(() => { if (!open) { setNBars(defaultBars); setLocalTf(timeframe); } }, [defaultBars, timeframe, open]);

  const [selIdx, setSelIdx] = useState<number | null>(null);

  // posMode: 0 = off · 1 = selected trade only (default) · 2 = all trades
  const [posMode,        setPosMode]        = useState<0 | 1 | 2>(1);
  const [showRibbon,     setShowRibbon]     = useState(false);
  const [showIndicators, setShowIndicators] = useState(true);
  const [showStructures, setShowStructures] = useState(true);
  const [showTradeHistory, setShowTradeHistory] = useState(true);

  // Replay
  const [replayIdx, setReplayIdx] = useState<number | null>(null);
  const [playing,   setPlaying]   = useState(false);
  const [speed,     setSpeed]     = useState<number>(1);
  const [pickMode,  setPickMode]  = useState(false);

  // Keep stable refs in sync so keyboard/pick handlers never capture stale values
  useEffect(() => { replayIdxRef.current = replayIdx; }, [replayIdx]);
  useEffect(() => { dataRef.current = data; }, [data]);

  // Editable position tool — live entry/SL/TP for the selected trade
  const [editEntry, setEditEntry] = useState<number | null>(null);
  const [editSl,    setEditSl]    = useState<number | null>(null);
  const [editTp,    setEditTp]    = useState<number | null>(null);

  const TF_OPTIONS = ["M5", "M15", "M30", "H1", "H4", "D1"];

  // ── Fetch ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!open || !graph || graph.nodes.length === 0) return;
    setBusy(true); setErr(null); setData(null); setSelIdx(null);
    // Same Settings-derived execution/order fields the real Run backtest uses
    // — otherwise the preview can show trades the real backtest wouldn't
    // (different costs, no session-hours filter, no concurrency cap).
    const s = loadSettings();
    v2ChartPreview({
      graph, symbol,
      timeframe: timeframe,
      view_tf:   localTf !== timeframe ? localTf : undefined,
      n_bars: nBars,
      target_r:         mgmt.target_r,
      target_close_pct: mgmt.target_close_pct,
      trail_mode:       mgmt.trail_mode,
      trail_start:      mgmt.trail_start,
      trail_params:     mgmt.trail_params,
      spread_pips:      s.spread_pips,
      commission:       s.commission,
      slippage_pips:    s.slippage_pips,
      swap_long_pips:   s.swap_long_pips,
      swap_short_pips:  s.swap_short_pips,
      max_concurrent:   s.max_concurrent,
      risk_pct:         s.risk_pct,
      max_risk_usd:     s.max_risk_usd,
    })
      .then(setData)
      .catch((e) => setErr(e.message ?? String(e)))
      .finally(() => setBusy(false));
  }, [open, graph, mgmt, symbol, localTf, nBars]);  // eslint-disable-line react-hooks/exhaustive-deps


  // ── Build chart ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || !data || data.bars.length === 0) return;

    if (chartRef.current) { chartRef.current.remove(); chartRef.current = null; }
    const el = containerRef.current;

    const chart = createChart(el, {
      layout: { background: { color: C.cream }, textColor: C.muted },
      grid:   { vertLines: { color: C.grid }, horzLines: { color: C.grid } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: C.border, scaleMargins: { top: 0.08, bottom: 0.18 } },
      timeScale: {
        borderColor: C.border, timeVisible: true, secondsVisible: false,
        rightOffset: 8, minBarSpacing: 2,
      },
      handleScroll: true, handleScale: true,
    });
    chartRef.current = chart;

    const displayBars = data.view_bars ?? data.bars;
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: C.sage, downColor: C.terra,
      borderUpColor: C.sage, borderDownColor: C.terra,
      wickUpColor: C.sage, wickDownColor: C.terra,
    });
    candles.setData(displayBars.map((b) => ({ time: b.t as UTCTimestamp, open: b.o, high: b.h, low: b.l, close: b.c })));
    candlesRef.current = candles;

    try {
      const zp = new ZonesPrimitive();
      (candles as any).attachPrimitive?.(zp);
      zonesPrimRef.current = zp;
    } catch { zonesPrimRef.current = null; }

    try {
      const pb = new PositionBoxesPrimitive();
      (candles as any).attachPrimitive?.(pb);
      posBoxPrimRef.current = pb;
    } catch { posBoxPrimRef.current = null; }

    try {
      const sl = new ReplayStartLinePrimitive();
      (candles as any).attachPrimitive?.(sl);
      startLinePrimRef.current = sl;
    } catch { startLinePrimRef.current = null; }

    type M = { time: UTCTimestamp; position: SeriesMarkerBarPosition; shape: SeriesMarkerShape; color: string; size?: number };
    const markers: M[] = [];
    data.trades.forEach((tr) => {
      const isBull = tr.direction === "Bull";
      if (tr.signal_idx !== null && tr.fill_idx !== null && tr.signal_idx !== tr.fill_idx) {
        const sb = data.bars[tr.signal_idx];
        if (sb) markers.push({ time: sb.t as UTCTimestamp, position: (isBull ? "belowBar" : "aboveBar") as SeriesMarkerBarPosition, color: (isBull ? C.sage : C.terra) + "88", shape: "circle", size: 0.4 });
      }
      const fi = tr.fill_idx ?? tr.signal_idx;
      const fb = data.bars[fi];
      if (fb) markers.push({ time: fb.t as UTCTimestamp, position: (isBull ? "belowBar" : "aboveBar") as SeriesMarkerBarPosition, color: isBull ? C.sage : C.terra, shape: (isBull ? "arrowUp" : "arrowDown") as SeriesMarkerShape, size: 1.5 });
      if (tr.exit_idx !== null) {
        const eb = data.bars[tr.exit_idx];
        if (eb) markers.push({ time: eb.t as UTCTimestamp, position: (isBull ? "aboveBar" : "belowBar") as SeriesMarkerBarPosition, color: tradeColor(tr), shape: "circle", size: 0.8 });
      }
    });
    markers.sort((a, b) => (a.time as number) - (b.time as number));
    allMarkersRef.current = markers;
    markersRef.current = createSeriesMarkers(candles, markers);

    const ro = new ResizeObserver(() => {
      if (el && chartRef.current) chartRef.current.applyOptions({ width: el.clientWidth, height: el.clientHeight });
    });
    ro.observe(el);
    applyLiveView(chart, displayBars.length);

    return () => {
      ro.disconnect();
      markersRef.current?.detach();
      markersRef.current = null; candlesRef.current = null;
      zonesPrimRef.current = null; posBoxPrimRef.current = null;
      startLinePrimRef.current = null;
      ribbonRef.current = null; indicatorRefs.current = [];
      oscSeriesRef.current = []; oscPanesRef.current = [];
      selPriceLinesRef.current = [];
      lastViewCutoffRef.current = null;
      replayStartIdxRef.current = null;
      chart.remove(); chartRef.current = null;
    };
  }, [data]);  // eslint-disable-line react-hooks/exhaustive-deps


  // ── Strategy indicators ───────────────────────────────────────────────
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !data) return;
    // Adding/removing series makes lightweight-charts re-fit the time scale,
    // which snaps the candles back to the right edge. Snapshot the view and
    // restore it so toggling an indicator keeps the current framing.
    const savedRange = chart.timeScale().getVisibleLogicalRange();
    for (const s of indicatorRefs.current) { try { chart.removeSeries(s); } catch {} }
    indicatorRefs.current = [];
    const overlays = (data.indicators ?? []).filter((ind) => ind.kind !== "oscillator");
    if (showIndicators && overlays.length > 0) {
      const styleMap = { solid: LineStyle.Solid, dashed: LineStyle.Dashed, dotted: LineStyle.Dotted } as const;
      for (const ind of overlays) {
        const series = chart.addSeries(LineSeries, {
          color: ind.color, lineWidth: ind.line_width as 1|2|3|4,
          lineStyle: styleMap[ind.line_style] ?? LineStyle.Solid,
          crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
          title: ind.label,
        });
        const points: Array<{ time: UTCTimestamp; value?: number }> = [];
        for (let i = 0; i < data.bars.length && i < ind.values.length; i++) {
          const v = ind.values[i];
          const t = data.bars[i].t as UTCTimestamp;
          points.push(v === null || v === undefined || !Number.isFinite(v) ? { time: t } : { time: t, value: v });
        }
        series.setData(points as any);
        indicatorRefs.current.push(series);
      }
    }
    if (savedRange) chart.timeScale().setVisibleLogicalRange(savedRange);
  }, [data, showIndicators]);


  // ── Oscillator indicators (RSI/MACD/ADX/Stochastic/CCI/Williams%R/ROC) ──
  // These don't share the candlestick's price scale, so each node gets its
  // own pane stacked below the chart — same layout TradingView uses.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !data) return;

    for (const s of oscSeriesRef.current) { try { chart.removeSeries(s); } catch {} }
    oscSeriesRef.current = [];
    for (const idx of [...oscPanesRef.current].sort((a, b) => b - a)) {
      try { (chart as any).removePane(idx); } catch {}
    }
    oscPanesRef.current = [];

    const osc = showIndicators ? (data.indicators ?? []).filter((ind) => ind.kind === "oscillator") : [];
    if (osc.length === 0) return;

    // Group series by pane_id so e.g. MACD's macd/signal/histogram share one pane.
    const groups = new Map<string, typeof osc>();
    for (const ind of osc) {
      const key = ind.pane_id ?? ind.node_id;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(ind);
    }

    const styleMap = { solid: LineStyle.Solid, dashed: LineStyle.Dashed, dotted: LineStyle.Dotted } as const;
    let paneIndex = 1;   // pane 0 is the main candlestick pane
    for (const group of groups.values()) {
      for (const ind of group) {
        const series = ind.series_type === "histogram"
          ? chart.addSeries(HistogramSeries, {
              color: ind.color, lastValueVisible: false, priceLineVisible: false, title: ind.label,
            }, paneIndex)
          : chart.addSeries(LineSeries, {
              color: ind.color, lineWidth: ind.line_width as 1 | 2 | 3 | 4,
              lineStyle: styleMap[ind.line_style] ?? LineStyle.Solid,
              crosshairMarkerVisible: false, lastValueVisible: true, priceLineVisible: false,
              title: ind.label,
            }, paneIndex);
        const points: Array<{ time: UTCTimestamp; value?: number }> = [];
        for (let i = 0; i < data.bars.length && i < ind.values.length; i++) {
          const v = ind.values[i];
          const t = data.bars[i].t as UTCTimestamp;
          points.push(v === null || v === undefined || !Number.isFinite(v) ? { time: t } : { time: t, value: v });
        }
        series.setData(points as any);
        oscSeriesRef.current.push(series);

        if (ind.ref_lines && ind.series_type !== "histogram") {
          for (const lvl of ind.ref_lines) {
            try {
              series.createPriceLine({
                price: lvl, color: "#8A807166", lineWidth: 1,
                lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "",
              });
            } catch { /* ignore */ }
          }
        }
      }
      try { (chart as any).panes?.()[paneIndex]?.setHeight(110); } catch { /* ignore */ }
      oscPanesRef.current.push(paneIndex);
      paneIndex++;
    }
  }, [data, showIndicators]);


  // ── Structural zones ──────────────────────────────────────────────────
  useEffect(() => {
    const zp = zonesPrimRef.current;
    if (!zp || !data) return;
    if (!showStructures || !data.artifacts || data.artifacts.length === 0) { zp.setShapes([]); return; }
    const bars = data.bars;
    const shapes: ZShape[] = [];
    for (const a of data.artifacts) {
      if (a.kind === "zone" && a.from_idx != null && a.to_idx != null && a.price_hi != null && a.price_lo != null) {
        const b1 = bars[a.from_idx]; const b2 = bars[a.to_idx];
        if (!b1 || !b2) continue;
        const bull = a.color_hint !== "bear";
        shapes.push({ type: "rect", t1: b1.t as UTCTimestamp, t2: b2.t as UTCTimestamp, hi: a.price_hi, lo: a.price_lo, fill: bull ? "rgba(107,155,122,0.10)" : "rgba(201,123,99,0.10)", stroke: bull ? "rgba(107,155,122,0.55)" : "rgba(201,123,99,0.55)" });
      } else if (a.kind === "level" && a.at_idx != null && a.price != null) {
        const b1 = bars[a.at_idx]; const b2 = bars[Math.min(bars.length - 1, a.at_idx + 15)];
        if (!b1 || !b2) continue;
        shapes.push({ type: "hline", t1: b1.t as UTCTimestamp, t2: b2.t as UTCTimestamp, price: a.price, color: a.color_hint === "bear" ? "rgba(201,123,99,0.9)" : "rgba(107,155,122,0.9)" });
      }
    }
    zp.setShapes(shapes);
  }, [data, showStructures]);


  // ── Position boxes ─────────────────────────────────────────────────────
  // posMode 0 = off · 1 = selected trade only · 2 = all trades
  // Selected trade uses editEntry/editSl/editTp for live what-if adjustment.
  useEffect(() => {
    const pb = posBoxPrimRef.current;
    if (!pb || !data) return;

    if (posMode === 0) { pb.setBoxes([]); return; }

    const tR = mgmt.target_r ?? 3;
    const boxes: TBox[] = [];
    data.trades.forEach((tr, i) => {
      const isSel = i === selIdx;
      if (posMode === 1 && !isSel) return;

      const fi = tr.fill_idx ?? tr.signal_idx;
      const ei = tr.exit_idx ?? Math.min(data.bars.length - 1, fi + 60);
      const b1 = data.bars[fi]; const b2 = data.bars[ei];
      if (!b1 || !b2) return;

      boxes.push({
        t1:     b1.t as UTCTimestamp,
        t2:     b2.t as UTCTimestamp,
        entry:  isSel && editEntry !== null ? editEntry : tr.entry,
        sl:     isSel && editSl    !== null ? editSl    : tr.sl,
        tp:     isSel && editTp    !== null ? editTp    : tpPrice(tr, tR),
        isBull: tr.direction === "Bull",
        sel:    isSel,
      });
    });
    pb.setBoxes(boxes);
  }, [posMode, data, mgmt.target_r, selIdx, editEntry, editSl, editTp]);


  // ── Position ribbon ───────────────────────────────────────────────────
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !data) return;
    // Preserve framing across the series add/remove (see indicators effect).
    const savedRange = chart.timeScale().getVisibleLogicalRange();
    if (!showRibbon) {
      if (ribbonRef.current) { chart.removeSeries(ribbonRef.current); ribbonRef.current = null; }
      if (savedRange) chart.timeScale().setVisibleLogicalRange(savedRange);
      return;
    }
    const ribbon = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" }, priceScaleId: "ribbon",
      lastValueVisible: false, priceLineVisible: false,
    });
    chart.priceScale("ribbon").applyOptions({ scaleMargins: { top: 0.92, bottom: 0 } });
    const arr = data.bars.map((b, i) => {
      const active = data.trades.find((tr) => activeAt(tr, i));
      if (!active) return { time: b.t as UTCTimestamp, value: 0, color: "transparent" };
      return { time: b.t as UTCTimestamp, value: 1, color: active.direction === "Bull" ? C.sageF : C.terraF };
    });
    ribbon.setData(arr as any);
    ribbonRef.current = ribbon;
    if (savedRange) chart.timeScale().setVisibleLogicalRange(savedRange);
  }, [showRibbon, data]);


  // ── Trade selection: zoom + price lines ───────────────────────────────
  useEffect(() => {
    const chart  = chartRef.current;
    const series = candlesRef.current;
    if (!chart || !series || !data) return;

    for (const pl of selPriceLinesRef.current) { try { series.removePriceLine(pl); } catch {} }
    selPriceLinesRef.current = [];

    if (selIdx === null) return;
    const tr = data.trades[selIdx];
    if (!tr) return;

    const tp = editTp ?? tpPrice(tr, mgmt.target_r ?? 3);
    const entry = editEntry ?? tr.entry;
    const sl    = editSl    ?? tr.sl;

    selPriceLinesRef.current = [
      series.createPriceLine({ price: entry, color: C.ink,   lineWidth: 1, lineStyle: LineStyle.Solid,  axisLabelVisible: true, title: `Entry #${selIdx + 1}` }),
      series.createPriceLine({ price: sl,    color: C.terra, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "SL" }),
      series.createPriceLine({ price: tp,    color: C.sage,  lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: `TP ${mgmt.target_r ?? 3}R` }),
    ];

    const s   = tr.fill_idx ?? tr.signal_idx;
    const e   = tr.exit_idx ?? s + 30;
    const pad = Math.max(15, Math.round((e - s) * 0.5));
    const from = data.bars[Math.max(0, s - pad)];
    const to   = data.bars[Math.min(data.bars.length - 1, e + pad)];
    if (from && to) chart.timeScale().setVisibleRange({ from: from.t as UTCTimestamp, to: to.t as UTCTimestamp });
  }, [selIdx, data, mgmt.target_r, editEntry, editSl, editTp]);


  // ── Sync edit values when a trade is selected ─────────────────────────
  useEffect(() => {
    if (selIdx === null || !data) {
      setEditEntry(null); setEditSl(null); setEditTp(null);
      return;
    }
    const tr = data.trades[selIdx];
    if (tr) {
      setEditEntry(tr.entry);
      setEditSl(tr.sl);
      setEditTp(tpPrice(tr, mgmt.target_r ?? 3));
    }
  }, [selIdx, data]);  // eslint-disable-line react-hooks/exhaustive-deps


  // ── Replay ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!playing || !data) return;
    const id = setInterval(() => {
      setReplayIdx((cur) => {
        const max = data.bars.length - 1;
        const next = (cur == null ? 0 : cur) + 1;
        if (next >= max) { setPlaying(false); return max; }
        return next;
      });
    }, Math.round(140 / speed));
    return () => clearInterval(id);
  }, [playing, data, speed]);

  useEffect(() => {
    const chart   = chartRef.current;
    const candles = candlesRef.current;
    if (!chart || !candles || !data || data.bars.length === 0) return;

    const displayBars = data.view_bars ?? data.bars;

    if (replayIdx == null) {
      if (lastViewCutoffRef.current !== null) {
        // Was in replay — restore all bars and markers
        candles.setData(displayBars.map(b => ({ time: b.t as UTCTimestamp, open: b.o, high: b.h, low: b.l, close: b.c })));
        markersRef.current?.setMarkers(allMarkersRef.current);
        lastViewCutoffRef.current = null;
      }
      applyLiveView(chart, displayBars.length);
      return;
    }

    const stratBar = data.bars[replayIdx];
    if (!stratBar) return;

    // Map strategy bar → view bar cutoff index
    const viewCutoff = (() => {
      if (!data.view_bars) return replayIdx + 1;
      const idx = data.view_bars.findIndex(b => (b.t as number) > (stratBar.t as number));
      return idx === -1 ? data.view_bars.length : idx;
    })();

    const lastCutoff = lastViewCutoffRef.current;

    if (lastCutoff !== null && viewCutoff > lastCutoff && viewCutoff - lastCutoff <= 10) {
      // Incremental advance during playback — append only the new bars
      for (let i = lastCutoff; i < viewCutoff; i++) {
        const b = displayBars[i];
        if (b) candles.update({ time: b.t as UTCTimestamp, open: b.o, high: b.h, low: b.l, close: b.c });
      }
    } else {
      // Full reset — scrubbing backward or entering replay mode
      candles.setData(displayBars.slice(0, viewCutoff).map(b => ({
        time: b.t as UTCTimestamp, open: b.o, high: b.h, low: b.l, close: b.c,
      })));
    }
    lastViewCutoffRef.current = viewCutoff;

    // Clip markers to bars at or before the current strategy bar
    const clippedMarkers = allMarkersRef.current.filter(m => (m.time as number) <= (stratBar.t as number));
    markersRef.current?.setMarkers(clippedMarkers);

    // Center the current bar: show halfWindow bars of history + halfWindow bars of future empty space
    const halfWindow = 80;
    const fromBar = displayBars[Math.max(0, viewCutoff - halfWindow)];
    const lastBar = displayBars[viewCutoff - 1];
    if (!fromBar || !lastBar) return;
    const prevBar = displayBars[Math.max(0, viewCutoff - 2)];
    const barSpacingSec = viewCutoff >= 2
      ? (lastBar.t as number) - (prevBar.t as number)
      : 3600;
    const futureT = (lastBar.t as number) + barSpacingSec * halfWindow;
    chart.timeScale().setVisibleRange({ from: fromBar.t as UTCTimestamp, to: futureT as UTCTimestamp });
  }, [replayIdx, data]);


  // ── Replay start-line: set when entering replay, clear on reset ───────
  useEffect(() => {
    if (replayIdx !== null && replayStartIdxRef.current === null) {
      replayStartIdxRef.current = replayIdx;
      const t = data?.bars[replayIdx]?.t;
      if (t != null) startLinePrimRef.current?.setTime(t as UTCTimestamp);
    }
    if (replayIdx === null) {
      replayStartIdxRef.current = null;
      startLinePrimRef.current?.setTime(null);
    }
  }, [replayIdx, data]);


  // ── Keyboard shortcuts (Space = play/pause · → = step) ───────────────
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (e.code === "Space") {
        e.preventDefault();
        if (replayIdxRef.current == null) setReplayIdx(0);
        setPlaying((p) => !p);
      } else if (e.code === "ArrowRight") {
        e.preventDefault();
        const d = dataRef.current;
        if (!d) return;
        setPlaying(false);
        setReplayIdx((cur) => Math.min((cur ?? 0) + 1, d.bars.length - 1));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);


  // ── Pick mode: click chart to seek to that bar ────────────────────────
  useEffect(() => {
    const container = containerRef.current;
    const chart     = chartRef.current;
    if (!pickMode || !container || !chart || !data) return;
    container.style.cursor = "crosshair";
    function onClick(e: MouseEvent) {
      if (!chart || !data) return;
      const rect = container!.getBoundingClientRect();
      const time = chart.timeScale().coordinateToTime(e.clientX - rect.left) as UTCTimestamp | null;
      if (time != null) {
        const bars = data.bars;
        let nearest = 0, minDiff = Infinity;
        for (let i = 0; i < bars.length; i++) {
          const d = Math.abs((bars[i].t as number) - (time as number));
          if (d < minDiff) { minDiff = d; nearest = i; }
        }
        setReplayIdx(nearest);
        setPlaying(false);
      }
      setPickMode(false);
    }
    container.addEventListener("click", onClick);
    return () => {
      container.removeEventListener("click", onClick);
      container.style.cursor = "";
    };
  }, [pickMode, data]);


  const replayInfo = useMemo(() => {
    if (replayIdx == null || !data) return null;
    const b = data.bars[replayIdx];
    if (!b) return null;
    const entries = data.trades.filter((t) => (t.fill_idx ?? t.signal_idx) === replayIdx);
    const exits   = data.trades.filter((t) => t.exit_idx === replayIdx);
    const zones   = (data.artifacts ?? []).filter((a) => a.kind === "zone" && a.from_idx != null && a.to_idx != null && a.from_idx <= replayIdx && replayIdx <= (a.to_idx as number));
    const levels  = (data.artifacts ?? []).filter((a) => a.kind === "level" && a.at_idx === replayIdx);
    return { b, entries, exits, zones, levels };
  }, [replayIdx, data]);

  if (!open) return null;

  const wins    = data?.trades.filter((t) => t.result === "Win").length  ?? 0;
  const losses  = data?.trades.filter((t) => t.result === "Loss").length ?? 0;
  const totalR  = data?.trades.reduce((s, t) => s + t.pnl_r, 0)         ?? 0;
  const selTrade = selIdx !== null ? data?.trades[selIdx] : null;

  const POS_MODE_LABELS = ["Position: Off", "Position: Selected", "Position: All"] as const;
  const POS_MODE_COLORS = [
    "bg-cream border-border text-muted hover:bg-cream2",
    "bg-sage/15 border-sage/40 text-sage",
    "bg-amber/20 border-amber/40 text-amber-900",
  ] as const;
  const POS_DOT_COLORS = ["bg-muted", "bg-sage", "bg-amber"] as const;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-cream2 overflow-hidden">

      {/* ── Header ────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-border shrink-0 bg-cream">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="font-semibold text-sm">{symbol}</span>
          {data?.data_source?.label && (
            <span title="Data source used" className={`text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${data.data_source.provider === "mt5" ? "bg-sage/15 border-sage/40 text-sage" : "bg-amber/25 border-amber/50 text-amber-900"}`}>
              {data.data_source.provider === "mt5" ? "● " : "⚠ "}{data.data_source.label}
            </span>
          )}

          {/* Timeframe selector */}
          <div className="flex items-center gap-1 bg-cream2 rounded-lg border border-border p-0.5">
            <button
              onClick={() => setLocalTf(timeframe)} disabled={busy}
              title={localTf === timeframe ? `Strategy runs on ${timeframe}` : `Reset to strategy TF (${timeframe})`}
              className={`text-[10.5px] px-2 py-0.5 rounded-md font-medium transition-all ${localTf === timeframe ? "bg-ink text-cream shadow-sm" : "bg-amber/30 text-amber-900 hover:bg-amber/50"}`}
            >
              {timeframe}
            </button>
            <span className="w-px h-3 bg-border mx-0.5 shrink-0" />
            {TF_OPTIONS.filter(tf => tf !== timeframe).map((tf) => (
              <button key={tf} onClick={() => setLocalTf(tf)} disabled={busy}
                title={`View ${timeframe} trades on ${tf} candles`}
                className={`text-[10.5px] px-2 py-0.5 rounded-md font-medium transition-colors ${localTf === tf ? "bg-ink text-cream shadow-sm" : "text-muted hover:text-ink"}`}
              >
                {tf}
              </button>
            ))}
          </div>

          {data && (
            <>
              <span className="text-muted text-xs">·</span>
              <span className="text-xs text-muted">{(data.view_bars ?? data.bars).length} bars</span>
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

        <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
          {/* Toggle pills */}
          <button onClick={() => setShowStructures((v) => !v)}
            title="Show order-block zones, FVG gaps, swept liquidity levels"
            className={`text-[11px] px-2.5 py-1 rounded-full border transition-colors flex items-center gap-1.5 ${showStructures ? "bg-amber/25 border-amber/50 text-amber-900" : "bg-cream border-border text-muted hover:bg-cream2"}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${showStructures ? "bg-amber" : "bg-muted"}`} />
            Structures{data?.artifacts && data.artifacts.length > 0 ? ` (${data.artifacts.length})` : ""}
          </button>

          <button onClick={() => setShowIndicators((v) => !v)}
            title="Show strategy indicators (EMA, Donchian, Bollinger, VWAP…)"
            className={`text-[11px] px-2.5 py-1 rounded-full border transition-colors flex items-center gap-1.5 ${showIndicators ? "bg-sage/15 border-sage/40 text-sage" : "bg-cream border-border text-muted hover:bg-cream2"}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${showIndicators ? "bg-sage" : "bg-muted"}`} />
            Indicators{data?.indicators && data.indicators.length > 0 ? ` (${data.indicators.length})` : ""}
          </button>

          {/* 3-state position tool: Off → Selected only → All trades */}
          <button
            onClick={() => setPosMode((m) => ((m + 1) % 3) as 0 | 1 | 2)}
            title={["Off — no position boxes", "Selected trade only — click a trade to see its box", "All trades — shows boxes for every trade"][posMode]}
            className={`text-[11px] px-2.5 py-1 rounded-full border transition-colors flex items-center gap-1.5 ${POS_MODE_COLORS[posMode]}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${POS_DOT_COLORS[posMode]}`} />
            {POS_MODE_LABELS[posMode]}
          </button>

          <button onClick={() => setShowRibbon((v) => !v)}
            title="Show position ribbon at the bottom (long/short/flat)"
            className={`text-[11px] px-2.5 py-1 rounded-full border transition-colors flex items-center gap-1.5 ${showRibbon ? "bg-amber/30 border-amber/50 text-amber-900" : "bg-cream border-border text-muted hover:bg-cream2"}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${showRibbon ? "bg-amber" : "bg-muted"}`} />
            Ribbon
          </button>

          {/* Trade history toggle */}
          <button
            onClick={() => setShowTradeHistory((v) => !v)}
            title={showTradeHistory ? "Collapse trade history" : "Show trade history"}
            className={`text-[11px] px-2.5 py-1 rounded-full border transition-colors flex items-center gap-1.5 ${showTradeHistory ? "bg-ink/10 border-ink/20 text-ink" : "bg-cream border-border text-muted hover:bg-cream2"}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${showTradeHistory ? "bg-ink" : "bg-muted"}`} />
            Trades{data ? ` (${data.trades.length})` : ""}
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
            className="w-8 h-8 rounded-full hover:bg-cream2 flex items-center justify-center text-muted hover:text-ink text-xl leading-none transition-colors">
            ×
          </button>
        </div>
      </div>

      {/* ── Body ──────────────────────────────────────────────────────── */}
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
              <div className="bg-cream border border-border rounded-xl px-6 py-4 text-sm text-terra max-w-md text-center shadow-lg">{err}</div>
            </div>
          )}
          <div ref={containerRef} className="w-full h-full" />

          {/* Replay readout */}
          {replayInfo && (
            <div className="absolute top-3 right-3 z-10 bg-cream2 border border-border rounded-lg shadow-md px-3 py-2 text-[11px] max-w-[260px]">
              <div className="font-semibold text-ink mb-1">
                Bar {(replayIdx ?? 0) + 1} · {new Date((replayInfo.b.t as number) * 1000).toUTCString().slice(5, 22)}
              </div>
              <div className="font-mono text-muted mb-1">
                O {replayInfo.b.o.toFixed(2)} · H {replayInfo.b.h.toFixed(2)} · L {replayInfo.b.l.toFixed(2)} · C {replayInfo.b.c.toFixed(2)}
              </div>
              <div className="space-y-0.5">
                {replayInfo.entries.map((t, k) => (
                  <div key={`e${k}`} className="font-medium" style={{ color: t.direction === "Bull" ? C.sage : C.terra }}>
                    {t.direction === "Bull" ? "▲ Long entry" : "▼ Short entry"} @ {t.entry.toFixed(2)}
                  </div>
                ))}
                {replayInfo.exits.map((t, k) => (
                  <div key={`x${k}`} className="text-ink">✕ Exit ({t.exit_type || t.result}) · {t.pnl_r >= 0 ? "+" : ""}{t.pnl_r.toFixed(2)}R</div>
                ))}
                {replayInfo.levels.map((a, k) => (<div key={`l${k}`} className="text-amber-900">⚑ {a.label}</div>))}
                {replayInfo.zones.length > 0 && (<div className="text-muted">In {replayInfo.zones.length} active zone{replayInfo.zones.length > 1 ? "s" : ""}</div>)}
                {replayInfo.entries.length === 0 && replayInfo.exits.length === 0 && replayInfo.levels.length === 0 && (
                  <div className="text-muted italic">No trade here — waiting for a setup.</div>
                )}
              </div>
            </div>
          )}

          {/* ── Selected trade overlay: editable position tool ── */}
          {selTrade && selIdx !== null && (() => {
            const e  = editEntry ?? selTrade.entry;
            const s  = editSl    ?? selTrade.sl;
            const t  = editTp    ?? tpPrice(selTrade, mgmt.target_r ?? 3);
            const risk   = Math.abs(e - s);
            const reward = Math.abs(t - e);
            const rr     = risk > 0 ? reward / risk : 0;
            const isBull = selTrade.direction === "Bull";
            const validDir = isBull ? (t > e && e > s) : (t < e && e < s);
            return (
              <div className="absolute top-3 left-3 z-10 bg-cream2/95 border border-border rounded-xl shadow-lg px-3.5 py-3 text-[11px] w-[230px] backdrop-blur-sm">
                {/* Title row */}
                <div className="flex items-center gap-2 mb-2.5">
                  <span className="font-semibold text-[12px]" style={{ color: isBull ? C.sage : C.terra }}>
                    #{selIdx + 1} · {isBull ? "▲ Long" : "▼ Short"}
                  </span>
                  <span className="ml-auto font-mono font-semibold text-[12px]" style={{ color: tradeColor(selTrade) }}>
                    {selTrade.pnl_r >= 0 ? "+" : ""}{selTrade.pnl_r.toFixed(2)}R
                  </span>
                </div>

                {/* Editable price fields */}
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-muted w-10 shrink-0">Entry</span>
                    <input
                      type="number" step="0.01" value={e}
                      onChange={(ev) => { const v = parseFloat(ev.target.value); if (!isNaN(v)) setEditEntry(v); }}
                      className="flex-1 text-[11px] font-mono bg-cream border border-border rounded px-1.5 py-0.5 text-ink focus:outline-none focus:ring-1 focus:ring-ink/30 w-0"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-terra w-10 shrink-0">SL</span>
                    <input
                      type="number" step="0.01" value={s}
                      onChange={(ev) => { const v = parseFloat(ev.target.value); if (!isNaN(v)) setEditSl(v); }}
                      className="flex-1 text-[11px] font-mono bg-cream border border-terra/30 rounded px-1.5 py-0.5 text-terra focus:outline-none focus:ring-1 focus:ring-terra/30 w-0"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sage w-10 shrink-0">TP</span>
                    <input
                      type="number" step="0.01" value={t}
                      onChange={(ev) => { const v = parseFloat(ev.target.value); if (!isNaN(v)) setEditTp(v); }}
                      className="flex-1 text-[11px] font-mono bg-cream border border-sage/30 rounded px-1.5 py-0.5 text-sage focus:outline-none focus:ring-1 focus:ring-sage/30 w-0"
                    />
                  </div>
                </div>

                {/* Live R:R metrics */}
                <div className="mt-2.5 pt-2 border-t border-border/60 grid grid-cols-3 gap-1 text-center">
                  <div>
                    <div className="text-[9px] text-muted uppercase tracking-wide mb-0.5">Risk</div>
                    <div className="text-[11px] font-mono text-terra">{risk.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-[9px] text-muted uppercase tracking-wide mb-0.5">Reward</div>
                    <div className="text-[11px] font-mono text-sage">{reward.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-[9px] text-muted uppercase tracking-wide mb-0.5">R:R</div>
                    <div className={`text-[12px] font-mono font-bold ${!validDir ? "text-terra" : rr >= 2 ? "text-sage" : "text-amber"}`}>
                      {validDir ? `1:${rr.toFixed(1)}` : "⚠"}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 mt-2 pt-1.5 border-t border-border/40">
                  <span className="text-[9px] text-muted uppercase tracking-wide">{selTrade.exit_type || selTrade.result}</span>
                  <button
                    onClick={() => { setEditEntry(selTrade.entry); setEditSl(selTrade.sl); setEditTp(tpPrice(selTrade, mgmt.target_r ?? 3)); }}
                    className="text-[10px] text-muted hover:text-ink underline"
                  >
                    Reset
                  </button>
                  <button onClick={() => setSelIdx(null)} className="text-[10px] text-muted hover:text-ink underline ml-auto">
                    Close
                  </button>
                </div>
              </div>
            );
          })()}
        </div>

        {/* ── Trade history panel ─────────────────────────────────────── */}
        {showTradeHistory && data && data.trades.length > 0 && (
          <div className="w-64 shrink-0 border-l border-border flex flex-col bg-cream">
            <div className="px-4 py-2.5 border-b border-border shrink-0 flex items-center justify-between">
              <div>
                <div className="text-xs font-semibold text-ink">Trade history</div>
                <div className="text-[10px] text-muted mt-0.5">Click to zoom · edit position tool on the left</div>
              </div>
              <button
                onClick={() => setShowTradeHistory(false)}
                title="Collapse trade history"
                className="text-muted hover:text-ink text-lg leading-none px-1 shrink-0"
              >
                ›
              </button>
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
                    className={`w-full text-left px-4 py-2.5 border-b border-border/50 transition-all text-xs hover:bg-cream2
                      ${isSel ? "bg-cream2 border-l-[3px] border-l-sage" : "border-l-[3px] border-l-transparent"}`}
                  >
                    <div className="flex items-center justify-between mb-0.5">
                      <div className="flex items-center gap-1.5">
                        <span className="text-muted font-mono text-[10px]">#{i + 1}</span>
                        <span className="font-semibold text-[11px]" style={{ color: isBull ? C.sage : C.terra }}>
                          {isBull ? "▲" : "▼"} {tr.entry.toFixed(2)}
                        </span>
                      </div>
                      <span className="font-semibold font-mono text-[11px]" style={{ color: col }}>{pnlStr}</span>
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-muted">
                      <span>SL <span className="font-mono">{tr.sl.toFixed(2)}</span></span>
                      <span className="px-1.5 py-0.5 rounded-full text-[9px] font-medium" style={{ background: col + "22", color: col }}>
                        {tr.exit_type || tr.result}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="px-4 py-2.5 border-t border-border shrink-0 bg-cream/80">
              <div className="flex justify-between text-[10px] text-muted">
                <span>Win: <strong className="text-sage">{wins}</strong></span>
                <span>Loss: <strong className="text-terra">{losses}</strong></span>
                <span>Net: <strong style={{ color: totalR >= 0 ? C.sage : C.terra }}>{totalR >= 0 ? "+" : ""}{totalR.toFixed(1)}R</strong></span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Replay controls ────────────────────────────────────────────── */}
      {data && data.bars.length > 0 && (
        <div className="px-5 py-2 border-t border-border shrink-0 bg-cream/60 flex items-center gap-3">
          {/* Speed control */}
          <div className="flex items-center gap-0.5 bg-cream2 rounded border border-border p-0.5 shrink-0">
            {([0.5, 1, 2, 4] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSpeed(s)}
                className={`text-[10px] px-2 py-0.5 rounded font-medium transition-colors ${speed === s ? "bg-ink text-cream" : "text-muted hover:text-ink"}`}
              >
                {s === 0.5 ? "½x" : `${s}x`}
              </button>
            ))}
          </div>
          {/* Pick start point */}
          <button
            onClick={() => { setPlaying(false); setPickMode((v) => !v); }}
            title="Click a candle on the chart to jump replay to that point"
            className={`text-xs px-3 py-1 rounded-md font-medium transition-colors shrink-0 ${pickMode ? "bg-blue-500 text-white" : "bg-cream border border-border text-muted hover:text-ink"}`}>
            ✂ Pick
          </button>

          {/* Play / Pause */}
          <button
            onClick={() => { if (replayIdx == null) setReplayIdx(0); setPlaying((p) => !p); }}
            title="Space"
            className="text-xs px-3 py-1 rounded-md bg-ink text-cream font-medium hover:opacity-90 transition-opacity shrink-0">
            {playing ? "⏸ Pause" : "▶ Play"}
          </button>

          {/* Step forward one bar */}
          <button
            onClick={() => {
              if (!data) return;
              setPlaying(false);
              setReplayIdx((cur) => Math.min((cur ?? 0) + 1, data.bars.length - 1));
            }}
            title="Step forward one bar  →"
            className="text-xs px-2 py-1 rounded-md bg-cream border border-border text-muted hover:text-ink font-medium shrink-0">
            ›
          </button>
          <input
            type="range" min={0} max={data.bars.length - 1}
            value={replayIdx ?? data.bars.length - 1}
            onChange={(e) => { setPlaying(false); setReplayIdx(parseInt(e.target.value)); }}
            className="flex-1 accent-sage"
          />
          <span className="text-[10px] text-muted font-mono w-28 text-right shrink-0">
            {replayIdx == null ? "Live (all bars)" : `bar ${replayIdx + 1} / ${data.bars.length}`}
          </span>
          {replayIdx != null && (
            <button
              onClick={() => { setReplayIdx(null); setPlaying(false); }}
              className="text-xs px-2 py-1 rounded border border-border text-muted hover:text-ink hover:bg-cream shrink-0">
              Reset
            </button>
          )}
        </div>
      )}

      {/* ── Legend ─────────────────────────────────────────────────────── */}
      <div className="px-5 py-2 border-t border-border shrink-0 bg-cream/70 flex flex-wrap items-center gap-x-5 gap-y-1 text-[10px] text-muted">
        <span className="flex items-center gap-1.5"><span style={{ color: C.sage }}>▲</span> Long entry</span>
        <span className="flex items-center gap-1.5"><span style={{ color: C.terra }}>▼</span> Short entry</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-2 h-2 rounded-full" style={{ background: C.sage }} /> Win exit</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-2 h-2 rounded-full" style={{ background: C.terra }} /> Loss exit</span>
        {posMode > 0 && (
          <>
            <span className="flex items-center gap-1.5"><span className="inline-block w-5 h-3 rounded-sm" style={{ background: "rgba(107,155,122,0.30)" }} /> Profit zone</span>
            <span className="flex items-center gap-1.5"><span className="inline-block w-5 h-3 rounded-sm" style={{ background: "rgba(201,123,99,0.30)" }} /> Loss zone</span>
            <span className="flex items-center gap-1.5"><span className="inline-block w-5 border-t" style={{ borderColor: C.ink }} /> Entry</span>
          </>
        )}
        {showIndicators && data?.indicators && data.indicators.map((ind) => (
          <span key={ind.id} className="flex items-center gap-1.5">
            <span className="inline-block w-5" style={{ borderTop: `${ind.line_width}px ${ind.line_style} ${ind.color}` }} />
            {ind.label}
          </span>
        ))}
        <span className="ml-auto italic">Click trade → zoom · Scroll → zoom · Drag → pan · Space → play/pause · → → step</span>
      </div>
    </div>
  );
}
