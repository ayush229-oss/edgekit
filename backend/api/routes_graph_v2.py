"""
v2 graph endpoints (parallel to /graph/* — v1 stays live until the
frontend is migrated).

  GET  /graph/v2/nodes              — full v2 node library (typed ports)
  GET  /graph/v2/templates          — list starter graphs
  GET  /graph/v2/templates/{id}     — fetch one full template graph
  POST /graph/v2/complexity         — score a graph (green/amber/red)
  POST /graph/v2/backtest           — run backtest against a v2 graph
"""
from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional, Tuple
from fastapi import APIRouter, HTTPException, Depends, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.engine.builder_v2 import (
    NODE_LIBRARY, GraphV2Strategy, list_templates, get_template,
    validate_graph, complexity_score, generate_pinescript,
)
from backend.engine.core import (
    load_mt5, simulate, compute_metrics, infer_pip_from_df, validate_ohlcv,
    data_source_of,
)
from backend.engine.core.metrics import compute_challenge_result
from backend.api import store
from backend.api.cache import backtest_cache
from backend.api.schemas import BacktestResponse, BacktestMetrics, ChallengeParams, ChallengeResult, ChallengeDayResult
from backend.db import get_db


router = APIRouter(prefix="/graph/v2", tags=["graph_v2"])


# ─── Indicator series extractor ───────────────────────────────────────────
# After detect() runs, ctx.cache contains every indicator's full series keyed
# by a deterministic name. We auto-pick the price-overlay ones (values in the
# same magnitude as the close price) and pretty-label them per node type.
#
# Each entry: cache_key_template → (port_label, color, line_style, line_width)
# Templates substitute the node's params via .format(**params).
_PRICE_OVERLAY_INDICATORS = {
    "indicator.ema":        [("ema_{period}",          "EMA {period}",      "#3B82F6", "solid",  2)],
    "indicator.sma":        [("sma_{period}",          "SMA {period}",      "#8B5CF6", "solid",  2)],
    "indicator.donchian":   [
        ("donch_u_{period}", "Donchian Upper {period}", "#0EA5E9", "dashed", 1),
        ("donch_l_{period}", "Donchian Lower {period}", "#0EA5E9", "dashed", 1),
    ],
    "indicator.bollinger":  [
        ("bb_{period}_{mult}_u", "Bollinger Upper", "#A855F7", "dashed", 1),
        ("bb_{period}_{mult}_m", "Bollinger Mid",   "#A855F7", "solid",  1),
        ("bb_{period}_{mult}_l", "Bollinger Lower", "#A855F7", "dashed", 1),
    ],
    "indicator.vwap":       [("vwap",                  "VWAP",              "#14B8A6", "solid",  2)],
    "indicator.supertrend": [("st_{period}_{mult}_v",  "SuperTrend",        "#F59E0B", "solid",  2)],
    "indicator.swing_high": [("swing_h_{period}",      "Swing High {period}", "#0EA5E9", "dotted", 1)],
    "indicator.swing_low":  [("swing_l_{period}",      "Swing Low {period}",  "#F97316", "dotted", 1)],
    "indicator.ichimoku":   [
        ("ichi_{tenkan_period}_{kijun_period}_{senkou_b_period}_t", "Tenkan",         "#DC2626", "solid", 1),
        ("ichi_{tenkan_period}_{kijun_period}_{senkou_b_period}_k", "Kijun",          "#3B82F6", "solid", 1),
        ("ichi_{tenkan_period}_{kijun_period}_{senkou_b_period}_a", "Senkou Span A",  "#16A34A", "solid", 1),
        ("ichi_{tenkan_period}_{kijun_period}_{senkou_b_period}_b", "Senkou Span B",  "#DC2626", "solid", 1),
    ],
    # NOTE: indicator.order_block is intentionally NOT here — it now renders as a
    # shaded zone via the structural trace (see artifacts), not as three lines.
}

# Oscillators — these don't share the candlestick's price scale (RSI is 0-100,
# MACD is unbounded, etc.), so the frontend draws each one in its own pane
# below the chart instead of overlaying it on price. Each series tuple is
# (cache_key_template, label_template, color, line_style, line_width, series_type).
_OSCILLATOR_INDICATORS: Dict[str, Dict[str, Any]] = {
    "indicator.rsi": {
        "range": [0, 100], "ref_lines": [30, 70],
        "series": [("rsi_{period}", "RSI {period}", "#8B5CF6", "solid", 2, "line")],
    },
    "indicator.macd": {
        "range": None, "ref_lines": [0],
        "series": [
            ("macd_{fast}_{slow}_{signal}_m", "MACD",      "#3B82F6", "solid", 2, "line"),
            ("macd_{fast}_{slow}_{signal}_s", "Signal",    "#F97316", "solid", 1, "line"),
            ("macd_{fast}_{slow}_{signal}_h", "Histogram", "#8A8071", "solid", 1, "histogram"),
        ],
    },
    "indicator.adx": {
        "range": [0, 100], "ref_lines": [25],
        "series": [("adx_{period}", "ADX {period}", "#EAB308", "solid", 2, "line")],
    },
    "indicator.stochastic": {
        "range": [0, 100], "ref_lines": [20, 80],
        "series": [
            ("stoch_{k_period}_{d_period}_k", "%K", "#3B82F6", "solid", 2, "line"),
            ("stoch_{k_period}_{d_period}_d", "%D", "#F97316", "solid", 1, "line"),
        ],
    },
    "indicator.cci": {
        "range": None, "ref_lines": [-100, 100],
        "series": [("cci_{period}", "CCI {period}", "#14B8A6", "solid", 2, "line")],
    },
    "indicator.williams_r": {
        "range": [-100, 0], "ref_lines": [-20, -80],
        "series": [("wpr_{period}", "Williams %R {period}", "#EC4899", "solid", 2, "line")],
    },
    "indicator.roc": {
        "range": None, "ref_lines": [0],
        "series": [("roc_{period}", "ROC {period}", "#DC2626", "solid", 2, "line")],
    },
}

def _extract_indicators(strategy, df) -> List[Dict[str, Any]]:
    """Walk every indicator.* node in the graph; emit its cached series
    for price-overlay-style indicators. Skips nodes whose cache keys are
    missing (e.g. a different version of an indicator we don't recognise)."""
    import math
    import numpy as np

    ctx = getattr(strategy, "ctx", None)
    if ctx is None:
        return []

    out: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()

    # When the same indicator type appears multiple times (e.g. fast EMA + slow EMA),
    # rotate through a distinct color palette so each line is visually unique.
    _COLOR_ROTATION = ["#3B82F6", "#F97316", "#A855F7", "#14B8A6", "#EAB308", "#EC4899"]
    type_seen_count: Dict[str, int] = {}

    for nid, node in strategy.nodes.items():
        ntype = node["type"]
        if not ntype.startswith("indicator."):
            continue
        templates = _PRICE_OVERLAY_INDICATORS.get(ntype)
        if not templates:
            continue
        params = node.get("params", {}) or {}

        # Override the default color if this is the 2nd+ instance of this type
        # AND the indicator only emits one series (otherwise we'd recolor every
        # series of e.g. a 2nd Donchian, which is fine — they all get the rotated color)
        type_seen_count[ntype] = type_seen_count.get(ntype, 0) + 1
        rotation_idx = (type_seen_count[ntype] - 1) % len(_COLOR_ROTATION)
        rotated_color = _COLOR_ROTATION[rotation_idx] if type_seen_count[ntype] > 1 else None

        for key_tmpl, label_tmpl, color, style, width in templates:
            try:
                key   = key_tmpl.format(**params)
                label = label_tmpl.format(**params)
            except (KeyError, IndexError):
                continue
            if key in seen_keys:
                continue
            arr = ctx.cache.get(key)
            if arr is None:
                continue
            # Convert to plain list of floats / None (NaN → None for JSON safety)
            try:
                vals: List[Any] = []
                for v in np.asarray(arr):
                    fv = float(v)
                    if math.isnan(fv) or math.isinf(fv):
                        vals.append(None)
                    else:
                        vals.append(fv)
            except Exception:
                continue
            seen_keys.add(key)
            out.append({
                "id":         f"{nid}__{key}",
                "node_id":    nid,
                "node_type":  ntype,
                "label":      label,
                "color":      rotated_color or color,
                "line_style": style,    # "solid" | "dashed" | "dotted"
                "line_width": width,
                "values":     vals,
                "kind":       "overlay",   # shares the candlestick's price scale
            })

    # ── Oscillators — RSI/MACD/ADX/Stochastic/CCI/Williams%R/ROC don't share
    # the price scale, so each gets tagged with its own pane_id (grouped by
    # originating node — MACD's 3 series stay together in one pane) plus a
    # value range / reference-line hint the frontend uses to draw the pane.
    for nid, node in strategy.nodes.items():
        ntype = node["type"]
        osc = _OSCILLATOR_INDICATORS.get(ntype)
        if not osc:
            continue
        params = node.get("params", {}) or {}
        for key_tmpl, label_tmpl, color, style, width, series_type in osc["series"]:
            try:
                key   = key_tmpl.format(**params)
                label = label_tmpl.format(**params)
            except (KeyError, IndexError):
                continue
            if key in seen_keys:
                continue
            arr = ctx.cache.get(key)
            if arr is None:
                continue
            try:
                vals: List[Any] = []
                for v in np.asarray(arr):
                    fv = float(v)
                    if math.isnan(fv) or math.isinf(fv):
                        vals.append(None)
                    else:
                        vals.append(fv)
            except Exception:
                continue
            seen_keys.add(key)
            out.append({
                "id":         f"{nid}__{key}",
                "node_id":    nid,
                "node_type":  ntype,
                "label":      label,
                "color":      color,
                "line_style": style,
                "line_width": width,
                "values":     vals,
                "kind":       "oscillator",
                "series_type": series_type,   # "line" | "histogram"
                "pane_id":    nid,             # series from the same node share a pane
                "range":      osc["range"],    # [lo, hi] or null (unbounded)
                "ref_lines":  osc["ref_lines"],
            })
    return out


@router.get("/nodes")
def list_nodes() -> List[Dict[str, Any]]:
    """Every v2 node, with its typed inputs / outputs."""
    return [spec.to_dict() for spec in NODE_LIBRARY.values()]


# A static fallback for when MT5 isn't connected — the most common instruments
# across asset classes. Free-text input on the frontend lets users override
# with any broker-specific symbol (e.g. "GOLD", "US30.cash", "BTCUSDm").
_COMMON_SYMBOLS = [
    # Metals
    {"symbol": "XAUUSD", "description": "Gold vs USD",         "category": "Metals"},
    {"symbol": "XAGUSD", "description": "Silver vs USD",       "category": "Metals"},
    {"symbol": "XPTUSD", "description": "Platinum vs USD",     "category": "Metals"},
    # Forex majors
    {"symbol": "EURUSD", "description": "Euro / US Dollar",        "category": "Forex Majors"},
    {"symbol": "GBPUSD", "description": "British Pound / USD",     "category": "Forex Majors"},
    {"symbol": "USDJPY", "description": "USD / Japanese Yen",      "category": "Forex Majors"},
    {"symbol": "USDCHF", "description": "USD / Swiss Franc",       "category": "Forex Majors"},
    {"symbol": "AUDUSD", "description": "Australian Dollar / USD", "category": "Forex Majors"},
    {"symbol": "USDCAD", "description": "USD / Canadian Dollar",   "category": "Forex Majors"},
    {"symbol": "NZDUSD", "description": "NZ Dollar / USD",         "category": "Forex Majors"},
    # Forex crosses
    {"symbol": "EURJPY", "description": "Euro / Yen",          "category": "Forex Crosses"},
    {"symbol": "GBPJPY", "description": "Pound / Yen",         "category": "Forex Crosses"},
    {"symbol": "EURGBP", "description": "Euro / Pound",        "category": "Forex Crosses"},
    {"symbol": "AUDJPY", "description": "Aussie / Yen",        "category": "Forex Crosses"},
    # Indices
    {"symbol": "US30",   "description": "Dow Jones 30",        "category": "Indices"},
    {"symbol": "US500",  "description": "S&P 500",             "category": "Indices"},
    {"symbol": "NAS100", "description": "Nasdaq 100",          "category": "Indices"},
    {"symbol": "GER40",  "description": "DAX 40",              "category": "Indices"},
    {"symbol": "UK100",  "description": "FTSE 100",            "category": "Indices"},
    {"symbol": "JPN225", "description": "Nikkei 225",          "category": "Indices"},
    # Energies
    {"symbol": "USOIL",  "description": "US Crude Oil",        "category": "Energies"},
    {"symbol": "UKOIL",  "description": "Brent Crude",         "category": "Energies"},
    {"symbol": "NGAS",   "description": "Natural Gas",         "category": "Energies"},
    # Crypto
    {"symbol": "BTCUSD", "description": "Bitcoin / USD",       "category": "Crypto"},
    {"symbol": "ETHUSD", "description": "Ethereum / USD",      "category": "Crypto"},
]


