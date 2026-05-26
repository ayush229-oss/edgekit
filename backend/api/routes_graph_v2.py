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
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.engine.builder_v2 import (
    NODE_LIBRARY, GraphV2Strategy, list_templates, get_template,
    validate_graph, complexity_score, generate_pinescript,
)
from backend.engine.core import (
    load_mt5, simulate, compute_metrics, infer_pip_from_df, validate_ohlcv,
)
from backend.api import store
from backend.api.schemas import BacktestResponse, BacktestMetrics
from backend.db import get_db, BacktestRun


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
    "indicator.order_block":[
        ("ob_{direction}_{scan_min}_{scan_max}_h", "OB High",   "#F59E0B", "dashed", 1),
        ("ob_{direction}_{scan_min}_{scan_max}_m", "OB Mid",    "#F59E0B", "solid",  1),
        ("ob_{direction}_{scan_min}_{scan_max}_l", "OB Low",    "#F59E0B", "dashed", 1),
    ],
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


class ChartPreviewRequest(BaseModel):
    graph:            Dict[str, Any]
    symbol:           str  = "XAUUSD"
    timeframe:        str  = "M15"
    n_bars:           int  = 500
    target_r:         Optional[float] = 3.0
    target_close_pct: float           = 0.5
    trail_mode:       Literal["none", "candle", "atr", "pips", "swing"] = "candle"
    trail_start:      Literal["immediate", "after_target"] = "after_target"
    trail_params:     Dict[str, Any]  = Field(default_factory=lambda: {"buf_pips": 1})


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

        return {
            "symbol":    req.symbol,
            "timeframe": req.timeframe,
            "pip":       pip,
            "bars":      bars,
            "trades":    trades,
            "n_setups":  len(setups),
            "indicators": indicators,
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Packing response failed: {type(e).__name__}: {e}")


# ─── AI: plain-English → V2 graph ─────────────────────────────────────────
class FromTextRequest(BaseModel):
    description: str
    symbol:      str = "XAUUSD"
    timeframe:   str = "M15"


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
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key"),
) -> Dict[str, Any]:
    """
    Convert a plain-English strategy description into a V2 graph using Gemini.
    Returns a V2Graph JSON that the canvas can render directly.

    API key priority: request header (user's own key from Resources page) →
    server env var (admin default).
    """
    try:
        return _from_text_impl(req, x_gemini_key)
    except HTTPException:
        raise
    except Exception as e:
        # Catch-all: never let a bare exception leak as "Internal Server Error".
        # The frontend reads `detail` and shows it to the user — make it useful.
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"AI generation crashed: {type(e).__name__}: {str(e)[:300]}")


def _from_text_impl(
    req: "FromTextRequest",
    x_gemini_key: Optional[str],
) -> Dict[str, Any]:
    import os, json as _json
    api_key = (x_gemini_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    if not api_key:
        raise HTTPException(
            503,
            "AI generation needs a Gemini API key. Add yours under Resources → AI Model, "
            "or set GEMINI_API_KEY on the server."
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise HTTPException(503, "AI generation disabled: google-genai SDK not installed.")

    # Compact catalog — only the bits the model needs to produce valid graphs
    catalog = []
    for spec in NODE_LIBRARY.values():
        d = spec.to_dict()
        catalog.append({
            "type":     d["type"],
            "lane":     d["lane"],
            "label":    d["label"],
            "desc":     d["description"],
            "inputs":   [{"name": p["name"], "type": p["type"]} for p in d["inputs"]],
            "outputs":  [{"name": p["name"], "type": p["type"]} for p in d["outputs"]],
            "params":   [
                {"key": p["key"], "type": p["type"], "default": p["default"]}
                for p in d["params"]
            ],
        })

    system_prompt = _AI_SYSTEM_TEMPLATE.format(catalog=_json.dumps(catalog, separators=(",", ":")))
    user_prompt   = (
        f"Symbol: {req.symbol}\nTimeframe: {req.timeframe}\n\n"
        f"Strategy description:\n{req.description}\n\n"
        f"Generate the V2 graph JSON."
    )

    # Force the response shape so the model can't return a malformed graph
    response_schema = {
        "type": "object",
        "properties": {
            "name":  {"type": "string"},
            "nodes": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "id":     {"type": "string"},
                    "type":   {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["id", "type", "params"],
            }},
            "edges": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "from":      {"type": "string"},
                    "to":        {"type": "string"},
                    "from_port": {"type": "string"},
                    "to_port":   {"type": "string"},
                },
                "required": ["from", "to", "from_port", "to_port"],
            }},
        },
        "required": ["name", "nodes", "edges"],
    }

    # Client construction can throw on some SDK versions if the key is malformed
    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        raise HTTPException(400, f"Could not initialize Gemini client: {e}. Check your API key on the Resources page.")

    def _call(extra_user: str = "") -> str:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt + extra_user,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=response_schema,
                temperature=0.3,
            ),
        )
        return resp.text or ""

    # Wrap the actual Gemini SDK call. Failures here are almost always one of:
    #   • Bad/expired API key             → 400, ask user to check Resources page
    #   • Quota / rate limit              → 429, ask user to wait
    #   • Network or transient            → 503, ask user to retry
    # Anything else falls through as a 502 (upstream provider error). We never
    # let the raw SDK exception leak to the frontend as a bare 500.
    try:
        raw = _call()
    except Exception as e:
        msg = str(e)
        low = msg.lower()
        if "api_key_invalid" in low or "api key not valid" in low or "invalid api key" in low:
            raise HTTPException(
                400,
                "The Gemini API key is invalid. Update it on the Resources page "
                "(get a free one at aistudio.google.com/apikey)."
            )
        if "quota" in low or "rate" in low or "429" in low or "resource_exhausted" in low:
            raise HTTPException(
                429,
                "Gemini quota / rate limit hit. Wait a minute and try again, "
                "or check your account at aistudio.google.com."
            )
        if "permission" in low or "permission_denied" in low or "403" in low:
            raise HTTPException(
                403,
                "The Gemini API key doesn't have permission to call this model. "
                "Make sure your key is enabled for Gemini 2.5 Flash."
            )
        # Unknown upstream failure — surface a readable message, not a raw 500.
        raise HTTPException(502, f"AI provider error: {msg[:300]}")

    try:
        graph = _json.loads(raw)
        validate_graph(graph)
    except Exception as e:
        # Retry once with the error message — JSON-schema mode guarantees valid JSON
        # so the only thing that can still fail is the graph-semantics validator.
        try:
            raw2 = _call(f"\n\nYour previous attempt failed graph validation: {e}\nRebuild the graph correctly.")
            graph = _json.loads(raw2)
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


