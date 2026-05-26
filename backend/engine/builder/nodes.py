"""
Node library — every node the visual builder can drop on its canvas.

Each NodeSpec describes:
    type        unique id, e.g. "signal.ema_cross"
    category    "signal" | "filter" | "entry" | "risk"
    label       human-friendly title shown on the node header
    description one-line plain-English explanation of what it does
    params      list of ParamSpec dicts (key, label, type, default, ...)
    eval_fn     called per-bar (signal/filter) or per-setup (entry/risk)

The eval_fn signature differs by category:
    signal.eval(df, i, p)  -> Optional["Bull" | "Bear"]
    filter.eval(df, i, p)  -> bool
    entry.eval(df, i, p, direction)        -> float (entry price)
    risk.eval(df, i, p, direction, entry)  -> float (sl price)

Lean v1 library: 6 signals, 3 filters, 2 entries, 3 risks.
Add more by appending to NODE_LIBRARY — no other code needs to change.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional
import numpy as np
import pandas as pd


NodeCategory = Literal["signal", "filter", "entry", "risk"]


@dataclass
class NodeSpec:
    type:        str
    category:    NodeCategory
    label:       str
    description: str
    params:      List[Dict[str, Any]] = field(default_factory=list)
    eval_fn:     Optional[Callable]   = None    # set by the @register decorator

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type":        self.type,
            "category":    self.category,
            "label":       self.label,
            "description": self.description,
            "params":      self.params,
        }


NODE_LIBRARY: Dict[str, NodeSpec] = {}


def register(spec: NodeSpec):
    """Decorator: attach an eval_fn to a NodeSpec and register it."""
    def deco(fn: Callable):
        spec.eval_fn = fn
        NODE_LIBRARY[spec.type] = spec
        return fn
    return deco


# ─── Helpers (kept here so node logic stays self-contained) ─────────────────
def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    alpha = 2.0 / (period + 1)
    out   = np.zeros_like(arr, dtype=float)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


def _rsi(arr: np.ndarray, period: int = 14) -> np.ndarray:
    delta = np.diff(arr, prepend=arr[0])
    gain  = np.where(delta > 0, delta, 0.0)
    loss  = np.where(delta < 0, -delta, 0.0)
    avg_g = pd.Series(gain).ewm(alpha=1/period, adjust=False).mean().values
    avg_l = pd.Series(loss).ewm(alpha=1/period, adjust=False).mean().values
    rs    = np.where(avg_l == 0, 0, avg_g / np.maximum(avg_l, 1e-9))
    return 100 - 100 / (1 + rs)


def _atr(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    H, L, C = df["H"].values, df["L"].values, df["C"].values
    prev_c  = np.concatenate(([C[0]], C[:-1]))
    tr      = np.maximum.reduce([H - L, np.abs(H - prev_c), np.abs(L - prev_c)])
    return pd.Series(tr).ewm(alpha=1/period, adjust=False).mean().values


# Cache of precomputed series per (df_id, key) — populated by GraphStrategy
# before walking bars, so each per-bar eval is O(1).
_CACHE_KEY = "__edgekit_node_cache__"


def _cache(df: pd.DataFrame) -> Dict[str, Any]:
    if not hasattr(df, "attrs") or _CACHE_KEY not in df.attrs:
        df.attrs[_CACHE_KEY] = {}
    return df.attrs[_CACHE_KEY]


# ═══════════════════════════════════════════════════════════════════════════
# SIGNALS
# ═══════════════════════════════════════════════════════════════════════════

@register(NodeSpec(
    type="signal.ema_cross",
    category="signal",
    label="EMA cross",
    description="Fires when the fast EMA crosses the slow EMA. Pick direction.",
    params=[
        {"key": "fast",      "label": "Fast EMA",  "type": "int", "default": 20, "min": 2,  "max": 200},
        {"key": "slow",      "label": "Slow EMA",  "type": "int", "default": 50, "min": 5,  "max": 400},
        {"key": "direction", "label": "Direction", "type": "select",
         "default": "both",   "options": ["long", "short", "both"]},
    ],
))
def _ema_cross(df, i, p):
    cache = _cache(df)
    key_f = f"ema{p['fast']}"
    key_s = f"ema{p['slow']}"
    if key_f not in cache: cache[key_f] = _ema(df["C"].values, int(p["fast"]))
    if key_s not in cache: cache[key_s] = _ema(df["C"].values, int(p["slow"]))
    if i < 1: return None
    f0, f1 = cache[key_f][i-1], cache[key_f][i]
    s0, s1 = cache[key_s][i-1], cache[key_s][i]
    up   = f0 <= s0 and f1 > s1
    down = f0 >= s0 and f1 < s1
    d = p.get("direction", "both")
    if up   and d in ("long", "both"):  return "Bull"
    if down and d in ("short", "both"): return "Bear"
    return None


@register(NodeSpec(
    type="signal.rsi_threshold",
    category="signal",
    label="RSI threshold",
    description="Fires when RSI crosses your overbought / oversold level.",
    params=[
        {"key": "period",     "label": "RSI period", "type": "int",   "default": 14, "min": 2, "max": 50},
        {"key": "oversold",   "label": "Oversold",   "type": "int",   "default": 30, "min": 5, "max": 45},
        {"key": "overbought", "label": "Overbought", "type": "int",   "default": 70, "min": 55, "max": 95},
        {"key": "direction",  "label": "Direction",  "type": "select",
         "default": "both", "options": ["long", "short", "both"]},
    ],
))
def _rsi_threshold(df, i, p):
    cache = _cache(df)
    key   = f"rsi{p['period']}"
    if key not in cache: cache[key] = _rsi(df["C"].values, int(p["period"]))
    if i < 1: return None
    prev, curr = cache[key][i-1], cache[key][i]
    d = p.get("direction", "both")
    # Cross UP through oversold = long; cross DOWN through overbought = short
    if d in ("long", "both")  and prev <= p["oversold"]   and curr >  p["oversold"]:   return "Bull"
    if d in ("short", "both") and prev >= p["overbought"] and curr <  p["overbought"]: return "Bear"
    return None


@register(NodeSpec(
    type="signal.equal_levels",
    category="signal",
    label="Equal highs / lows",
    description="Fires when 2+ swing highs (or lows) are within tolerance — liquidity pool.",
    params=[
        {"key": "count",      "label": "Min equal levels", "type": "int",   "default": 2, "min": 2, "max": 5},
        {"key": "tolerance",  "label": "Tolerance (pips)", "type": "float", "default": 3, "min": 0.5, "max": 20},
        {"key": "lookback",   "label": "Lookback bars",    "type": "int",   "default": 30, "min": 5, "max": 200},
        {"key": "direction",  "label": "Direction",        "type": "select",
         "default": "both", "options": ["long", "short", "both"]},
    ],
))
def _equal_levels(df, i, p):
    pip = p.get("pip", 0.1)
    tol = p["tolerance"] * pip
    lb  = int(p["lookback"])
    if i < lb: return None
    H = df["H"].values[i-lb:i+1]
    L = df["L"].values[i-lb:i+1]
    d = p.get("direction", "both")
    if d in ("short", "both"):   # liquidity above (equal highs) → bear setup
        top = H.max()
        if (np.abs(H - top) <= tol).sum() >= p["count"]:
            return "Bear"
    if d in ("long", "both"):    # liquidity below (equal lows) → bull setup
        bot = L.min()
        if (np.abs(L - bot) <= tol).sum() >= p["count"]:
            return "Bull"
    return None


@register(NodeSpec(
    type="signal.fvg",
    category="signal",
    label="Fair Value Gap",
    description="Fires when a 3-bar imbalance forms (gap between bar n-2 and bar n).",
    params=[
        {"key": "min_pips",  "label": "Min gap (pips)", "type": "float", "default": 2.0, "min": 0.5, "max": 50},
        {"key": "direction", "label": "Direction",      "type": "select",
         "default": "both", "options": ["long", "short", "both"]},
    ],
))
def _fvg(df, i, p):
    if i < 2: return None
    pip = p.get("pip", 0.1)
    minpx = p["min_pips"] * pip
    H, L = df["H"].values, df["L"].values
    d = p.get("direction", "both")
    # Bull FVG: low[i] > high[i-2]
    if d in ("long", "both") and L[i] - H[i-2] >= minpx:
        return "Bull"
    # Bear FVG: high[i] < low[i-2]
    if d in ("short", "both") and L[i-2] - H[i] >= minpx:
        return "Bear"
    return None


@register(NodeSpec(
    type="signal.swing_break",
    category="signal",
    label="Swing break",
    description="Fires when price closes above a recent swing high (long) or below a swing low (short).",
    params=[
        {"key": "lookback",  "label": "Swing lookback", "type": "int", "default": 20, "min": 5, "max": 100},
        {"key": "direction", "label": "Direction",      "type": "select",
         "default": "both",  "options": ["long", "short", "both"]},
    ],
))
def _swing_break(df, i, p):
    lb = int(p["lookback"])
    if i < lb + 1: return None
    H, L, C = df["H"].values, df["L"].values, df["C"].values
    prior_hi = H[i-lb:i].max()
    prior_lo = L[i-lb:i].min()
    d = p.get("direction", "both")
    if d in ("long", "both")  and C[i] > prior_hi and C[i-1] <= prior_hi: return "Bull"
    if d in ("short", "both") and C[i] < prior_lo and C[i-1] >= prior_lo: return "Bear"
    return None


@register(NodeSpec(
    type="signal.engulfing",
    category="signal",
    label="Engulfing candle",
    description="Fires on a bullish or bearish engulfing pattern (body of bar n covers bar n-1).",
    params=[
        {"key": "direction", "label": "Direction", "type": "select",
         "default": "both",  "options": ["long", "short", "both"]},
    ],
))
def _engulfing(df, i, p):
    if i < 1: return None
    O, C = df["O"].values, df["C"].values
    o0, c0 = O[i-1], C[i-1]
    o1, c1 = O[i],   C[i]
    d = p.get("direction", "both")
    # Bullish engulf: prev red, curr green, curr body >= prev body
    if d in ("long", "both")  and c0 < o0 and c1 > o1 and c1 >= o0 and o1 <= c0: return "Bull"
    if d in ("short", "both") and c0 > o0 and c1 < o1 and c1 <= o0 and o1 >= c0: return "Bear"
    return None


# ═══════════════════════════════════════════════════════════════════════════
# FILTERS  (must all return True for a signal to become a setup)
# ═══════════════════════════════════════════════════════════════════════════

@register(NodeSpec(
    type="filter.session",
    category="filter",
    label="Session hours",
    description="Only allow setups during this time-of-day window (server local time).",
    params=[
        {"key": "start_hour", "label": "Start hour (0-23)", "type": "int", "default": 7,  "min": 0, "max": 23},
        {"key": "end_hour",   "label": "End hour (0-23)",   "type": "int", "default": 17, "min": 1, "max": 24},
    ],
))
def _filter_session(df, i, p):
    h = df["time"].dt.hour.iloc[i]
    return int(p["start_hour"]) <= h < int(p["end_hour"])


@register(NodeSpec(
    type="filter.atr_min",
    category="filter",
    label="ATR minimum",
    description="Skip the setup if volatility (ATR) is below this floor — avoids chop.",
    params=[
        {"key": "period",   "label": "ATR period",  "type": "int",   "default": 14,  "min": 2,  "max": 50},
        {"key": "min_pips", "label": "Min ATR (pips)", "type": "float", "default": 5, "min": 0.5, "max": 100},
    ],
))
def _filter_atr_min(df, i, p):
    cache = _cache(df)
    key   = f"atr{p['period']}"
    if key not in cache: cache[key] = _atr(df, int(p["period"]))
    pip = p.get("pip", 0.1)
    return cache[key][i] >= p["min_pips"] * pip


@register(NodeSpec(
    type="filter.cooldown",
    category="filter",
    label="Cooldown",
    description="Block new setups for N bars after the last one fired — prevents spam in choppy markets.",
    params=[
        {"key": "bars", "label": "Cooldown bars", "type": "int", "default": 10, "min": 1, "max": 200},
    ],
))
def _filter_cooldown(df, i, p):
    # Stateful filter — uses _cache to remember last-fired bar per node-id.
    nid = p.get("__node_id__", "cooldown")
    cache = _cache(df)
    last  = cache.get(f"_last_{nid}", -10_000)
    if i - last < int(p["bars"]):
        return False
    cache[f"_last_{nid}_pending"] = i      # tentatively mark; engine confirms on setup-emit
    return True


# ═══════════════════════════════════════════════════════════════════════════
# ENTRIES
# ═══════════════════════════════════════════════════════════════════════════

@register(NodeSpec(
    type="entry.market",
    category="entry",
    label="Market entry",
    description="Enter at the next bar's open (no waiting for retrace).",
    params=[],
))
def _entry_market(df, i, p, direction):
    # Use the current close as entry proxy. Simulator fills when price touches.
    return float(df["C"].values[i])


@register(NodeSpec(
    type="entry.pullback_ema",
    category="entry",
    label="Pullback to EMA",
    description="Place a limit order at the current EMA — wait for price to retrace.",
    params=[
        {"key": "period", "label": "EMA period", "type": "int", "default": 20, "min": 2, "max": 200},
    ],
))
def _entry_pullback_ema(df, i, p, direction):
    cache = _cache(df)
    key   = f"ema{p['period']}"
    if key not in cache: cache[key] = _ema(df["C"].values, int(p["period"]))
    return float(cache[key][i])


# ═══════════════════════════════════════════════════════════════════════════
# RISK (initial stop-loss)
# ═══════════════════════════════════════════════════════════════════════════

@register(NodeSpec(
    type="risk.fixed_pips",
    category="risk",
    label="Fixed pips",
    description="SL is a fixed pip distance from entry.",
    params=[
        {"key": "pips", "label": "SL distance (pips)", "type": "float", "default": 15, "min": 1, "max": 500},
    ],
))
def _risk_fixed(df, i, p, direction, entry):
    pip = p.get("pip", 0.1)
    d   = p["pips"] * pip
    return entry - d if direction == "Bull" else entry + d


@register(NodeSpec(
    type="risk.atr_mult",
    category="risk",
    label="ATR multiple",
    description="SL is ATR × multiplier away from entry. Adapts to volatility.",
    params=[
        {"key": "period", "label": "ATR period", "type": "int",   "default": 14,  "min": 2,  "max": 50},
        {"key": "mult",   "label": "ATR mult",   "type": "float", "default": 1.5, "min": 0.5, "max": 5.0},
    ],
))
def _risk_atr(df, i, p, direction, entry):
    cache = _cache(df)
    key   = f"atr{p['period']}"
    if key not in cache: cache[key] = _atr(df, int(p["period"]))
    d = cache[key][i] * float(p["mult"])
    return entry - d if direction == "Bull" else entry + d


@register(NodeSpec(
    type="risk.below_structure",
    category="risk",
    label="Below recent swing",
    description="SL is just beyond the most recent swing low (long) or high (short) within lookback bars.",
    params=[
        {"key": "lookback", "label": "Lookback bars",   "type": "int",   "default": 10, "min": 3,  "max": 100},
        {"key": "buf_pips", "label": "Buffer (pips)",   "type": "float", "default": 2,  "min": 0,  "max": 50},
    ],
))
def _risk_structure(df, i, p, direction, entry):
    pip = p.get("pip", 0.1)
    lb  = int(p["lookback"])
    buf = float(p["buf_pips"]) * pip
    lo, j0 = df["L"].values, max(0, i - lb)
    hi      = df["H"].values
    if direction == "Bull":
        return float(lo[j0:i+1].min()) - buf
    return float(hi[j0:i+1].max()) + buf