@router.get("/symbols")
def list_symbols() -> Dict[str, Any]:
    """
    Return symbols available for backtesting. Tries MT5 first (returns the
    actual symbols the user's broker offers); falls back to a curated common
    set if MT5 isn't initialized.
    """
    try:
        import MetaTrader5 as mt5    # type: ignore
        if not mt5.initialize():
            raise RuntimeError("MT5 not initialized")
        syms = mt5.symbols_get() or []
        out  = []
        for s in syms:
            try:
                out.append({
                    "symbol":      s.name,
                    "description": (s.description or s.name).strip()[:60],
                    "category":    (s.path.split("\\")[0] if s.path else "Other"),
                })
            except Exception:
                continue
        if out:
            # Sort by category then symbol for cleaner UX
            out.sort(key=lambda x: (x["category"], x["symbol"]))
            return {"source": "mt5", "symbols": out}
    except Exception:
        pass
    return {"source": "static", "symbols": _COMMON_SYMBOLS}


@router.get("/templates")
def list_starter_templates() -> List[Dict[str, Any]]:
    return list_templates()


@router.get("/templates/{template_id}")
def get_starter_template(template_id: str) -> Dict[str, Any]:
    try:
        return get_template(template_id)
    except KeyError:
        raise HTTPException(404, f"Unknown template: {template_id}")


class GraphInput(BaseModel):
    graph: Dict[str, Any]


@router.post("/complexity")
def score_graph(req: GraphInput) -> Dict[str, Any]:
    return complexity_score(req.graph)


class PineExportRequest(BaseModel):
    graph:            Dict[str, Any]
    target_r:         Optional[float] = 3.0
    target_close_pct: float           = 0.5
    trail_mode:       Literal["none", "candle", "atr", "pips", "swing"] = "candle"
    trail_start:      Literal["immediate", "after_target"] = "after_target"
    trail_params:     Dict[str, Any]  = Field(default_factory=lambda: {"buf_pips": 1})


class SimExecutionFields(BaseModel):
    """Every field that changes what simulate() actually produces, other than
    the graph/data/trade-management fields each endpoint already declares
    itself. Shared by every endpoint that runs a real simulation so Chart
    Preview and the real backtest CANNOT structurally diverge again — a past
    bug had Chart Preview silently ignoring the user's Settings-level spread/
    commission/slippage, session-hours filter, and max-concurrent limit,
    so the "what-if" preview could show trades the real backtest wouldn't."""
    spread_pips:      float = 0.0
    commission:       float = 0.0
    slippage_pips:    float = 0.0
    swap_long_pips:   float = 0.0
    swap_short_pips:  float = 0.0
    max_concurrent:   int   = 1
    order_expiry:     Optional[int] = None
    session_hours:    Optional[Tuple[int, int]] = None
    risk_pct:         float = 0.01
    initial_equity:   float = 100.0
    max_risk_usd:     float = 600.0


def _effective_sim_kwargs(req: "SimExecutionFields", strategy: "GraphV2Strategy") -> Dict[str, Any]:
    """Resolve the actual simulate() kwargs for a run. An `execution.costs`
    node on the canvas (written into the run context during detect()) takes
    precedence over the request-level cost fields; `x or y` means a node
    value of 0 defers to the request. Everything else is request-level only."""
    cctx = getattr(strategy, "ctx", None)
    return {
        "spread_pips":     float(getattr(cctx, "spread_pips",   0.0) or 0.0) or req.spread_pips,
        "commission":      float(getattr(cctx, "commission",    0.0) or 0.0) or req.commission,
        "slippage_pips":   float(getattr(cctx, "slippage_pips", 0.0) or 0.0) or req.slippage_pips,
        "swap_long_pips":  req.swap_long_pips,
        "swap_short_pips": req.swap_short_pips,
        "max_concurrent":  req.max_concurrent,
        "order_expiry":    req.order_expiry,
        "session_hours":   req.session_hours,
        "risk_pct":        req.risk_pct,
        "initial_equity":  req.initial_equity,
        "max_risk_usd":    req.max_risk_usd,
    }


class ChartPreviewRequest(SimExecutionFields):
    graph:            Dict[str, Any]
    symbol:           str  = "XAUUSD"
    timeframe:        str  = "M15"
    n_bars:           int  = 500
    target_r:         Optional[float] = 3.0
    target_close_pct: float           = 0.5
    trail_mode:       Literal["none", "candle", "atr", "pips", "swing"] = "candle"
    trail_start:      Literal["immediate", "after_target"] = "after_target"
    trail_params:     Dict[str, Any]  = Field(default_factory=lambda: {"buf_pips": 1})
    # Optional view TF — strategy always runs on `timeframe`; if view_tf differs,
    # bars for view_tf are also loaded and returned as `view_bars` for the chart.
    view_tf:          Optional[str]   = None


@router.post("/chart-preview")
def chart_preview(req: ChartPreviewRequest) -> Dict[str, Any]:
    """
    Return bars + trade markers for visualizing the strategy on the chart.
    Frontend renders the candles + entry/exit markers + SL lines.

    All failures return JSON with a useful `detail` so the frontend can show
    the actual cause (a bare 500 strips CORS headers and the browser
    misreports it as a CORS error).
    """
    import traceback

    # ── Validate graph ────────────────────────────────────────────────────
    try:
        graph = validate_graph(req.graph)
    except ValueError as e:
        raise HTTPException(400, f"Graph validation failed: {e}")
    except Exception as e:
        raise HTTPException(400, f"Graph validation failed: {e}")

    # ── Fetch bars from MT5 ──────────────────────────────────────────────
    try:
        df = load_mt5(req.symbol, req.timeframe, req.n_bars)
    except Exception as e:
        raise HTTPException(400, f"MT5 fetch failed for {req.symbol} {req.timeframe}: {e}")

    if df is None or len(df) == 0:
        raise HTTPException(400, f"No bars returned for {req.symbol} {req.timeframe}. "
                                  f"Either the symbol is wrong or MT5 has no history here.")

    # ── Detect setups + simulate trades ──────────────────────────────────
    try:
        pip      = infer_pip_from_df(df, req.symbol)
        strategy = GraphV2Strategy(graph)
        setups   = strategy.detect(df, {"pip": pip})
    except Exception as e:
        # Most common: graph wiring is incomplete or a node throws on this data
        raise HTTPException(422, f"Strategy ran into a problem: {type(e).__name__}: {e}\n\n"
                                  f"Check that every node has its required inputs wired.")

    try:
        tdf = simulate(
            df, setups,
            target_r         = req.target_r,
            target_close_pct = req.target_close_pct,
            trail_mode       = req.trail_mode,
            trail_start      = req.trail_start,
            trail_params     = req.trail_params,
            pip              = pip,
            **_effective_sim_kwargs(req, strategy),
        )
    except Exception as e:
        raise HTTPException(422, f"Trade simulation failed: {type(e).__name__}: {e}")

    # ── Pack response ────────────────────────────────────────────────────
    try:
        # Convert time column to unix seconds. load_mt5 returns
        # datetime64[s]; CSV uploads may give strings or other precisions.
        # Force seconds precision so .astype("int64") gives unix seconds
        # directly (avoids the ns/s precision footgun in pandas 2.x).
        import pandas as pd
        time_col = df["time"]
        if not pd.api.types.is_datetime64_any_dtype(time_col):
            time_col = pd.to_datetime(time_col, errors="coerce")
        # Normalize to seconds precision regardless of source unit
        times = time_col.astype("datetime64[s]").astype("int64").to_numpy()

        # Deduplicate while preserving order — lightweight-charts requires
        # strictly ascending unique timestamps. Bump duplicates by 1 second.
        seen_max = -1
        bars = []
        for i in range(len(df)):
            raw_t = times[i]
            # Guard against NaT → min-int64; skip the bar if time is bad
            if raw_t <= 0:
                continue
            t = int(raw_t)
            if t <= seen_max:
                t = seen_max + 1
            seen_max = t
            bars.append({
                "t": t,
                "o": float(df["O"].iloc[i]), "h": float(df["H"].iloc[i]),
                "l": float(df["L"].iloc[i]), "c": float(df["C"].iloc[i]),
            })

        # Helper — pandas stores missing ints as NaN; need to guard before int()
        import math
        def _opt_int(v):
            if v is None:                                       return None
            if isinstance(v, float) and math.isnan(v):          return None
            try:                                                return int(v)
            except (TypeError, ValueError):                     return None
        def _opt_float(v, default=0.0):
            if v is None:                                       return default
            if isinstance(v, float) and math.isnan(v):          return default
            try:                                                return float(v)
            except (TypeError, ValueError):                     return default

        trades = []
        if not tdf.empty:
            for _, t in tdf.iterrows():
                trades.append({
                    "signal_idx": _opt_int(t.get("signal_idx", 0)) or 0,
                    "fill_idx":   _opt_int(t.get("fill_idx")),
                    "exit_idx":   _opt_int(t.get("exit_idx")),
                    "direction":  str(t.get("direction", "Bull")),
                    "entry":      _opt_float(t.get("entry")),
                    "sl":         _opt_float(t.get("sl")),
                    "result":     str(t.get("result", "Unresolved")),
                    "exit_type":  str(t.get("exit_type", "")),
                    "pnl_r":      _opt_float(t.get("pnl_r")),
                })

        # ── Indicator series for chart overlay ──────────────────────────
        # Each indicator returns full bar-aligned values; the frontend draws
        # them as line series on top of the candlestick chart.
        try:
            indicators = _extract_indicators(strategy, df)
        except Exception:
            indicators = []

        # Structural artifacts (OB zones, FVG gaps, swept levels) the engine
        # actually decided — drawn as shapes, not guessed from param keys.
        artifacts = list(getattr(getattr(strategy, "ctx", None), "trace", []) or [])

        # ── Optional view_tf bars (different display TF, same strategy result) ──
        # If view_tf differs from timeframe, load bars for the requested view TF
        # and return them as `view_bars`. The frontend uses view_bars for the
        # candlestick backdrop while keeping the strategy trades/markers as-is
        # (all positions/markers are timestamp-based, so they auto-align).
        view_bars = None
        view_tf = req.view_tf
        if view_tf and view_tf != req.timeframe:
            try:
                _TF_MINS = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
                strat_mins = _TF_MINS.get(req.timeframe, 15)
                vw_mins    = _TF_MINS.get(view_tf, 5)
                view_n     = min(20000, max(100, int(req.n_bars * strat_mins / vw_mins)))
                vdf = load_mt5(req.symbol, view_tf, view_n)
                if vdf is not None and len(vdf) > 0:
                    vtimes = vdf["time"].astype("datetime64[s]").astype("int64").to_numpy()
                    vseen_max = -1
                    view_bars = []
                    for i in range(len(vdf)):
                        raw_t = int(vtimes[i])
                        if raw_t <= 0:
                            continue
                        t = raw_t
                        if t <= vseen_max:
                            t = vseen_max + 1
                        vseen_max = t
                        view_bars.append({
                            "t": t,
                            "o": float(vdf["O"].iloc[i]), "h": float(vdf["H"].iloc[i]),
                            "l": float(vdf["L"].iloc[i]), "c": float(vdf["C"].iloc[i]),
                        })
            except Exception:
                view_bars = None   # fall back to strategy bars on the frontend

        resp: Dict[str, Any] = {
            "symbol":    req.symbol,
            "timeframe": req.timeframe,
            "pip":       pip,
            "bars":      bars,
            "trades":    trades,
            "n_setups":  len(setups),
            "indicators": indicators,
            "artifacts": artifacts,
            "data_source": data_source_of(df),
        }
        if view_bars is not None:
            resp["view_bars"] = view_bars
            resp["view_tf"]   = view_tf
        return resp
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Packing response failed: {type(e).__name__}: {e}")


