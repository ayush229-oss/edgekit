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
  LineSeries,      // still used by strategy indicators
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


// ── Structural-zone primitive ────────────────────────────────────────────
// Draws the engine's actual decisions as shapes: filled OB / FVG rectangles
// and dashed swept-liquidity level lines. Uses lightweight-charts' series
// primitive API so shapes track pan/zoom precisely.
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
// Renders TradingView-style long / short position boxes for every trade:
//   • filled green zone  → entry ↔ TP  (profit)
//   • filled red zone    → SL ↔ entry  (loss)
//   • solid entry line, dashed SL and TP lines
//   • left edge: thin vertical at the fill bar
// Selected trade renders at full opacity; others are faded.
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
        const a     = box.sel ? 0.26 : 0.12;   // fill alpha

        // Profit zone (entry ↔ tp)
        ctx.fillStyle = `rgba(107,155,122,${a})`;
        ctx.fillRect(left, Math.min(yE, yT) * vr, w, Math.abs(yT - yE) * vr);

        // Loss zone (entry ↔ sl)
        ctx.fillStyle = `rgba(201,123,99,${a})`;
        ctx.fillRect(left, Math.min(yE, yS) * vr, w, Math.abs(yS - yE) * vr);

        const lw = (box.sel ? 1.5 : 1) * hr;

        // TP line — dashed sage
        ctx.strokeStyle = box.sel ? "rgba(107,155,122,1.0)" : "rgba(107,155,122,0.65)";
        ctx.lineWidth = lw; ctx.setLineDash([4 * hr, 3 * hr]);
        ctx.beginPath(); ctx.moveTo(left, yT * vr); ctx.lineTo(right, yT * vr); ctx.stroke();

        // SL line — dashed terra
        ctx.strokeStyle = box.sel ? "rgba(201,123,99,1.0)" : "rgba(201,123,99,0.65)";
        ctx.lineWidth = lw;
        ctx.beginPath(); ctx.moveTo(left, yS * vr); ctx.lineTo(right, yS * vr); ctx.stroke();

        // Entry line — solid ink
        ctx.strokeStyle = box.sel ? "rgba(44,62,45,1.0)" : "rgba(44,62,45,0.55)";
        ctx.lineWidth = lw; ctx.setLineDash([]);
        ctx.beginPath(); ctx.moveTo(left, yE * vr); ctx.lineTo(right, yE * vr); ctx.stroke();

        // Left-edge vertical at entry bar (direction colour)
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

  // Position-box primitive (replaces the 3 sparse line-series approach)
  const posBoxPrimRef = useRef<PositionBoxesPrimitive | null>(null);
  // Ribbon overlay series
  const ribbonRef     = useRef<ISeriesApi<"Histogram"> | null>(null);

  // Strategy indicator lines (EMA, Donchian, Bollinger, etc.) — rebuilt with the chart
  const indicatorRefs = useRef<ISeriesApi<"Line">[]>([]);

  // Structural-zone primitive (OB/FVG zones, swept levels)
  const zonesPrimRef  = useRef<ZonesPrimitive | null>(null);

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
  const [showStructures, setShowStructures] = useState(true);
  // Replay: null = live (show all); a number = playhead bar index
  const [replayIdx, setReplayIdx] = useState<number | null>(null);
  const [playing,   setPlaying]   = useState(false);

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

    // Attach the structural-zone primitive (OB/FVG/swept levels)
    try {
      const zp = new ZonesPrimitive();
      (candles as any).attachPrimitive?.(zp);
      zonesPrimRef.current = zp;
    } catch { zonesPrimRef.current = null; }

    // Attach the position-boxes primitive (trade entry/SL/TP boxes)
    try {
      const pb = new PositionBoxesPrimitive();
      (candles as any).attachPrimitive?.(pb);
      posBoxPrimRef.current = pb;
    } catch { posBoxPrimRef.current = null; }

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
      markersRef.current    = null;
      candlesRef.current    = null;
      zonesPrimRef.current  = null;
      posBoxPrimRef.current = null;
      ribbonRef.current     = null;
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


  // ── Structures: OB/FVG zones + swept-liquidity levels (the strategy trace) ──
  useEffect(() => {
    const zp = zonesPrimRef.current;
    if (!zp || !data) return;
    if (!showStructures || !data.artifacts || data.artifacts.length === 0) {
      zp.setShapes([]);
      return;
    }
    const bars = data.bars;
    const shapes: ZShape[] = [];
    for (const a of data.artifacts) {
      if (a.kind === "zone" && a.from_idx != null && a.to_idx != null
          && a.price_hi != null && a.price_lo != null) {
        const b1 = bars[a.from_idx]; const b2 = bars[a.to_idx];
        if (!b1 || !b2) continue;
        const bull = a.color_hint !== "bear";
        shapes.push({
          type: "rect",
          t1: b1.t as UTCTimestamp, t2: b2.t as UTCTimestamp,
          hi: a.price_hi, lo: a.price_lo,
          fill:   bull ? "rgba(107,155,122,0.10)" : "rgba(201,123,99,0.10)",
          stroke: bull ? "rgba(107,155,122,0.55)" : "rgba(201,123,99,0.55)",
        });
      } else if (a.kind === "level" && a.at_idx != null && a.price != null) {
        const b1 = bars[a.at_idx];
        const b2 = bars[Math.min(bars.length - 1, a.at_idx + 15)];
        if (!b1 || !b2) continue;
        const bear = a.color_hint === "bear";
        shapes.push({
          type: "hline",
          t1: b1.t as UTCTimestamp, t2: b2.t as UTCTimestamp,
          price: a.price,
          color: bear ? "rgba(201,123,99,0.9)" : "rgba(107,155,122,0.9)",
        });
      }
    }
    zp.setShapes(shapes);
  }, [data, showStructures]);


  // ── Toggle 1: Position boxes (replaces 3 sparse line series) ────────
  // Draws a TradingView-style long/short position tool for every trade:
  //   green filled zone = profit side (entry→TP), red = loss side (SL→entry)
  //   selected trade renders at full opacity; all others are faded.
  useEffect(() => {
    const pb = posBoxPrimRef.current;
    if (!pb || !data) return;

    if (!showZones) { pb.setBoxes([]); return; }

    const tR = mgmt.target_r ?? 3;
    const boxes: TBox[] = [];
    data.trades.forEach((tr, i) => {
      const fi = tr.fill_idx ?? tr.signal_idx;
      const ei = tr.exit_idx ?? Math.min(data.bars.length - 1, fi + 60);
      const b1 = data.bars[fi];
      const b2 = data.bars[ei];
      if (!b1 || !b2) return;
      boxes.push({
        t1:     b1.t as UTCTimestamp,
        t2:     b2.t as UTCTimestamp,
        entry:  tr.entry,
        sl:     tr.sl,
        tp:     tpPrice(tr, tR),
        isBull: tr.direction === "Bull",
        sel:    i === selIdx,
      });
    });
    pb.setBoxes(boxes);
  }, [showZones, data, mgmt.target_r, selIdx]);


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


  // ── Replay: advance the playhead while playing ───────────────────────
  useEffect(() => {
    if (!playing || !data) return;
    const id = setInterval(() => {
      setReplayIdx((cur) => {
        const max = data.bars.length - 1;
        const next = (cur == null ? 0 : cur) + 1;
        if (next >= max) { setPlaying(false); return max; }
        return next;
      });
    }, 140);
    return () => clearInterval(id);
  }, [playing, data]);

  // ── Replay: scroll the chart so the playhead sits at the right edge ──
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !data || data.bars.length === 0) return;
    if (replayIdx == null) { chart.timeScale().fitContent(); return; }
    const from = data.bars[Math.max(0, replayIdx - 120)];
    const to   = data.bars[replayIdx];
    if (from && to) {
      chart.timeScale().setVisibleRange({ from: from.t as UTCTimestamp, to: to.t as UTCTimestamp });
    }
  }, [replayIdx, data]);

  // What's happening at the playhead bar — the "why did/didn't it trade here" readout
  const replayInfo = useMemo(() => {
    if (replayIdx == null || !data) return null;
    const b = data.bars[replayIdx];
    if (!b) return null;
    const entries = data.trades.filter((t) => (t.fill_idx ?? t.signal_idx) === replayIdx);
    const exits   = data.trades.filter((t) => t.exit_idx === replayIdx);
    const zones   = (data.artifacts ?? []).filter(
      (a) => a.kind === "zone" && a.from_idx != null && a.to_idx != null
             && a.from_idx <= replayIdx && replayIdx <= (a.to_idx as number));
    const levels  = (data.artifacts ?? []).filter((a) => a.kind === "level" && a.at_idx === replayIdx);
    return { b, entries, exits, zones, levels };
  }, [replayIdx, data]);

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
              onClick={() => setShowStructures((v) => !v)}
              title="Show the structures the strategy uses — order-block zones, FVG gaps, swept liquidity levels"
              className={`text-[11px] px-2.5 py-1 rounded-full border transition-colors flex items-center gap-1.5
                ${showStructures ? "bg-amber/25 border-amber/50 text-amber-900" : "bg-cream border-border text-muted hover:bg-cream2"}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${showStructures ? "bg-amber" : "bg-muted"}`} />
              Structures{data?.artifacts && data.artifacts.length > 0 ? ` (${data.artifacts.length})` : ""}
            </button>
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
              title="Show TradingView-style position boxes for every trade — green profit zone, red loss zone, entry/SL/TP lines"
              className={`text-[11px] px-2.5 py-1 rounded-full border transition-colors flex items-center gap-1.5
                ${showZones ? "bg-sage/15 border-sage/40 text-sage" : "bg-cream border-border text-muted hover:bg-cream2"}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${showZones ? "bg-sage" : "bg-muted"}`} />
              Position tool
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

            {/* Replay readout — what's happening at the playhead bar */}
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
                  {replayInfo.levels.map((a, k) => (
                    <div key={`l${k}`} className="text-amber-900">⚑ {a.label}</div>
                  ))}
                  {replayInfo.zones.length > 0 && (
                    <div className="text-muted">In {replayInfo.zones.length} active zone{replayInfo.zones.length > 1 ? "s" : ""}</div>
                  )}
                  {replayInfo.entries.length === 0 && replayInfo.exits.length === 0 && replayInfo.levels.length === 0 && (
                    <div className="text-muted italic">No trade here — waiting for a setup.</div>
                  )}
                </div>
              </div>
            )}

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

        {/* ── Replay controls ──────────────────────────────────────────── */}
        {data && data.bars.length > 0 && (
          <div className="px-5 py-2 border-t border-border shrink-0 bg-cream/40 flex items-center gap-3">
            <button
              onClick={() => { if (replayIdx == null) setReplayIdx(0); setPlaying((p) => !p); }}
              className="text-xs px-3 py-1 rounded-md bg-ink text-cream font-medium hover:opacity-90 transition-opacity shrink-0">
              {playing ? "⏸ Pause" : "▶ Play"}
            </button>
            <input
              type="range" min={0} max={data.bars.length - 1}
              value={replayIdx ?? data.bars.length - 1}
              onChange={(e) => { setPlaying(false); setReplayIdx(parseInt(e.target.value)); }}
              className="flex-1 accent-sage"
              title="Scrub through the strategy bar-by-bar"
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
                <span className="inline-block w-5 h-3 rounded-sm" style={{ background: "rgba(107,155,122,0.30)" }} /> Profit zone (entry→TP)
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block w-5 h-3 rounded-sm" style={{ background: "rgba(201,123,99,0.30)" }} /> Loss zone (SL→entry)
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block w-5 border-t" style={{ borderColor: C.ink }} /> Entry
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
