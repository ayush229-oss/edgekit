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

        # Structural artifacts (OB zones, FVG gaps, swept levels) the engine
        # actually decided — drawn as shapes, not guessed from param keys.
        artifacts = list(getattr(getattr(strategy, "ctx", None), "trace", []) or [])

        return {
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

MODE 2 — BUILD (when you have enough to build a solid graph):
Output ONLY this JSON, nothing else:
{{"type":"graph","graph":{graph_schema}}}

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
          ("graph",   graph_dict)  — valid, laid-out graph ready to load
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
            return ("graph", graph)
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
        return {"type": "graph", "graph": payload, "decisions": _graph_decisions(payload)}
    if kind == "message":
        return {"type": "message", "content": payload}
    # Still invalid after repair attempts — be honest instead of looping.
    return {"type": "message", "content": (
        "I'm having trouble wiring this into a valid strategy graph. Try describing "
        "it a little more simply — the exact entry trigger, the exit, and how much "
        "to risk per trade — or pick a stronger model from the Model menu, and I'll "
        "try again."
    )}


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


def _graph_decisions(graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Summarize the settings the AI chose, in plain language, so the user can
    SEE every variable the engine decided (and know they're editable on canvas).

    One entry per node with tunable params: {node_id, node_label, lane,
    settings:[{key, label, value, default, is_default}]}.
    """
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
    challenge:        Optional[ChallengeParams] = None


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
    _cache_key = None
    if req.data_source != "upload":
        _cache_key = {
            "graph":      req.graph,
            "symbol":     req.symbol,
            "timeframe":  req.timeframe,
            "n_bars":     req.n_bars,
            "target_r":   req.target_r,
            "close_pct":  req.target_close_pct,
            "trail_mode": req.trail_mode,
        }
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