# ─── AI: plain-English → V2 graph ─────────────────────────────────────────
class FromTextRequest(BaseModel):
    description: str
    symbol:      str = "XAUUSD"
    timeframe:   str = "M15"
    # Optional reference image (chart screenshot / hand-drawn setup) as a data URL
    # — "data:image/png;base64,…". Used only by vision-capable providers
    # (Anthropic, Gemini, OpenAI); ignored by text-only ones (Groq, Mistral).
    image:       Optional[str] = None


_AI_SYSTEM_TEMPLATE = """You are Edgekit's strategy-graph generator. The user describes a trading strategy in plain English; you respond with a JSON V2Graph that the visual builder can load directly.

# V2Graph schema
{{
  "name":  string,
  "nodes": [{{"id": string, "type": string, "params": {{...}}}}],
  "edges": [{{"from": id, "to": id, "from_port": string, "to_port": string}}]
}}

# Available nodes (typed ports — only matching types can connect)
{catalog}

# Lane flow (left → right)
universe → indicator → alpha → filter → sizing → risk → exit → execution

# Hard rules
1. Every wire's `from_port` type MUST equal its `to_port` type.
2. The graph MUST end in exactly one execution.* node (or one per long/short chain combined via execution.combine_or — if that node exists).
3. Use sensible default params from the catalog unless the user is explicit.
4. For long+short strategies, build two parallel chains (own alpha, sizing, risk, exit, execution) and combine.
5. Limit-order executions need a `price` wire — wire OB.entry (or another price source) into `execution.limit_at_price.price`.
6. Risk nodes that need ATR or a level must have those wires — never leave a required input dangling.
7. Use unique ids like "atr1", "obL", "sweepL". Keep them short.
8. Position is optional — omit it, the frontend auto-lays out.

# Output
Return ONLY a JSON object matching the V2Graph schema. No prose, no markdown fences.
"""


@router.post("/from-text")
def from_text(
    req: FromTextRequest,
    request:       Request,
    x_gemini_key:  Optional[str] = Header(None, alias="X-Gemini-Key"),   # legacy
    x_ai_key:      Optional[str] = Header(None, alias="X-AI-Key"),
    x_ai_provider: Optional[str] = Header(None, alias="X-AI-Provider"),
) -> Dict[str, Any]:
    """
    Convert a plain-English strategy description into a V2 graph using the
    user's chosen AI provider (Gemini, Anthropic, OpenAI, Groq, Mistral).

    Key priority: X-AI-Key header → legacy X-Gemini-Key → server env var.
    """
    # Cap server-paid usage (no user key) per identity/day.
    if not ((x_ai_key or "").strip() or (x_gemini_key or "").strip()):
        from backend.api.limits import enforce_ai_quota
        enforce_ai_quota(request.client.host if request.client else "anon")
    try:
        return _from_text_impl(req, x_gemini_key, x_ai_key, x_ai_provider)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"AI generation crashed: {type(e).__name__}: {str(e)[:300]}")


# ─── Node-from-text: generate a single custom indicator node ─────────────────

_NODE_FROM_TEXT_SYSTEM = """You are an expert quantitative trading developer building nodes for a visual strategy builder.

The user describes a piece of strategy logic. You produce a UserNodeDef JSON for the most appropriate lane.

LANES:
  indicator  — computes a value/series from OHLCV. Outputs: number or series.
  alpha      — generates Bull/Bear signals. Formula returns "Bull", "Bear", or None.
  filter     — passes or blocks an incoming insight. Formula returns True (pass) or False (block).
  sizing     — returns a risk fraction (e.g. 0.01 = 1% of equity). Formula returns float 0–1.
  risk       — returns a stop-loss distance in pips. Formula returns positive float.
  exit       — returns a target R multiple. Formula returns float (e.g. 3.0).

OUTPUT SCHEMA:
{
  "label":        string,          // short display name
  "description":  string,          // one sentence
  "lane":         "indicator"|"alpha"|"filter"|"sizing"|"risk"|"exit",
  "outputs": [                     // INDICATOR ONLY — omit for other lanes
    {"name": string, "type": "series"|"number"}
  ],
  "extra_inputs": [                // additional wired number inputs (optional, any lane)
    {"name": string, "type": "number"}
  ],
  "params_spec": [
    {
      "key": string,               // Python identifier
      "label": string,
      "type": "int"|"float",
      "default": number,
      "min": number,               // optional
      "max": number                // optional
    }
  ],
  "formulas": {
    // indicator: one key per output port name → expression returning scalar or array
    // all others: single key "main" → expression for the lane (see rules below)
  }
}

FORMULA RULES — all lanes:
- Variables: open, high, low, close, volume (np.ndarray), i (bar index), pip (float)
- Modules: np (numpy), pd (pandas)
- Builtins: abs, min, max, len, sum, round, int, float, bool, list, range, zip, enumerate
- Params: each key available directly by name (e.g. `period`, not `params['period']`)
- extra_inputs: each name available directly (e.g. `ema_value`, `rsi_value`)
- Single expression only — no assignments, no multi-line, no imports

FORMULA RULES — by lane:
  indicator/series: returns np.ndarray of same length as close (full history, pre-computed once)
  indicator/number: returns scalar — close[-1], high[-1] style
  alpha/main:   returns "Bull", "Bear", or None
    example: '"Bull" if close[-1] > pd.Series(close).rolling(period).mean().values[-1] else ("Bear" if close[-1] < pd.Series(close).rolling(period).mean().values[-1] else None)'
  filter/main:  returns bool — True = pass insight, False = block
    available extra: direction ("Bull"/"Bear"), confidence (float)
    example: 'direction == "Bull" and close[-1] > pd.Series(close).rolling(20).mean().values[-1]'
  sizing/main:  returns float 0–1 (risk fraction)
    available extra: direction, confidence
    example: 'min(0.02, confidence * 0.025)'
  risk/main:    returns float (SL distance in pips, positive)
    available extra: entry_px, direction
    example: 'pd.Series(high - low).rolling(period).mean().values[-1] / pip * 1.5'
  exit/main:    returns float (target R multiple, e.g. 3.0)
    available extra: entry_px, direction
    example: '3.0 if pd.Series(high - low).rolling(14).mean().values[-1] < pd.Series(high - low).rolling(50).mean().values[-1] else 2.0'

Return ONLY the JSON object. No prose, no markdown fences.
"""


class NodeFromTextRequest(BaseModel):
    description: str


@router.post("/node-from-text")
def node_from_text(
    req:           NodeFromTextRequest,
    request:       Request,
    x_gemini_key:  Optional[str] = Header(None, alias="X-Gemini-Key"),
    x_ai_key:      Optional[str] = Header(None, alias="X-AI-Key"),
    x_ai_provider: Optional[str] = Header(None, alias="X-AI-Provider"),
) -> Dict[str, Any]:
    """
    Generate a single user-defined indicator node from a plain-English description.
    Returns a UserNodeDef JSON (label, outputs, params_spec, formulas).
    """
    import os, json as _json

    provider = (x_ai_provider or _DEFAULT_PROVIDER).strip().lower()
    api_key  = (x_ai_key or "").strip()
    if not api_key and x_gemini_key:
        api_key  = x_gemini_key.strip()
        provider = "gemini"
    if not api_key:
        provider = _DEFAULT_PROVIDER if not x_ai_provider else provider
        api_key  = os.environ.get(_PROVIDER_ENV.get(provider, ""), "").strip()
    if not api_key:
        raise HTTPException(503, f"AI generation needs an API key. Add yours under Resources → AI Model.")

    user_prompt = f"Create an indicator node for: {req.description}"

    def _call(extra: str = "") -> str:
        prompt = user_prompt + extra
        try:
            if provider == "gemini":
                return _call_gemini(api_key, _NODE_FROM_TEXT_SYSTEM, prompt)
            elif provider == "anthropic":
                return _call_anthropic(api_key, _NODE_FROM_TEXT_SYSTEM, prompt)
            elif provider in ("openai", "groq", "mistral"):
                return _call_openai_compat(provider, api_key, _NODE_FROM_TEXT_SYSTEM, prompt)
            else:
                raise HTTPException(400, f"Unknown provider '{provider}'.")
        except HTTPException:
            raise
        except Exception as e:
            raise _normalize_api_error(provider, str(e))

    VALID_LANES = {"indicator", "alpha", "filter", "sizing", "risk", "exit"}

    def _validate_node_def(d: Dict) -> None:
        if not isinstance(d.get("label"), str) or not d["label"].strip():
            raise ValueError("Missing label.")
        lane = d.get("lane", "indicator")
        if lane not in VALID_LANES:
            raise ValueError(f"Invalid lane '{lane}'. Must be one of {sorted(VALID_LANES)}.")
        if not isinstance(d.get("formulas"), dict) or not d["formulas"]:
            raise ValueError("formulas must be a non-empty object.")
        if lane == "indicator":
            outputs = d.get("outputs", [])
            if not outputs:
                raise ValueError("indicator nodes must have at least one output.")
            for o in outputs:
                if o.get("type") not in ("series", "number"):
                    raise ValueError(f"Output type must be 'series' or 'number', got: {o.get('type')}")
                if not d["formulas"].get(o["name"]):
                    raise ValueError(f"Missing formula for output '{o['name']}'.")
        else:
            # Non-indicator: must have a "main" formula
            if not d["formulas"].get("main"):
                raise ValueError(f"{lane} node must have a 'main' formula.")

    try:
        raw = _call()
    except HTTPException:
        raise

    try:
        node_def = _json.loads(_coerce_json_text(raw))
        _validate_node_def(node_def)
    except Exception as e:
        try:
            raw2     = _call(f"\n\nYour previous attempt failed validation: {e}\nFix it and return the corrected JSON.")
            node_def = _json.loads(_coerce_json_text(raw2))
            _validate_node_def(node_def)
        except Exception as e2:
            raise HTTPException(422, f"AI produced an invalid node definition: {e2}")

    node_def.setdefault("description", req.description[:140])
    node_def.setdefault("lane", "indicator")
    node_def.setdefault("params_spec", [])
    node_def.setdefault("extra_inputs", [])
    node_def.setdefault("outputs", [] if node_def.get("lane") != "indicator" else node_def.get("outputs", []))
    return node_def


# ── Per-provider env var fallbacks ──────────────────────────────────────────
_PROVIDER_ENV: Dict[str, str] = {
    "gemini":    "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai":    "OPENAI_API_KEY",
    "groq":      "GROQ_API_KEY",
    "mistral":   "MISTRAL_API_KEY",
}