class GraphBacktestV2Request(BaseModel):
    graph:            Dict[str, Any]
    data_source:      Literal["mt5", "upload"] = "mt5"
    symbol:           str  = "XAUUSD"
    timeframe:        str  = "M15"
    n_bars:           int  = 5000
    csv_data_id:      Optional[str] = None
    # Trade management — passed straight through to the simulator. (Exit nodes
    # in the graph also set these, but request-level lets the user override
    # without editing the graph.)
    target_r:         Optional[float] = 3.0
    target_close_pct: float           = 0.5
    trail_mode:       Literal["none", "candle", "atr", "pips", "swing"] = "candle"
    trail_start:      Literal["immediate", "after_target"] = "after_target"
    trail_params:     Dict[str, Any]  = Field(default_factory=lambda: {"buf_pips": 1})
    initial_equity:   float = 100.0
    risk_pct:         float = 0.01
    max_risk_usd:     float = 600.0
    max_concurrent:   int   = 1
    order_expiry:     Optional[int] = None
    session_hours:    Optional[Tuple[int, int]] = None


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

    pip = infer_pip_from_df(df, req.symbol)
    setups = GraphV2Strategy(graph).detect(df, {"pip": pip})

    tdf = simulate(
        df, setups,
        target_r         = req.target_r,
        target_close_pct = req.target_close_pct,
        trail_mode       = req.trail_mode,
        trail_start      = req.trail_start,
        trail_params     = req.trail_params,
        max_concurrent   = req.max_concurrent,
        order_expiry     = req.order_expiry,
        session_hours    = req.session_hours,
        pip              = pip,
    )
    m = compute_metrics(tdf,
                       initial_equity = req.initial_equity,
                       risk_pct       = req.risk_pct,
                       max_risk_usd   = req.max_risk_usd)
    if m is None:
        raise HTTPException(422, "No resolved trades — loosen parameters or check graph wiring.")

    if user is not None:
        try:
            db.add(BacktestRun(
                user_id         = user.id,
                strategy_id     = "graph_v2:" + (graph.get("name") or "custom"),
                params_snapshot = {"graph": graph},
                metrics         = {
                    "trades": m["trades"], "wr": m["wr"], "ev": m["ev"],
                    "total_r": m["total_r"],
                    "profit_factor": (m["profit_factor"] if m["profit_factor"] != float("inf") else 99.0),
                    "max_dd": m["max_dd"], "final_equity": m["final_equity"],
                },
                symbol = req.symbol, timeframe = req.timeframe, bars = len(df),
            ))
            db.commit()
        except Exception:
            db.rollback()

    return BacktestResponse(
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
            final_equity  = m["final_equity"],
            n_setups      = m["n_setups"],
            n_unresolved  = m["n_unresolved"],
            exit_counts   = {str(k): int(v) for k, v in m["exit_counts"].items()},
        ),
        equity_curve = m["curve"].tolist(),
        pnl_series   = m["pnl"].tolist(),
        issues       = validate_ohlcv(df),
    )