# When a user hasn't supplied their own key, Edgekit uses Claude on the server's
# dime (server-paid). The ANTHROPIC_API_KEY env var must be set on the VPS.
_DEFAULT_PROVIDER = "anthropic"

# Default model per provider
_PROVIDER_MODEL: Dict[str, str] = {
    "gemini":    "gemini-2.5-flash",
    "anthropic": "claude-sonnet-4-5",
    "openai":    "gpt-4o-mini",
    "groq":      "llama-3.3-70b-versatile",
    "mistral":   "mistral-small-latest",
}

# OpenAI-compatible base URLs for non-OpenAI providers
_OPENAI_COMPAT_BASE: Dict[str, str] = {
    "groq":    "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
}


def _build_catalog_and_prompts(req: "FromTextRequest") -> tuple:
    import json as _json
    catalog = []
    for spec in NODE_LIBRARY.values():
        d = spec.to_dict()
        catalog.append({
            "type":    d["type"],
            "lane":    d["lane"],
            "label":   d["label"],
            "desc":    d["description"],
            "inputs":  [{"name": p["name"], "type": p["type"]} for p in d["inputs"]],
            "outputs": [{"name": p["name"], "type": p["type"]} for p in d["outputs"]],
            "params":  [{"key": p["key"], "type": p["type"], "default": p["default"]}
                        for p in d["params"]],
        })
    system_prompt = _AI_SYSTEM_TEMPLATE.format(catalog=_json.dumps(catalog, separators=(",", ":")))
    user_prompt   = (
        f"Symbol: {req.symbol}\nTimeframe: {req.timeframe}\n\n"
        f"Strategy description:\n{req.description}\n\n"
        f"Generate the V2 graph JSON."
    )
    return system_prompt, user_prompt


def _parse_image(image: Optional[str]) -> Optional[Tuple[str, str]]:
    """Parse a data-URL (or raw base64) reference image into (media_type, base64).

    Returns None when no image is supplied. Raises 413 if it's too large.
    """
    if not image:
        return None
    s = image.strip()
    media_type, data = "image/png", s
    if s.startswith("data:"):
        try:
            header, data = s.split(",", 1)
            media_type = header[5:].split(";")[0] or "image/png"
        except ValueError:
            return None
    # base64 length ≈ 4/3 of byte size; ~7 MB base64 ≈ 5 MB image.
    if len(data) > 7_000_000:
        raise HTTPException(413, "Reference image is too large (max ~5 MB).")
    if media_type not in ("image/png", "image/jpeg", "image/webp", "image/gif"):
        media_type = "image/png"
    return (media_type, data)


def _coerce_json_text(s: str) -> str:
    """Pull the JSON object out of an LLM reply.

    Models often wrap JSON in ```json … ``` fences (or add a line of prose)
    despite being told not to — that makes json.loads() fail on char 0. Strip
    fences, then fall back to slicing between the outermost braces.
    """
    s = (s or "").strip()
    if s.startswith("```"):
        nl = s.find("\n")
        s = s[nl + 1:] if nl != -1 else s[3:]
        end = s.rfind("```")
        if end != -1:
            s = s[:end]
        s = s.strip()
    if not s.startswith("{"):
        i, j = s.find("{"), s.rfind("}")
        if i != -1 and j != -1 and j > i:
            s = s[i:j + 1]
    return s.strip()


def _call_gemini(api_key: str, system_prompt: str, user_prompt: str,
                 image: Optional[Tuple[str, str]] = None) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise HTTPException(503, "google-genai SDK not installed on server.")

    response_schema = {
        "type": "object",
        "properties": {
            "name":  {"type": "string"},
            "nodes": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"}, "type": {"type": "string"}, "params": {"type": "object"},
                },
                "required": ["id", "type", "params"],
            }},
            "edges": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "from": {"type": "string"}, "to": {"type": "string"},
                    "from_port": {"type": "string"}, "to_port": {"type": "string"},
                },
                "required": ["from", "to", "from_port", "to_port"],
            }},
        },
        "required": ["name", "nodes", "edges"],
    }
    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        raise HTTPException(400, f"Could not init Gemini client: {e}")

    if image is not None:
        import base64 as _b64
        media_type, data = image
        contents: Any = [
            types.Part.from_bytes(data=_b64.b64decode(data), mime_type=media_type),
            user_prompt,
        ]
    else:
        contents = user_prompt
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=0.3,
        ),
    )
    return resp.text or ""


def _call_anthropic(api_key: str, system_prompt: str, user_prompt: str,
                    image: Optional[Tuple[str, str]] = None) -> str:
    try:
        import anthropic
    except ImportError:
        raise HTTPException(503, "anthropic SDK not installed. Run: pip install anthropic")

    if image is not None:
        media_type, data = image
        content: Any = [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
            {"type": "text", "text": user_prompt},
        ]
    else:
        content = user_prompt

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        temperature=0.3,
        system=system_prompt + "\n\nIMPORTANT: Output ONLY raw JSON — no prose, no markdown fences.",
        messages=[{"role": "user", "content": content}],
    )
    return msg.content[0].text if msg.content else ""


def _call_openai_compat(provider: str, api_key: str, system_prompt: str, user_prompt: str,
                        image: Optional[Tuple[str, str]] = None) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise HTTPException(503, "openai SDK not installed. Run: pip install openai")

    kwargs: Dict[str, Any] = {"api_key": api_key}
    if provider in _OPENAI_COMPAT_BASE:
        kwargs["base_url"] = _OPENAI_COMPAT_BASE[provider]

    # Only OpenAI's GPT-4o models are vision-capable here; Groq/Mistral are text-only.
    if image is not None and provider == "openai":
        media_type, data = image
        user_content: Any = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{data}"}},
        ]
    else:
        user_content = user_prompt

    client = OpenAI(**kwargs)
    resp = client.chat.completions.create(
        model=_PROVIDER_MODEL[provider],
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt + "\n\nOutput ONLY raw JSON."},
            {"role": "user",   "content": user_content},
        ],
    )
    return resp.choices[0].message.content or ""


def _normalize_api_error(provider: str, msg: str) -> HTTPException:
    low = msg.lower()
    if any(x in low for x in ("invalid api key", "api_key_invalid", "unauthorized", "401", "incorrect api key")):
        return HTTPException(400, f"The {provider} API key is invalid. Update it on the Resources page.")
    if any(x in low for x in ("quota", "rate", "429", "resource_exhausted", "too many requests")):
        return HTTPException(429, f"{provider} rate limit hit. Wait a minute and try again.")
    if any(x in low for x in ("permission", "403", "permission_denied")):
        return HTTPException(403, f"The {provider} API key lacks permission for this model.")
    return HTTPException(502, f"AI provider error ({provider}): {msg[:300]}")


def _from_text_impl(
    req: "FromTextRequest",
    x_gemini_key:  Optional[str],
    x_ai_key:      Optional[str],
    x_ai_provider: Optional[str],
) -> Dict[str, Any]:
    import os, json as _json

    # Resolve provider + key. User-supplied key wins (they pay); otherwise fall
    # back to the server's Claude key (server-paid default).
    user_supplied = bool((x_ai_key or "").strip() or (x_gemini_key or "").strip())
    provider = (x_ai_provider or _DEFAULT_PROVIDER).strip().lower()
    api_key  = (x_ai_key or "").strip()

    # Backward compat: X-Gemini-Key header
    if not api_key and x_gemini_key:
        api_key  = x_gemini_key.strip()
        provider = "gemini"

    # Env var fallback (server key)
    if not api_key:
        provider = _DEFAULT_PROVIDER if not x_ai_provider else provider
        api_key = os.environ.get(_PROVIDER_ENV.get(provider, ""), "").strip()

    if not api_key:
        raise HTTPException(
            503,
            f"AI generation needs an API key for {provider}. "
            "Add yours under Resources → AI Model."
        )

    system_prompt, user_prompt = _build_catalog_and_prompts(req)

    img = _parse_image(req.image)
    if img is not None:
        if provider in ("groq", "mistral"):
            img = None   # text-only models — silently ignore the reference image
        else:
            user_prompt += (
                "\n\nA reference image is attached (e.g. a chart screenshot or a "
                "hand-drawn setup). Read it carefully — annotations, levels, "
                "patterns, indicators shown — and incorporate what it depicts into "
                "the strategy graph."
            )

    def _call(extra: str = "") -> str:
        prompt = user_prompt + extra
        try:
            if provider == "gemini":
                return _call_gemini(api_key, system_prompt, prompt, img)
            elif provider == "anthropic":
                return _call_anthropic(api_key, system_prompt, prompt, img)
            elif provider in ("openai", "groq", "mistral"):
                return _call_openai_compat(provider, api_key, system_prompt, prompt, img)
            else:
                raise HTTPException(400, f"Unknown provider '{provider}'. Use: gemini, anthropic, openai, groq, mistral.")
        except HTTPException:
            raise
        except Exception as e:
            raise _normalize_api_error(provider, str(e))

    try:
        raw = _call()
    except HTTPException:
        raise

    try:
        graph = _json.loads(_coerce_json_text(raw))
        validate_graph(graph)
    except Exception as e:
        try:
            raw2  = _call(f"\n\nYour previous attempt failed graph validation: {e}\nRebuild the graph correctly.")
            graph = _json.loads(_coerce_json_text(raw2))
            validate_graph(graph)
        except Exception as e2:
            raise HTTPException(422, f"AI produced an invalid graph: {e2}")

    # Auto-layout — lay nodes out left-to-right by lane index
    lane_order = ["universe", "indicator", "alpha", "filter", "sizing", "risk", "exit", "execution"]
    lane_of = {spec.type: spec.lane for spec in NODE_LIBRARY.values()}
    lane_buckets: Dict[str, List[str]] = {l: [] for l in lane_order}
    for n in graph.get("nodes", []):
        ln = lane_of.get(n.get("type", ""), "alpha")
        lane_buckets.setdefault(ln, []).append(n["id"])
    pos: Dict[str, Dict[str, int]] = {}
    for col, lane in enumerate(lane_order):
        for row, nid in enumerate(lane_buckets.get(lane, [])):
            pos[nid] = {"x": 80 + col * 240, "y": 80 + row * 180}
    for n in graph.get("nodes", []):
        if n["id"] in pos:
            n["position"] = pos[n["id"]]

    return graph


# ─── AI Chat: conversational strategy builder ─────────────────────────────
class ChatMessage(BaseModel):
    role:    str   # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    messages:  List[ChatMessage]
    symbol:    str = "XAUUSD"
    timeframe: str = "M15"
    # When the user opens the chat from an existing strategy on the canvas, the
    # current graph (and a short summary of its last backtest) are passed in so
    # the assistant can EDIT it rather than start from scratch.
    current_graph:  Optional[Dict[str, Any]] = None
    result_summary: Optional[str] = None
    # Optional reference image (chart screenshot) for THIS turn, as a data URL.
    # Used by vision-capable providers (Anthropic default, Gemini, OpenAI).
    image:          Optional[str] = None

_CHAT_SYSTEM = """You are Edgekit's friendly trading strategy assistant. Your job is to help non-technical traders design a backtestable strategy through conversation — without them needing to know code, Python, or indicators.

You have two modes:

MODE 1 — CLARIFY (when you don't yet have enough information):
Ask ONE clear, simple question per turn. Focus on:
  - What market condition triggers a trade? (e.g. "price breaks above a high", "RSI is low", "candle pattern")
  - Long, short, or both directions?
  - Where does the stop loss go? (e.g. "below the last swing low", "fixed distance")
  - Any filters? (e.g. "only trade London hours", "only when trend is strong")
Keep questions short. Use plain trader language, not technical jargon.
You MUST use MODE 1 (do not guess) when the user's description is missing ANY of:
  (a) the entry trigger, (b) direction (long/short/both), (c) the stop-loss idea.
Everything else (periods, pips, R targets, trail settings) may be defaulted in MODE 2 —
but every defaulted value MUST be declared in "user_specified" bookkeeping below.

MODE 2 — BUILD (when you have enough to build a solid graph):
Output ONLY this JSON, nothing else:
{{"type":"graph","graph":{graph_schema},"user_specified":[{{"node_id":string,"param":string}}],"open_questions":[string]}}

"user_specified" lists EVERY node param whose value came directly from the user's words
(e.g. they said "RSI 30" → the RSI threshold param is user-specified; they never mentioned
the RSI period → period is NOT listed). Be strict: when in doubt, leave it out.
"open_questions" (0-3 short strings) are things you assumed that most change the strategy's
behaviour and the user may want to reconsider (e.g. "I assumed a 15-pip fixed stop — do you
prefer a stop below the swing low?"). Empty array if nothing important was assumed.

where graph matches the V2Graph schema with available nodes below.

V2Graph schema:
{{"name":string,"nodes":[{{"id":string,"type":string,"params":{{...}}}}],"edges":[{{"from":string,"to":string,"from_port":string,"to_port":string}}]}}

Available nodes:
{catalog}

Lane flow: universe → indicator → alpha → filter → sizing → risk → exit → execution

Rules:
1. Only use node types from the catalog above.
2. Every edge from_port type must equal to_port type.
3. Every required input must be wired.
4. End in exactly one execution node.
5. Use sensible default params.

MODE 1 output format (when asking questions):
{{"type":"message","content":"your question here"}}

CRITICAL: Output ONLY valid JSON matching one of the two formats above. No markdown. No prose outside the JSON."""


_NODE_CHAT_SYSTEM = """You are Edgekit's node design assistant. Help traders create a single custom node through conversation.

A node is ONE building block (not a full strategy). Lanes:
  indicator — computes a value or series from price data (e.g. custom moving average)
  alpha     — generates Bull/Bear signals (e.g. "go long when X crosses Y")
  filter    — passes or blocks an incoming signal (e.g. "only during London hours")
  sizing    — returns a risk fraction (e.g. "risk 1% scaled by volatility")
  risk      — returns a stop-loss distance in pips
  exit      — returns a target R multiple

You have two modes:

MODE 1 — CLARIFY (need more details):
Ask ONE clear, focused question per turn. Typical questions:
  - Is this meant to output a value (indicator) or generate signals (alpha)?
  - What parameters should be adjustable? (period, threshold, etc.)
  - What is the exact formula or condition?
Keep questions short and plain — no jargon.

MODE 2 — BUILD (you have enough to define the node):
Output ONLY this JSON, nothing else:
{"type":"node_def","def":{...}}

Node def schema:
{
  "label": string,
  "description": string (one sentence),
  "lane": "indicator"|"alpha"|"filter"|"sizing"|"risk"|"exit",
  "outputs": [{"name":string,"type":"series"|"number"}],  // indicator ONLY
  "extra_inputs": [],
  "params_spec": [{"key":string,"label":string,"type":"int"|"float","default":number,"min":number,"max":number}],
  "formulas": {
    // indicator: one key per output name → numpy/pandas expression returning scalar or array
    // all others: single key "main" → expression for the lane
  }
}

Formula rules:
- Variables: open, high, low, close, volume (np.ndarray), i (bar index), pip (float)
- Modules: np (numpy), pd (pandas)
- Params available by name (e.g. period)
- Single expression only — no assignments, no imports

MODE 1 format: {"type":"message","content":"your question here"}
CRITICAL: Output ONLY valid JSON. No markdown fences. No prose outside the JSON."""


class NodeChatRequest(BaseModel):
    messages: List[Dict[str, str]]


@router.post("/node-chat")
def node_chat(
    req:           NodeChatRequest,
    request:       Request,
    x_gemini_key:  Optional[str] = Header(None, alias="X-Gemini-Key"),
    x_ai_key:      Optional[str] = Header(None, alias="X-AI-Key"),
    x_ai_provider: Optional[str] = Header(None, alias="X-AI-Provider"),
    x_ai_model:    Optional[str] = Header(None, alias="X-AI-Model"),
) -> Dict[str, Any]:
    """
    Multi-turn node design assistant.
    Returns {"type":"message","content":"..."} for clarifying questions
    or {"type":"node_def","def":{...}} when ready to build.
    """
    import os, json as _json

    user_supplied = bool((x_ai_key or "").strip() or (x_gemini_key or "").strip())
    provider = (x_ai_provider or _DEFAULT_PROVIDER).strip().lower()
    api_key  = (x_ai_key or "").strip()
    if not api_key and x_gemini_key:
        api_key = x_gemini_key.strip(); provider = "gemini"
    if not api_key:
        if not x_ai_provider: provider = _DEFAULT_PROVIDER
        api_key = os.environ.get(_PROVIDER_ENV.get(provider, ""), "").strip()
    if not api_key:
        raise HTTPException(503, "AI key required. Add yours under Resources → AI Model.")
    if not user_supplied:
        from backend.api.limits import enforce_ai_quota
        enforce_ai_quota(request.client.host if request.client else "anon")

    history = [{"role": m["role"], "content": m["content"]} for m in req.messages]
    model   = (x_ai_model or "").strip() or None

    try:
        raw = _call_chat(provider, api_key, _NODE_CHAT_SYSTEM, history, model=model)
    except HTTPException:
        raise
    except Exception as e:
        raise _normalize_api_error(provider, str(e))

    result = _parse_model_json(raw)
    if result is None:
        return {"type": "message", "content": raw.strip() or "Tell me more about what this node should do."}

    if result.get("type") == "node_def":
        def_data = result.get("def")
        if not isinstance(def_data, dict):
            return {"type": "message", "content": "I had trouble generating the node. Could you describe it differently?"}
        try:
            _validate_node_def(def_data)
            return {"type": "node_def", "def": def_data}
        except Exception as e:
            # One repair attempt
            fix_hist = list(history) + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"The node_def failed validation: {e}. Fix it and return corrected JSON."},
            ]
            try:
                raw2 = _call_chat(provider, api_key, _NODE_CHAT_SYSTEM, fix_hist, model=model)
                r2   = _parse_model_json(raw2)
                if r2 and r2.get("type") == "node_def":
                    d2 = r2.get("def", {})
                    _validate_node_def(d2)
                    return {"type": "node_def", "def": d2}
            except Exception:
                pass
            return {"type": "message", "content": "I ran into a formula issue. Let me ask a bit more to get this right."}

    return {"type": "message", "content": result.get("content", raw.strip())}


@router.post("/chat")
def graph_chat(
    req: ChatRequest,
    request:       Request,
    x_gemini_key:  Optional[str] = Header(None, alias="X-Gemini-Key"),
    x_ai_key:      Optional[str] = Header(None, alias="X-AI-Key"),
    x_ai_provider: Optional[str] = Header(None, alias="X-AI-Provider"),
    x_ai_model:    Optional[str] = Header(None, alias="X-AI-Model"),
) -> Dict[str, Any]:
    """
    Multi-turn strategy design assistant for non-technical users.
    Returns {type: "message", content: "..."} when asking clarifying questions,
    or {type: "graph", graph: {...}} when ready to build.
    """
    import os, json as _json

    # User-supplied key wins (they pay). Otherwise default to the server's Claude.
    user_supplied = bool((x_ai_key or "").strip() or (x_gemini_key or "").strip())
    provider = (x_ai_provider or _DEFAULT_PROVIDER).strip().lower()
    api_key  = (x_ai_key or "").strip()
    if not api_key and x_gemini_key:
        api_key  = x_gemini_key.strip()
        provider = "gemini"
    if not api_key:
        if not x_ai_provider:
            provider = _DEFAULT_PROVIDER
        api_key = os.environ.get(_PROVIDER_ENV.get(provider, ""), "").strip()
    if not api_key:
        raise HTTPException(503, "AI key required. Add yours under Resources → AI Model.")

    # Server-paid usage (no user key) is capped per identity/day to bound spend.
    if not user_supplied:
        from backend.api.limits import enforce_ai_quota
        ident = request.client.host if request.client else "anon"
        enforce_ai_quota(ident)

    import json as _json
    catalog = []
    for spec in NODE_LIBRARY.values():
        d = spec.to_dict()
        catalog.append({
            "type":    d["type"],
            "lane":    d["lane"],
            "label":   d["label"],
            "inputs":  [{"name": p["name"], "type": p["type"]} for p in d["inputs"]],
            "outputs": [{"name": p["name"], "type": p["type"]} for p in d["outputs"]],
            "params":  [{"key": p["key"], "type": p["type"], "default": p["default"]}
                        for p in d["params"]],
        })

    graph_schema = '{"name":string,"nodes":[{"id":string,"type":string,"params":{}}],"edges":[{"from":string,"to":string,"from_port":string,"to_port":string}]}'
    system_prompt = _CHAT_SYSTEM.format(
        catalog=_json.dumps(catalog, separators=(",", ":")),
        graph_schema=graph_schema,
    )

    # EDIT MODE: the user opened the chat from an existing strategy. Give the
    # assistant the current graph + last result so it modifies that strategy
    # instead of starting over.
    if isinstance(req.current_graph, dict) and req.current_graph.get("nodes"):
        edit_ctx = (
            "\n\n--- EDIT MODE ---\n"
            "The user already has this strategy on their canvas. When they ask for "
            "changes, modify THIS graph and return the FULL updated graph (every node "
            "and edge, not just the change) in the graph format. Keep node ids stable "
            "where possible. Only ask a clarifying question if the request is ambiguous.\n"
            f"CURRENT_GRAPH:\n{_json.dumps(req.current_graph, separators=(',', ':'))}"
        )
        if req.result_summary:
            edit_ctx += f"\n\nLATEST BACKTEST RESULT: {req.result_summary.strip()}"
        system_prompt = system_prompt + edit_ctx

    # Convert messages to format each provider needs
    history = [{"role": m.role, "content": m.content} for m in req.messages]

    # Add context about symbol/timeframe
    if history and history[0]["role"] == "user":
        history = list(history)  # copy
        history[0] = {
            "role": "user",
            "content": f"[Symbol: {req.symbol}, Timeframe: {req.timeframe}]\n\n{history[0]['content']}",
        }

    model = (x_ai_model or "").strip() or None

    # Reference image (this turn only). Vision providers see it; text-only ignore.
    img = _parse_image(req.image)
    if img is not None and provider in ("groq", "mistral"):
        img = None
    if img is not None and history:
        for i in range(len(history) - 1, -1, -1):
            if history[i]["role"] == "user":
                history[i] = {**history[i], "content": history[i]["content"] +
                              "\n\n[A reference chart image is attached — read it "
                              "(levels, patterns, indicators) and use it to design "
                              "the strategy.]"}
                break

    def _build_from_raw(raw_text: str):
        """Classify a model reply.

        Returns one of:
          ("graph",   (graph_dict, user_specified, open_questions))
          ("message", text)        — a clarifying question / plain reply
          ("invalid", error_str)   — claimed a graph but it failed validation
        """
        result = _parse_model_json(raw_text)
        if result is None:
            txt = raw_text.strip()
            return ("message", txt or "Tell me more about your strategy idea.")
        if result.get("type") == "graph":
            graph = result.get("graph")
            if not isinstance(graph, dict):
                return ("invalid", "graph field missing")
            try:
                validate_graph(graph)
            except Exception as e:
                return ("invalid", str(e))
            _layout_graph(graph)
            uspec = result.get("user_specified")
            if not isinstance(uspec, list):
                uspec = []
            oq = result.get("open_questions")
            if not isinstance(oq, list):
                oq = []
            oq = [str(q) for q in oq if isinstance(q, str) and q.strip()][:3]
            return ("graph", (graph, uspec, oq))
        if result.get("type") == "message":
            return ("message", result.get("content", ""))
        return ("message", "Tell me more about your strategy idea — what market condition should trigger a trade?")

    def _ask(hist, image=None):
        try:
            return _call_chat(provider, api_key, system_prompt, hist, model=model, image=image)
        except HTTPException:
            raise
        except Exception as e:
            raise _normalize_api_error(provider, str(e))

    raw = _ask(history, image=img)   # image only on the first turn
    kind, payload = _build_from_raw(raw)

    # Self-repair: a type mismatch / unwired port is a structural error the user
    # can't fix. Hand the model its own broken JSON plus the exact validation
    # error and let it correct the graph. Up to 2 automatic attempts.
    repair_history = list(history)
    attempts = 0
    while kind == "invalid" and attempts < 2:
        attempts += 1
        repair_history = repair_history + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": (
                f"That graph failed validation:\n{payload}\n\n"
                "Fix it. Hard rules: (1) every edge must connect two ports of the "
                "SAME type — check each port's type in the catalog; (2) every node "
                "input port must be wired; (3) include at least one execution node. "
                "If two ports have incompatible types, insert the correct "
                "intermediate node to bridge them rather than wiring them directly. "
                "Output ONLY the corrected JSON in the same "
                '{"type":"graph","graph":{...}} format — no prose.'
            )},
        ]
        raw = _ask(repair_history)
        kind, payload = _build_from_raw(raw)

    if kind == "graph":
        graph, uspec, open_questions = payload
        return {
            "type":           "graph",
            "graph":          graph,
            "decisions":      _graph_decisions(graph, user_specified=uspec),
            "open_questions": open_questions,
        }
    if kind == "message":
        return {"type": "message", "content": payload}
    # Still invalid after repair attempts — be honest instead of looping.
    return {"type": "message", "content": (
        "I'm having trouble wiring this into a valid strategy graph. Try describing "
        "it a little more simply — the exact entry trigger, the exit, and how much "
        "to risk per trade — or pick a stronger model from the Model menu, and I'll "
        "try again."
    )}


class ExplainErrorRequest(BaseModel):
    # The raw error / setup message shown to the user.
    error:     str
    # Optional context so the AI can give graph-specific advice.
    graph:     Optional[Dict[str, Any]] = None
    symbol:    Optional[str] = None
    timeframe: Optional[str] = None


_EXPLAIN_ERROR_SYSTEM = """You are Edgekit's troubleshooting assistant. A non-technical trader just hit an error or a setup/validation message while building or backtesting a strategy. Translate it into plain English and tell them exactly how to fix it.

Edgekit is a no-code strategy builder: users wire "nodes" (indicators, signals, filters, sizing, risk, exits, execution) on a canvas, then run a backtest on historical price data. Common causes of errors: a node input port left unwired, two ports of incompatible types connected, no execution/entry node, too few bars or a date range with no data, a missing symbol/timeframe, or a custom node referencing unknown types.

Respond with ONLY a JSON object, no prose outside it, in this exact shape:
{"explanation": "<one or two short sentences, plain language, no jargon>", "suggestions": ["<short actionable step>", "<short actionable step>", ...]}

Rules:
- 2 to 4 suggestions, each a single concrete action the trader can take right now on the canvas or in the settings.
- Be specific to the actual error text — reference the node, port, field, or value named in it when possible.
- No code. No markdown. Keep each suggestion under ~140 characters."""


@router.post("/explain-error")
def explain_error(
    req: ExplainErrorRequest,
    request:       Request,
    x_gemini_key:  Optional[str] = Header(None, alias="X-Gemini-Key"),
    x_ai_key:      Optional[str] = Header(None, alias="X-AI-Key"),
    x_ai_provider: Optional[str] = Header(None, alias="X-AI-Provider"),
    x_ai_model:    Optional[str] = Header(None, alias="X-AI-Model"),
) -> Dict[str, Any]:
    """Turn a raw backtest/setup error into a plain-language explanation plus a
    few AI-generated fix suggestions. Used by the builder's centered error
    dialog. Returns {explanation: str, suggestions: [str, ...]}."""
    import os, json as _json

    # Same key resolution as /chat: user-supplied key wins, else server-paid Claude.
    user_supplied = bool((x_ai_key or "").strip() or (x_gemini_key or "").strip())
    provider = (x_ai_provider or _DEFAULT_PROVIDER).strip().lower()
    api_key  = (x_ai_key or "").strip()
    if not api_key and x_gemini_key:
        api_key  = x_gemini_key.strip()
        provider = "gemini"
    if not api_key:
        if not x_ai_provider:
            provider = _DEFAULT_PROVIDER
        api_key = os.environ.get(_PROVIDER_ENV.get(provider, ""), "").strip()
    if not api_key:
        raise HTTPException(503, "AI suggestions need a key. Add one under Resources → AI Model.")

    if not user_supplied:
        from backend.api.limits import enforce_ai_quota
        ident = request.client.host if request.client else "anon"
        enforce_ai_quota(ident)

    ctx = f"[Symbol: {req.symbol or '—'}, Timeframe: {req.timeframe or '—'}]\n"
    if isinstance(req.graph, dict) and req.graph.get("nodes"):
        # A trimmed node/edge summary is enough for the model to reason about wiring.
        nodes = [{"id": n.get("id"), "type": n.get("type")} for n in req.graph.get("nodes", [])]
        edges = req.graph.get("edges", [])
        ctx += f"CURRENT_STRATEGY: nodes={_json.dumps(nodes, separators=(',', ':'))} edges={_json.dumps(edges, separators=(',', ':'))}\n"
    user_msg = f"{ctx}\nERROR MESSAGE:\n{req.error.strip()}"

    model = (x_ai_model or "").strip() or None
    try:
        raw = _call_chat(provider, api_key, _EXPLAIN_ERROR_SYSTEM,
                         [{"role": "user", "content": user_msg}], model=model)
    except HTTPException:
        raise
    except Exception as e:
        raise _normalize_api_error(provider, str(e))

    parsed = _parse_model_json(raw)
    if isinstance(parsed, dict) and isinstance(parsed.get("suggestions"), list):
        suggestions = [str(s).strip() for s in parsed["suggestions"] if str(s).strip()][:4]
        explanation = str(parsed.get("explanation") or "").strip()
        return {"explanation": explanation, "suggestions": suggestions}
    # Model didn't return clean JSON — surface its prose as the explanation.
    return {"explanation": (raw or "").strip(), "suggestions": []}


def _parse_model_json(raw_text: str) -> Optional[Dict[str, Any]]:
    """Parse a model reply that should be JSON, tolerating common wrappers.

    Models (especially Claude) often wrap JSON in ```json ... ``` fences or add
    stray prose. Try a plain parse first, then strip code fences, then fall back
    to the outermost {...} slice. Returns the parsed object, or None if no JSON
    object can be recovered.
    """
    import json as _json, re as _re
    if not raw_text:
        return None
    text = raw_text.strip()

    def _try(s: str) -> Optional[Dict[str, Any]]:
        try:
            obj = _json.loads(s)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

    obj = _try(text)
    if obj is not None:
        return obj

    # Strip a leading/trailing markdown code fence (```json ... ``` or ``` ... ```).
    fenced = _re.match(r"^```[a-zA-Z]*\s*\n?(.*?)\n?```$", text, _re.DOTALL)
    if fenced:
        obj = _try(fenced.group(1).strip())
        if obj is not None:
            return obj

    # Last resort: grab from the first '{' to the last '}'.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        obj = _try(text[start:end + 1])
        if obj is not None:
            return obj
    return None


def _graph_decisions(graph: Dict[str, Any],
                     user_specified: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Summarize the settings the AI chose, in plain language, so the user can
    SEE every variable the engine decided (and know they're editable on canvas).

    user_specified — AI-reported list of {node_id, param} pairs whose values came
    directly from the user's own words. Every other param is an AI assumption,
    flagged so the frontend can show it as editable-before-load.

    One entry per node with tunable params: {node_id, node_label, lane,
    settings:[{key, label, value, default, is_default, user_specified, ...spec}]}.
    """
    uspec_set = set()
    for it in (user_specified or []):
        if isinstance(it, dict) and it.get("node_id") and it.get("param"):
            uspec_set.add((str(it["node_id"]), str(it["param"])))

    out: List[Dict[str, Any]] = []
    for n in graph.get("nodes", []):
        spec = NODE_LIBRARY.get(n.get("type"))
        if not spec or not spec.params:
            continue
        params = n.get("params") or {}
        settings = []
        for pspec in spec.params:
            key = pspec["key"]
            val = params.get(key, pspec.get("default"))
            settings.append({
                "key":        key,
                "label":      pspec.get("label", key),
                "value":      val,
                "default":    pspec.get("default"),
                "is_default": val == pspec.get("default"),
                "user_specified": (str(n.get("id")), key) in uspec_set,
                # Editing metadata so the frontend can render the right control
                "type":       pspec.get("type", "float"),
                "min":        pspec.get("min"),
                "max":        pspec.get("max"),
                "step":       pspec.get("step"),
                "options":    pspec.get("options"),
            })
        out.append({
            "node_id":    n.get("id"),
            "node_label": spec.label,
            "lane":       spec.lane,
            "settings":   settings,
        })
    return out


def _layout_graph(graph: Dict[str, Any]) -> None:
    """Assign each node an (x, y) position by lane, in place."""
    lane_order = ["universe","indicator","alpha","filter","sizing","risk","exit","execution"]
    lane_of = {spec.type: spec.lane for spec in NODE_LIBRARY.values()}
    lane_buckets: Dict[str, List[str]] = {l: [] for l in lane_order}
    for n in graph.get("nodes", []):
        ln = lane_of.get(n.get("type", ""), "alpha")
        lane_buckets.setdefault(ln, []).append(n["id"])
    pos: Dict[str, Dict[str, int]] = {}
    for col, lane in enumerate(lane_order):
        for row, nid in enumerate(lane_buckets.get(lane, [])):
            pos[nid] = {"x": 80 + col * 240, "y": 80 + row * 180}
    for n in graph.get("nodes", []):
        if n["id"] in pos:
            n["position"] = pos[n["id"]]


def _call_chat(provider: str, api_key: str, system_prompt: str, history: List[Dict],
               model: Optional[str] = None, image: Optional[Tuple[str, str]] = None) -> str:
    """Call AI provider with a full conversation history.

    `model` is an optional user-selected override. When None, each provider
    uses its built-in default. `image` (media_type, base64) is attached to the
    last user message for vision-capable providers.
    """
    if provider == "gemini":
        return _call_gemini_chat(api_key, system_prompt, history, model=model, image=image)
    elif provider == "anthropic":
        return _call_anthropic_chat(api_key, system_prompt, history, model=model, image=image)
    elif provider in ("openai", "groq", "mistral"):
        return _call_openai_compat_chat(provider, api_key, system_prompt, history, model=model, image=image)
    else:
        raise HTTPException(400, f"Unknown provider '{provider}'.")


def _call_gemini_chat(api_key: str, system_prompt: str, history: List[Dict],
                      model: Optional[str] = None, image: Optional[Tuple[str, str]] = None) -> str:
    import time
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise HTTPException(503, "google-genai SDK not installed.")
    client = genai.Client(api_key=api_key)
    # Gemini uses alternating user/model turns
    contents = []
    for m in history:
        role = "model" if m["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=m["content"])]))
    # Attach the reference image to the last user turn.
    if image is not None:
        import base64 as _b64
        media_type, data = image
        for c in reversed(contents):
            if c.role == "user":
                c.parts.append(types.Part.from_bytes(data=_b64.b64decode(data), mime_type=media_type))
                break

    # User-selected model is tried first; gemini-2.0-flash stays as a safety
    # fallback on overload. When no model is chosen, use the default pair.
    if model:
        models_to_try = [model] + (["gemini-2.0-flash"] if model != "gemini-2.0-flash" else [])
    else:
        models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash"]
    last_err = None
    quota_hit = False
    for model in models_to_try:
        for attempt in range(3):
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.4,
                    ),
                )
                return resp.text or ""
            except Exception as e:
                last_err = e
                err_low = str(e).lower()
                # Quota/billing limit (429): retrying the same key won't help on a
                # daily cap, and the fallback model shares the same quota. Surface
                # a clear, actionable message instead of pretending it's overload.
                if any(x in err_low for x in ["429", "resource_exhausted", "quota", "exceeded your current quota"]):
                    quota_hit = True
                    break  # quota is per-key — trying another model won't help
                # Transient overload (503): back off and retry, then try next model.
                if any(x in err_low for x in ["503", "unavailable", "overloaded"]):
                    if attempt < 2:
                        time.sleep(2 ** attempt)  # 1s, 2s
                        continue
                    break  # try next model
                raise  # non-retriable error — re-raise immediately
        if quota_hit:
            break
    if quota_hit:
        raise HTTPException(
            429,
            "Your Gemini API key is out of quota (free-tier daily limit reached). "
            "Pick a different model from the Model menu, switch provider on the "
            "Resources page (Groq has a generous free tier), or enable billing on "
            "your Google AI key. Quota resets daily.",
        )
    raise HTTPException(503, f"Gemini is currently overloaded. Please try again in a moment. ({last_err})")


def _call_anthropic_chat(api_key: str, system_prompt: str, history: List[Dict],
                         model: Optional[str] = None, image: Optional[Tuple[str, str]] = None) -> str:
    try:
        import anthropic
    except ImportError:
        raise HTTPException(503, "anthropic SDK not installed.")
    # Attach the reference image to the last user message (Anthropic accepts a
    # content list of image + text blocks).
    if image is not None and history:
        history = list(history)
        media_type, data = image
        for i in range(len(history) - 1, -1, -1):
            if history[i]["role"] == "user":
                history[i] = {"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64",
                                                 "media_type": media_type, "data": data}},
                    {"type": "text", "text": history[i]["content"]},
                ]}
                break
    client = anthropic.Anthropic(api_key=api_key)
    # Prompt caching: the system prompt embeds the full (static) node catalog,
    # which is identical on every turn and across users. Marking it cacheable
    # lets Anthropic reuse it — cache reads are ~90% cheaper and faster (5-min
    # TTL, refreshed on each hit). Sent as a content block so cache_control can
    # attach. Falls back gracefully if the SDK is too old to support it.
    system_blocks = [{
        "type": "text",
        "text": system_prompt,
        "cache_control": {"type": "ephemeral"},
    }]
    create_kwargs = dict(
        model=model or "claude-sonnet-4-5",
        max_tokens=4096,
        temperature=0.4,
        messages=history,
    )
    try:
        msg = client.messages.create(system=system_blocks, **create_kwargs)
    except TypeError:
        # Older SDK that doesn't accept structured system blocks.
        msg = client.messages.create(system=system_prompt, **create_kwargs)
    return msg.content[0].text if msg.content else ""


def _call_openai_compat_chat(provider: str, api_key: str, system_prompt: str, history: List[Dict],
                             model: Optional[str] = None, image: Optional[Tuple[str, str]] = None) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise HTTPException(503, "openai SDK not installed.")
    kwargs: Dict[str, Any] = {"api_key": api_key}
    if provider in _OPENAI_COMPAT_BASE:
        kwargs["base_url"] = _OPENAI_COMPAT_BASE[provider]
    client = OpenAI(**kwargs)
    messages = [{"role": "system", "content": system_prompt}] + list(history)
    # Only OpenAI GPT-4o models are vision-capable here; Groq/Mistral are text-only.
    if image is not None and provider == "openai":
        media_type, data = image
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                messages[i] = {"role": "user", "content": [
                    {"type": "text", "text": messages[i]["content"]},
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{data}"}},
                ]}
                break
    resp = client.chat.completions.create(
        model=model or _PROVIDER_MODEL[provider],
        temperature=0.4,
        response_format={"type": "json_object"},
        messages=messages,
    )
    return resp.choices[0].message.content or ""


@router.post("/pinescript")
def export_pinescript(req: PineExportRequest) -> Dict[str, Any]:
    """Generate a TradingView Pine Script v5 strategy from the graph."""
    try:
        code = generate_pinescript(req.graph, {
            "target_r":         req.target_r,
            "target_close_pct": req.target_close_pct,
            "trail_mode":       req.trail_mode,
            "trail_start":      req.trail_start,
            "trail_params":     req.trail_params,
        })
    except ValueError as e:
        raise HTTPException(400, f"Graph validation failed: {e}")
    return {"code": code, "lines": code.count("\n") + 1}


class GraphBacktestV2Request(SimExecutionFields):
    graph:            Dict[str, Any]
    data_source:      Literal["mt5", "upload"] = "mt5"
    symbol:           str  = "XAUUSD"
    timeframe:        str  = "M15"
    n_bars:           int  = 5000
    csv_data_id:      Optional[str] = None
    # Date range filter (YYYY-MM-DD); takes priority over n_bars when provided
    start_date:       Optional[str] = None
    end_date:         Optional[str] = None
    # Trade management
    target_r:         Optional[float] = 3.0
    target_close_pct: float           = 0.5
    trail_mode:       Literal["none", "candle", "atr", "pips", "swing"] = "candle"
    trail_start:      Literal["immediate", "after_target"] = "after_target"
    trail_params:     Dict[str, Any]  = Field(default_factory=lambda: {"buf_pips": 1})
    challenge:        Optional[ChallengeParams] = None


# ─── Parameter Sweep ─────────────────────────────────────────────────────────

class SweepParamRange(BaseModel):
    node_id:  str
    param_key: str
    values:   List[Any]   # discrete list of values to try


class SweepRequest(BaseModel):
    graph:       Dict[str, Any]
    param_ranges: List[SweepParamRange]
    data_source:  Literal["mt5", "upload"] = "mt5"
    symbol:       str  = "XAUUSD"
    timeframe:    str  = "M15"
    n_bars:       int  = 5000
    csv_data_id:  Optional[str] = None
    target_r:     Optional[float] = 3.0
    trail_mode:   str  = "none"
    trail_params: Dict[str, Any] = Field(default_factory=dict)
    pip:          float = 0.10
    spread_pips:  float = 0.0
    commission:   float = 0.0
    slippage_pips: float = 0.0


class SweepResult(BaseModel):
    params:       Dict[str, Any]
    trades:       int
    wr:           float
    total_r:      float
    profit_factor: float
    max_dd:       float
    sharpe:       Optional[float] = None
    sortino:      Optional[float] = None


@router.post("/sweep")
def param_sweep(
    req: SweepRequest,
    x_dev_user:    Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """
    Grid-search over discrete parameter values. Returns a ranked results table.
    All combinations of param_ranges.values are tried; max 200 combinations.
    """
    import itertools
    from backend.engine.core.data_loader import load_mt5
    from backend.api import store

    # Load data once
    if req.data_source == "mt5":
        df = load_mt5(req.symbol, req.timeframe, req.n_bars)
    elif req.data_source == "upload" and req.csv_data_id:
        df = store.get(req.csv_data_id)
        if df is None:
            raise HTTPException(404, f"data_id {req.csv_data_id} not found")
    else:
        raise HTTPException(400, "data_source must be 'mt5' or 'upload' with csv_data_id")

    pip = infer_pip_from_df(df, req.symbol)
    base_graph = dict(req.graph)

    # Build all combinations
    keys    = [(r.node_id, r.param_key) for r in req.param_ranges]
    values  = [r.values for r in req.param_ranges]
    combos  = list(itertools.product(*values))
    if len(combos) > 200:
        raise HTTPException(400, f"Too many combinations ({len(combos)}). Max 200 — reduce param ranges.")

    results = []
    for combo in combos:
        # Deep-copy the graph and patch params
        import copy, json as _json
        g = _json.loads(_json.dumps(base_graph))
        param_label: Dict[str, Any] = {}
        for (node_id, param_key), val in zip(keys, combo):
            param_label[f"{node_id}.{param_key}"] = val
            for n in g.get("nodes", []):
                if n["id"] == node_id:
                    n.setdefault("params", {})[param_key] = val
        try:
            validated = validate_graph(g)
            strategy  = GraphV2Strategy(validated)
            setups    = strategy.detect(df, {"pip": pip})
            tdf = simulate(
                df, setups,
                target_r      = req.target_r,
                trail_mode    = req.trail_mode,
                trail_params  = req.trail_params,
                pip           = pip,
                spread_pips   = req.spread_pips,
                commission    = req.commission,
                slippage_pips = req.slippage_pips,
            )
            m = compute_metrics(tdf)
            if m is None:
                continue
            def _safe(v):
                return None if (v is None or (isinstance(v, float) and v != v)) else float(v)
            results.append({
                "params":       param_label,
                "trades":       m["trades"],
                "wr":           round(m["wr"], 1),
                "total_r":      round(m["total_r"], 2),
                "profit_factor": round(min(m["profit_factor"], 99.0), 2),
                "max_dd":       round(m["max_dd"], 2),
                "sharpe":       _safe(m.get("sharpe")),
                "sortino":      _safe(m.get("sortino")),
            })
        except Exception:
            continue   # skip invalid combos silently

    # Sort by Sharpe if available, else profit_factor
    results.sort(key=lambda r: (r.get("sharpe") or 0, r["profit_factor"]), reverse=True)
    return {"results": results, "combinations_tried": len(combos)}


# ─── Walk-forward & Monte Carlo ───────────────────────────────────────────────

class WalkForwardRequest(BaseModel):
    graph:        Dict[str, Any]
    data_source:  Literal["mt5", "upload"] = "mt5"
    symbol:       str  = "XAUUSD"
    timeframe:    str  = "M15"
    n_bars:       int  = 5000
    csv_data_id:  Optional[str] = None
    n_splits:     int  = 5     # number of in/out-of-sample windows
    is_pct:       float = 0.7  # fraction of each window used for in-sample
    target_r:     Optional[float] = 3.0
    trail_mode:   str  = "none"
    trail_params: Dict[str, Any] = Field(default_factory=dict)
    spread_pips:  float = 0.0
    commission:   float = 0.0
    slippage_pips: float = 0.0


@router.post("/walk-forward")
def walk_forward(
    req: WalkForwardRequest,
    x_dev_user:    Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """
    Rolling walk-forward test. Splits data into N windows; for each window
    runs a backtest on the out-of-sample portion. Returns per-window metrics
    and an aggregate OOS equity curve.
    """
    from backend.engine.core.data_loader import load_mt5
    from backend.api import store

    if req.data_source == "mt5":
        df = load_mt5(req.symbol, req.timeframe, req.n_bars)
    elif req.data_source == "upload" and req.csv_data_id:
        df = store.get(req.csv_data_id)
        if df is None:
            raise HTTPException(404, f"data_id {req.csv_data_id} not found")
    else:
        raise HTTPException(400, "Bad data_source")

    pip = infer_pip_from_df(df, req.symbol)
    n   = len(df)
    window_size = n // req.n_splits
    if window_size < 100:
        raise HTTPException(400, "Not enough bars per window — increase n_bars or reduce n_splits.")

    try:
        validated = validate_graph(req.graph)
        strategy  = GraphV2Strategy(validated)
    except Exception as e:
        raise HTTPException(400, str(e))

    windows = []
    oos_equity = [100.0]   # track OOS equity cumulatively

    for split in range(req.n_splits):
        start = split * window_size
        end   = start + window_size
        is_end = start + int(window_size * req.is_pct)
        oos_df = df.iloc[is_end:end].reset_index(drop=True)
        if len(oos_df) < 20:
            continue
        try:
            setups = strategy.detect(oos_df, {"pip": pip})
            tdf = simulate(
                oos_df, setups,
                target_r      = req.target_r,
                trail_mode    = req.trail_mode,
                trail_params  = req.trail_params,
                pip           = pip,
                spread_pips   = req.spread_pips,
                commission    = req.commission,
                slippage_pips = req.slippage_pips,
            )
            m = compute_metrics(tdf, initial_equity=oos_equity[-1])
            if m is None:
                windows.append({"split": split + 1, "trades": 0, "oos_bars": len(oos_df),
                                 "start": str(oos_df["time"].iloc[0].date()),
                                 "end":   str(oos_df["time"].iloc[-1].date())})
                continue
            oos_equity.append(float(m["final_equity"]))
            windows.append({
                "split":    split + 1,
                "start":    str(oos_df["time"].iloc[0].date()),
                "end":      str(oos_df["time"].iloc[-1].date()),
                "oos_bars": len(oos_df),
                "trades":   m["trades"],
                "wr":       round(m["wr"], 1),
                "total_r":  round(m["total_r"], 2),
                "max_dd":   round(m["max_dd"], 2),
                "pf":       round(min(m["profit_factor"], 99.0), 2),
            })
        except Exception:
            continue

    return {
        "windows":     windows,
        "oos_equity":  oos_equity,
        "n_splits":    req.n_splits,
    }


class MonteCarloRequest(BaseModel):
    graph:        Dict[str, Any]
    data_source:  Literal["mt5", "upload"] = "mt5"
    symbol:       str  = "XAUUSD"
    timeframe:    str  = "M15"
    n_bars:       int  = 5000
    csv_data_id:  Optional[str] = None
    n_sims:       int  = 200   # number of Monte Carlo runs
    target_r:     Optional[float] = 3.0
    trail_mode:   str  = "none"
    trail_params: Dict[str, Any] = Field(default_factory=dict)
    spread_pips:  float = 0.0
    commission:   float = 0.0
    slippage_pips: float = 0.0


@router.post("/monte-carlo")
def monte_carlo(
    req: MonteCarloRequest,
    x_dev_user:    Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """
    Monte Carlo simulation: shuffle the detected trade PnL sequence N times
    and compute equity curve percentile bands (p5, p25, p50, p75, p95).
    """
    import numpy as np
    from backend.engine.core.data_loader import load_mt5
    from backend.api import store

    if req.data_source == "mt5":
        df = load_mt5(req.symbol, req.timeframe, req.n_bars)
    elif req.data_source == "upload" and req.csv_data_id:
        df = store.get(req.csv_data_id)
        if df is None:
            raise HTTPException(404, f"data_id {req.csv_data_id} not found")
    else:
        raise HTTPException(400, "Bad data_source")

    pip = infer_pip_from_df(df, req.symbol)

    try:
        validated = validate_graph(req.graph)
        strategy  = GraphV2Strategy(validated)
        setups    = strategy.detect(df, {"pip": pip})
        tdf = simulate(
            df, setups,
            target_r      = req.target_r,
            trail_mode    = req.trail_mode,
            trail_params  = req.trail_params,
            pip           = pip,
            spread_pips   = req.spread_pips,
            commission    = req.commission,
            slippage_pips = req.slippage_pips,
        )
    except Exception as e:
        raise HTTPException(422, str(e))

    if tdf is None or tdf.empty:
        raise HTTPException(422, "No trades detected.")

    res = tdf[tdf["result"] != "Unresolved"]
    if len(res) < 5:
        raise HTTPException(422, "Need at least 5 resolved trades for Monte Carlo.")

    pnl = res["pnl_r"].values
    n_sims = min(req.n_sims, 1000)

    curves = []
    rng = np.random.default_rng(42)
    risk_pct_mc = 0.02   # fixed 2% per trade for MC — exaggerates path dependency
    for _ in range(n_sims):
        shuffled = rng.permutation(pnl)
        eq = 100.0
        curve = [eq]
        for r in shuffled:
            # Compound: risk fraction of current equity, so order matters
            eq = max(0.01, eq + r * eq * risk_pct_mc)
            curve.append(eq)
        curves.append(curve)

    # Pad all curves to same length
    max_len = max(len(c) for c in curves)
    padded  = np.array([c + [c[-1]] * (max_len - len(c)) for c in curves])

    percentiles = {
        "p5":  np.percentile(padded, 5,  axis=0).tolist(),
        "p25": np.percentile(padded, 25, axis=0).tolist(),
        "p50": np.percentile(padded, 50, axis=0).tolist(),
        "p75": np.percentile(padded, 75, axis=0).tolist(),
        "p95": np.percentile(padded, 95, axis=0).tolist(),
    }

    m = compute_metrics(res)
    return {
        "n_sims":      n_sims,
        "n_trades":    len(pnl),
        "percentiles": percentiles,
        "base_metrics": {
            "total_r":  round(float(pnl.sum()), 2),
            "max_dd":   round(float(m["max_dd"]), 2) if m else None,
            "wr":       round(float(m["wr"]), 1) if m else None,
        },
    }


@router.post("/backtest", response_model=BacktestResponse)
def run_v2_backtest(
    req: GraphBacktestV2Request,
    db:  Session = Depends(get_db),
    x_dev_user:    Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
):
    try:
        graph = validate_graph(req.graph)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # ── Cache check (skip for upload data — unique per session) ──────────────
    # Key on the FULL request body so EVERY result-affecting field busts the
    # cache. A hand-picked subset previously omitted execution costs, risk/
    # equity, trail params, date range, session hours and the prop-firm
    # challenge — so changing those sliders returned a stale cached result.
    # csv_data_id is irrelevant here (upload is excluded above).
    _cache_key = None
    if req.data_source != "upload":
        _cache_key = req.model_dump(mode="json", exclude={"csv_data_id"})
        cached = backtest_cache.get(_cache_key)
        if cached is not None:
            return cached

    # Soft-auth + quota (same pattern as /backtest)
    user = None
    try:
        from backend.api.auth import current_user as _cu
        user = _cu(db=db, x_dev_user=x_dev_user, authorization=authorization)
        from backend.api.limits import enforce_backtest_quota as _eq
        _eq(user=user, db=db)
    except HTTPException as e:
        if e.status_code == 401:
            user = None
        else:
            raise

    # Data
    if req.data_source == "mt5":
        try:
            df = load_mt5(req.symbol, req.timeframe, req.n_bars)
        except Exception as e:
            raise HTTPException(400, f"MT5 fetch failed: {e}")
    elif req.data_source == "upload":
        if not req.csv_data_id:
            raise HTTPException(400, "csv_data_id required when data_source='upload'")
        df = store.get(req.csv_data_id)
        if df is None:
            raise HTTPException(404, f"data_id {req.csv_data_id} not found")
    else:
        raise HTTPException(400, f"Unsupported data_source: {req.data_source}")

    # Apply date range filter when start_date or end_date is given
    if req.start_date or req.end_date:
        import pandas as pd
        df = df.copy()
        df["time"] = pd.to_datetime(df["time"])
        if req.start_date:
            df = df[df["time"] >= pd.Timestamp(req.start_date)]
        if req.end_date:
            df = df[df["time"] <= pd.Timestamp(req.end_date) + pd.Timedelta(days=1)]
        df = df.reset_index(drop=True)
        if len(df) == 0:
            raise HTTPException(422, "No bars in the specified date range.")

    pip = infer_pip_from_df(df, req.symbol)
    strategy = GraphV2Strategy(graph)
    setups = strategy.detect(df, {"pip": pip})

    tdf = simulate(
        df, setups,
        target_r         = req.target_r,
        target_close_pct = req.target_close_pct,
        trail_mode       = req.trail_mode,
        trail_start      = req.trail_start,
        trail_params     = req.trail_params,
        pip              = pip,
        **_effective_sim_kwargs(req, strategy),
    )
    m = compute_metrics(tdf,
                       initial_equity = req.initial_equity,
                       risk_pct       = req.risk_pct,
                       max_risk_usd   = req.max_risk_usd)
    if m is None:
        raise HTTPException(422, "No resolved trades — loosen parameters or check graph wiring.")

    # Log to Supabase — sole source of truth for backtest history.
    from backend.api import supa
    supa.log_backtest_run(
        user_id         = (user.clerk_id if user is not None else None),
        strategy_id     = "graph_v2:" + (graph.get("name") or "custom"),
        params_snapshot = {"graph": graph},
        metrics         = {
            "trades": m["trades"], "wr": m["wr"], "ev": m["ev"],
            "total_r": m["total_r"],
            "profit_factor": (m["profit_factor"] if m["profit_factor"] != float("inf") else 99.0),
            "max_dd": m["max_dd"], "final_equity": m["final_equity"],
        },
        symbol = req.symbol, timeframe = req.timeframe, bars = len(df),
    )

    # Optional prop firm challenge analysis
    challenge_result = None
    if req.challenge is not None:
        cr = compute_challenge_result(
            tdf, df,
            req.challenge.model_dump(),
            risk_pct     = req.risk_pct,
            max_risk_usd = req.max_risk_usd,
        )
        if cr is not None:
            challenge_result = ChallengeResult(
                passed         = cr["passed"],
                verdict        = cr["verdict"],
                failure_rule   = cr.get("failure_rule"),
                failure_day    = cr.get("failure_day"),
                profit_hit_day = cr.get("profit_hit_day"),
                trading_days   = cr["trading_days"],
                final_equity   = cr["final_equity"],
                account_size   = cr["account_size"],
                daily          = [ChallengeDayResult(**d) for d in cr["daily"]],
            )

    response = BacktestResponse(
        strategy_id  = "graph_v2:custom",
        data_range   = (df["time"].iloc[0].isoformat(), df["time"].iloc[-1].isoformat()),
        bars         = len(df),
        pip          = pip,
        metrics      = BacktestMetrics(
            trades        = m["trades"],
            wr            = m["wr"],
            ev            = m["ev"],
            total_r       = m["total_r"],
            profit_factor = (m["profit_factor"] if m["profit_factor"] != float("inf") else 99.0),
            max_dd        = m["max_dd"],
            avg_win       = m["avg_win"],
            avg_loss      = m["avg_loss"],
            avg_rr        = m.get("avg_rr") or 0.0,
            sharpe        = (m.get("sharpe") if m.get("sharpe") and not (isinstance(m.get("sharpe"), float) and (m["sharpe"] != m["sharpe"])) else None),
            sortino       = (m.get("sortino") if m.get("sortino") and not (isinstance(m.get("sortino"), float) and (m["sortino"] != m["sortino"])) else None),
            calmar        = (m.get("calmar") if m.get("calmar") and not (isinstance(m.get("calmar"), float) and (m["calmar"] != m["calmar"])) else None),
            cagr          = (m.get("cagr") if m.get("cagr") and not (isinstance(m.get("cagr"), float) and (m["cagr"] != m["cagr"])) else None),
            final_equity  = m["final_equity"],
            n_setups      = m["n_setups"],
            n_unresolved  = m["n_unresolved"],
            exit_counts   = {str(k): int(v) for k, v in m["exit_counts"].items()},
        ),
        equity_curve = m["curve"].tolist(),
        pnl_series   = m["pnl"].tolist(),
        issues       = validate_ohlcv(df),
        data_source  = data_source_of(df),
        challenge    = challenge_result,
    )

    # Store in cache (only for MT5/yfinance data, not user uploads)
    if _cache_key is not None:
        backtest_cache.set(_cache_key, response)

    return response
