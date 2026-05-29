"""
Expanded node library — registers ~25 additional nodes covering the most
common indicators, filters, signals, sizing schemes, risk overlays, and
exit styles. Imported by builder_v2.__init__ for side-effect registration.

Each node follows the v2 contract from nodes.py:
    prepare(df, ctx, params)              — once before bar loop
    eval(df, i, ctx, inputs, params)      — per-bar
"""
from __future__ import annotations
from typing import Any, Dict, Tuple
import numpy as np
import pandas as pd

from .types import PortType, Insight, PortfolioTarget, AdjustedTarget, OrderIntent
from .nodes import NodeSpec, NODE_LIBRARY, _register, _ema, _atr


# ─── Indicator helpers (extras) ────────────────────────────────────────────
def _rsi(arr: np.ndarray, period: int) -> np.ndarray:
    delta = np.diff(arr, prepend=arr[0])
    gain  = np.where(delta > 0, delta, 0.0)
    loss  = np.where(delta < 0, -delta, 0.0)
    avg_g = pd.Series(gain).ewm(alpha=1/period, adjust=False).mean().values
    avg_l = pd.Series(loss).ewm(alpha=1/period, adjust=False).mean().values
    rs    = np.where(avg_l == 0, 0, avg_g / np.maximum(avg_l, 1e-9))
    return 100 - 100 / (1 + rs)


def _bbands(arr: np.ndarray, period: int, mult: float):
    s = pd.Series(arr)
    mid   = s.rolling(period, min_periods=1).mean().to_numpy(copy=True)
    sd    = s.rolling(period, min_periods=1).std(ddof=0).fillna(0).to_numpy(copy=True)
    upper = mid + mult * sd
    lower = mid - mult * sd
    return upper, mid, lower


def _stoch(df: pd.DataFrame, k_period: int, d_period: int):
    H = pd.Series(df["H"].values).rolling(k_period, min_periods=1).max()
    L = pd.Series(df["L"].values).rolling(k_period, min_periods=1).min()
    C = pd.Series(df["C"].values)
    k_raw = 100 * (C - L) / (H - L).replace(0, 1e-9)
    k = k_raw.to_numpy(copy=True)
    d = k_raw.rolling(d_period, min_periods=1).mean().to_numpy(copy=True)
    return k, d


def _macd(arr: np.ndarray, fast: int, slow: int, signal: int):
    macd_line = _ema(arr, fast) - _ema(arr, slow)
    sig_line  = _ema(macd_line, signal)
    return macd_line, sig_line, macd_line - sig_line


def _adx(df: pd.DataFrame, period: int) -> np.ndarray:
    H, L, C = df["H"].values, df["L"].values, df["C"].values
    up   = H - np.concatenate(([H[0]], H[:-1]))
    down = np.concatenate(([L[0]], L[:-1])) - L
    plus_dm  = np.where((up > down)  & (up > 0),    up, 0.0)
    minus_dm = np.where((down > up)  & (down > 0), down, 0.0)
    atr  = _atr(df, period)
    plus_di  = 100 * pd.Series(plus_dm).ewm(alpha=1/period, adjust=False).mean().values  / np.maximum(atr, 1e-9)
    minus_di = 100 * pd.Series(minus_dm).ewm(alpha=1/period, adjust=False).mean().values / np.maximum(atr, 1e-9)
    dx = 100 * np.abs(plus_di - minus_di) / np.maximum(plus_di + minus_di, 1e-9)
    return pd.Series(dx).ewm(alpha=1/period, adjust=False).mean().values


def _vwap(df: pd.DataFrame) -> np.ndarray:
    tp  = (df["H"].values + df["L"].values + df["C"].values) / 3.0
    vol = df.get("V")
    if vol is None:
        v = np.ones_like(tp)
    else:
        v = vol.values
    cum_pv  = np.cumsum(tp * v)
    cum_v   = np.cumsum(v)
    return cum_pv / np.maximum(cum_v, 1e-9)


def _swing_rolling(arr: np.ndarray, period: int, is_high: bool) -> np.ndarray:
    s = pd.Series(arr).shift(1)  # exclude current bar so signals can compare
    out = (s.rolling(period, min_periods=1).max() if is_high
           else s.rolling(period, min_periods=1).min()).to_numpy(copy=True)
    out[0] = arr[0]
    return out


# ════════════════════════════════════════════════════════════════════════════
# INDICATORS (extras)
# ════════════════════════════════════════════════════════════════════════════

# price — exposes raw price as a wireable number (close/open/high/low pick)
def _price_prepare(df, ctx, p):
    src = p.get("source", "close")
    key = f"price_{src}"
    if key not in ctx.cache:
        ctx.cache[key] = df[{"close":"C","open":"O","high":"H","low":"L"}[src]].values.astype(float)

def _price_eval(df, i, ctx, inputs, p):
    return {"value": float(ctx.cache[f"price_{p.get('source','close')}"][i])}

_register(NodeSpec(
    type="indicator.price",
    lane="indicator",
    label="Price",
    description="Raw price as a wire. Use to feed crossover / threshold alphas.",
    outputs=[("value", PortType.NUMBER)],
    params=[{"key": "source", "label": "Source", "type": "select",
             "default": "close", "options": ["close", "open", "high", "low"]}],
))((_price_prepare, _price_eval))


# RSI
def _rsi_prepare(df, ctx, p):
    key = f"rsi_{p['period']}"
    if key not in ctx.cache:
        ctx.cache[key] = _rsi(df["C"].values, int(p["period"]))
    ctx.warmup_bars = max(ctx.warmup_bars, int(p["period"]))

def _rsi_eval(df, i, ctx, inputs, p):
    return {"value": float(ctx.cache[f"rsi_{p['period']}"][i])}

_register(NodeSpec(
    type="indicator.rsi",
    lane="indicator",
    label="RSI",
    description="Relative Strength Index — 0–100 oscillator.",
    outputs=[("value", PortType.NUMBER)],
    params=[{"key": "period", "label": "Period", "type": "int", "default": 14, "min": 2, "max": 50}],
))((_rsi_prepare, _rsi_eval))


# MACD
def _macd_prepare(df, ctx, p):
    key = f"macd_{p['fast']}_{p['slow']}_{p['signal']}"
    if key not in ctx.cache:
        m, s, h = _macd(df["C"].values, int(p["fast"]), int(p["slow"]), int(p["signal"]))
        ctx.cache[key + "_m"] = m
        ctx.cache[key + "_s"] = s
        ctx.cache[key + "_h"] = h
    ctx.warmup_bars = max(ctx.warmup_bars, int(p["slow"]) + int(p["signal"]))

def _macd_eval(df, i, ctx, inputs, p):
    k = f"macd_{p['fast']}_{p['slow']}_{p['signal']}"
    return {"macd":      float(ctx.cache[k + "_m"][i]),
            "signal":    float(ctx.cache[k + "_s"][i]),
            "histogram": float(ctx.cache[k + "_h"][i])}

_register(NodeSpec(
    type="indicator.macd",
    lane="indicator",
    label="MACD",
    description="Moving Average Convergence/Divergence — trend + momentum, 3 outputs.",
    outputs=[("macd", PortType.NUMBER), ("signal", PortType.NUMBER), ("histogram", PortType.NUMBER)],
    params=[
        {"key": "fast",   "label": "Fast EMA",   "type": "int", "default": 12, "min": 2,  "max": 50},
        {"key": "slow",   "label": "Slow EMA",   "type": "int", "default": 26, "min": 5,  "max": 100},
        {"key": "signal", "label": "Signal EMA", "type": "int", "default": 9,  "min": 2,  "max": 30},
    ],
))((_macd_prepare, _macd_eval))


# Bollinger Bands
def _bb_prepare(df, ctx, p):
    key = f"bb_{p['period']}_{p['mult']}"
    if key + "_u" not in ctx.cache:
        u, m, l = _bbands(df["C"].values, int(p["period"]), float(p["mult"]))
        ctx.cache[key + "_u"], ctx.cache[key + "_m"], ctx.cache[key + "_l"] = u, m, l
    ctx.warmup_bars = max(ctx.warmup_bars, int(p["period"]))

def _bb_eval(df, i, ctx, inputs, p):
    k = f"bb_{p['period']}_{p['mult']}"
    return {"upper":  float(ctx.cache[k + "_u"][i]),
            "middle": float(ctx.cache[k + "_m"][i]),
            "lower":  float(ctx.cache[k + "_l"][i])}

_register(NodeSpec(
    type="indicator.bollinger",
    lane="indicator",
    label="Bollinger Bands",
    description="Volatility bands around a moving average. Wire upper/lower into Channel-break.",
    outputs=[("upper", PortType.NUMBER), ("middle", PortType.NUMBER), ("lower", PortType.NUMBER)],
    params=[
        {"key": "period", "label": "Period",    "type": "int",   "default": 20, "min": 2,   "max": 200},
        {"key": "mult",   "label": "Std-dev x", "type": "float", "default": 2.0, "min": 0.5, "max": 5.0, "step": 0.1},
    ],
))((_bb_prepare, _bb_eval))


# ADX
def _adx_prepare(df, ctx, p):
    key = f"adx_{p['period']}"
    if key not in ctx.cache:
        ctx.cache[key] = _adx(df, int(p["period"]))
    ctx.warmup_bars = max(ctx.warmup_bars, int(p["period"]) * 2)

def _adx_eval(df, i, ctx, inputs, p):
    return {"value": float(ctx.cache[f"adx_{p['period']}"][i])}

_register(NodeSpec(
    type="indicator.adx",
    lane="indicator",
    label="ADX",
    description="Trend strength (0–100). Wire into Threshold filter to gate sideways markets.",
    outputs=[("value", PortType.NUMBER)],
    params=[{"key": "period", "label": "Period", "type": "int", "default": 14, "min": 2, "max": 50}],
))((_adx_prepare, _adx_eval))


# Stochastic
def _stoch_prepare(df, ctx, p):
    key = f"stoch_{p['k_period']}_{p['d_period']}"
    if key + "_k" not in ctx.cache:
        k, d = _stoch(df, int(p["k_period"]), int(p["d_period"]))
        ctx.cache[key + "_k"], ctx.cache[key + "_d"] = k, d
    ctx.warmup_bars = max(ctx.warmup_bars, int(p["k_period"]))

def _stoch_eval(df, i, ctx, inputs, p):
    k = f"stoch_{p['k_period']}_{p['d_period']}"
    return {"k": float(ctx.cache[k + "_k"][i]),
            "d": float(ctx.cache[k + "_d"][i])}

_register(NodeSpec(
    type="indicator.stochastic",
    lane="indicator",
    label="Stochastic",
    description="%K / %D oscillator. Wire %K into Threshold for overbought/oversold.",
    outputs=[("k", PortType.NUMBER), ("d", PortType.NUMBER)],
    params=[
        {"key": "k_period", "label": "%K period", "type": "int", "default": 14, "min": 2, "max": 50},
        {"key": "d_period", "label": "%D smooth", "type": "int", "default": 3,  "min": 1, "max": 20},
    ],
))((_stoch_prepare, _stoch_eval))


# VWAP
def _vwap_prepare(df, ctx, p):
    if "vwap" not in ctx.cache:
        ctx.cache["vwap"] = _vwap(df)

def _vwap_eval(df, i, ctx, inputs, p):
    return {"value": float(ctx.cache["vwap"][i])}

_register(NodeSpec(
    type="indicator.vwap",
    lane="indicator",
    label="VWAP",
    description="Volume-weighted average price (1.0 fallback if no volume).",
    outputs=[("value", PortType.NUMBER)],
    params=[],
))((_vwap_prepare, _vwap_eval))


# Swing high / low (rolling N-bar) — exclude current bar
def _swing_high_prepare(df, ctx, p):
    key = f"swing_h_{p['period']}"
    if key not in ctx.cache:
        ctx.cache[key] = _swing_rolling(df["H"].values, int(p["period"]), True)
    ctx.warmup_bars = max(ctx.warmup_bars, int(p["period"]))

def _swing_high_eval(df, i, ctx, inputs, p):
    return {"value": float(ctx.cache[f"swing_h_{p['period']}"][i])}

_register(NodeSpec(
    type="indicator.swing_high",
    lane="indicator",
    label="Swing high (rolling)",
    description="Highest high in the last N bars (excluding current). Wire into structural risk / range-break alpha.",
    outputs=[("value", PortType.NUMBER)],
    params=[{"key": "period", "label": "Lookback bars", "type": "int", "default": 20, "min": 3, "max": 200}],
))((_swing_high_prepare, _swing_high_eval))


def _swing_low_prepare(df, ctx, p):
    key = f"swing_l_{p['period']}"
    if key not in ctx.cache:
        ctx.cache[key] = _swing_rolling(df["L"].values, int(p["period"]), False)
    ctx.warmup_bars = max(ctx.warmup_bars, int(p["period"]))

def _swing_low_eval(df, i, ctx, inputs, p):
    return {"value": float(ctx.cache[f"swing_l_{p['period']}"][i])}

_register(NodeSpec(
    type="indicator.swing_low",
    lane="indicator",
    label="Swing low (rolling)",
    description="Lowest low in the last N bars (excluding current). Pair with Swing high for range setups.",
    outputs=[("value", PortType.NUMBER)],
    params=[{"key": "period", "label": "Lookback bars", "type": "int", "default": 20, "min": 3, "max": 200}],
))((_swing_low_prepare, _swing_low_eval))


# SMA
def _sma_prepare(df, ctx, p):
    key = f"sma_{p['period']}"
    if key not in ctx.cache:
        ctx.cache[key] = pd.Series(df["C"].values).rolling(int(p["period"]), min_periods=1).mean().to_numpy(copy=True)
    ctx.warmup_bars = max(ctx.warmup_bars, int(p["period"]))

def _sma_eval(df, i, ctx, inputs, p):
    return {"value": float(ctx.cache[f"sma_{p['period']}"][i])}

_register(NodeSpec(
    type="indicator.sma",
    lane="indicator",
    label="SMA",
    description="Simple moving average — equal-weighted, classic.",
    outputs=[("value", PortType.NUMBER)],
    params=[{"key": "period", "label": "Period", "type": "int", "default": 20, "min": 2, "max": 400}],
))((_sma_prepare, _sma_eval))


# SuperTrend
def _supertrend(df, period, mult):
    H, L, C = df["H"].values, df["L"].values, df["C"].values
    atr = _atr(df, period)
    hl2 = (H + L) / 2.0
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    out = np.zeros_like(C)
    direction = np.ones_like(C)        # 1 = uptrend, -1 = downtrend
    out[0] = lower[0]
    for i in range(1, len(C)):
        if C[i] > upper[i-1]:
            direction[i] = 1
        elif C[i] < lower[i-1]:
            direction[i] = -1
        else:
            direction[i] = direction[i-1]
            if direction[i] == 1  and lower[i] < lower[i-1]: lower[i] = lower[i-1]
            if direction[i] == -1 and upper[i] > upper[i-1]: upper[i] = upper[i-1]
        out[i] = lower[i] if direction[i] == 1 else upper[i]
    return out, direction

def _st_prepare(df, ctx, p):
    key = f"st_{p['period']}_{p['mult']}"
    if key + "_v" not in ctx.cache:
        line, dirn = _supertrend(df, int(p["period"]), float(p["mult"]))
        ctx.cache[key + "_v"], ctx.cache[key + "_d"] = line, dirn
    ctx.warmup_bars = max(ctx.warmup_bars, int(p["period"]))

def _st_eval(df, i, ctx, inputs, p):
    k = f"st_{p['period']}_{p['mult']}"
    return {"line": float(ctx.cache[k + "_v"][i]), "direction": float(ctx.cache[k + "_d"][i])}

_register(NodeSpec(
    type="indicator.supertrend",
    lane="indicator",
    label="SuperTrend",
    description="ATR-based trend line. Direction flips on regime change.",
    outputs=[("line", PortType.NUMBER), ("direction", PortType.NUMBER)],
    params=[
        {"key": "period", "label": "ATR period", "type": "int",   "default": 10,  "min": 3,   "max": 50},
        {"key": "mult",   "label": "Multiplier", "type": "float", "default": 3.0, "min": 1.0, "max": 6.0, "step": 0.1},
    ],
))((_st_prepare, _st_eval))


# CCI
def _cci_prepare(df, ctx, p):
    key = f"cci_{p['period']}"
    if key not in ctx.cache:
        tp = (df["H"].values + df["L"].values + df["C"].values) / 3.0
        s  = pd.Series(tp)
        sma = s.rolling(int(p["period"]), min_periods=1).mean()
        mad = s.rolling(int(p["period"]), min_periods=1).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
        ctx.cache[key] = ((s - sma) / (0.015 * mad.replace(0, 1e-9))).to_numpy(copy=True)
    ctx.warmup_bars = max(ctx.warmup_bars, int(p["period"]))

def _cci_eval(df, i, ctx, inputs, p):
    return {"value": float(ctx.cache[f"cci_{p['period']}"][i])}

_register(NodeSpec(
    type="indicator.cci",
    lane="indicator",
    label="CCI",
    description="Commodity Channel Index — typically ±100. Cross thresholds for momentum signals.",
    outputs=[("value", PortType.NUMBER)],
    params=[{"key": "period", "label": "Period", "type": "int", "default": 20, "min": 5, "max": 100}],
))((_cci_prepare, _cci_eval))


# Williams %R
def _wpr_prepare(df, ctx, p):
    key = f"wpr_{p['period']}"
    if key not in ctx.cache:
        H = pd.Series(df["H"].values).rolling(int(p["period"]), min_periods=1).max()
        L = pd.Series(df["L"].values).rolling(int(p["period"]), min_periods=1).min()
        C = pd.Series(df["C"].values)
        ctx.cache[key] = (-100 * (H - C) / (H - L).replace(0, 1e-9)).to_numpy(copy=True)
    ctx.warmup_bars = max(ctx.warmup_bars, int(p["period"]))

def _wpr_eval(df, i, ctx, inputs, p):
    return {"value": float(ctx.cache[f"wpr_{p['period']}"][i])}

_register(NodeSpec(
    type="indicator.williams_r",
    lane="indicator",
    label="Williams %R",
    description="Inverted stochastic. Values from -100 (oversold) to 0 (overbought).",
    outputs=[("value", PortType.NUMBER)],
    params=[{"key": "period", "label": "Period", "type": "int", "default": 14, "min": 2, "max": 100}],
))((_wpr_prepare, _wpr_eval))


# ROC
def _roc_prepare(df, ctx, p):
    key = f"roc_{p['period']}"
    if key not in ctx.cache:
        C = pd.Series(df["C"].values)
        ctx.cache[key] = (100 * (C - C.shift(int(p["period"]))) / C.shift(int(p["period"])).replace(0, 1e-9)).fillna(0).to_numpy(copy=True)
    ctx.warmup_bars = max(ctx.warmup_bars, int(p["period"]))

def _roc_eval(df, i, ctx, inputs, p):
    return {"value": float(ctx.cache[f"roc_{p['period']}"][i])}

_register(NodeSpec(
    type="indicator.roc",
    lane="indicator",
    label="Rate of Change",
    description="Percent change over N bars. Pure momentum oscillator.",
    outputs=[("value", PortType.NUMBER)],
    params=[{"key": "period", "label": "Period", "type": "int", "default": 10, "min": 2, "max": 100}],
))((_roc_prepare, _roc_eval))


# Order Block — the SMC POI for limit entries
# For a Bull setup: the most recent BEARISH candle within scan_min..scan_max bars back.
# For a Bear setup: the most recent BULLISH candle in the same window.
# The "direction" param picks which one you want exposed as wires.
def _ob_prepare(df, ctx, p):
    direction = p.get("direction", "long")
    smin, smax = int(p["scan_min"]), int(p["scan_max"])
    key = f"ob_{direction}_{smin}_{smax}"
    if key + "_h" in ctx.cache: return
    O, C = df["O"].values, df["C"].values
    H, L = df["H"].values, df["L"].values
    n = len(df)
    ob_h = np.zeros(n); ob_l = np.zeros(n); ob_m = np.zeros(n)
    # Look at every bar; scan backwards for matching candle color
    for i in range(n):
        lo = max(0, i - smax)
        hi = i - smin if i - smin >= 0 else 0
        found = None
        for j in range(hi, lo - 1, -1):
            if direction == "long":
                if C[j] < O[j]:   # bearish candle = Bull OB
                    found = j; break
            else:
                if C[j] > O[j]:   # bullish candle = Bear OB
                    found = j; break
        if found is not None:
            ob_h[i] = H[found]; ob_l[i] = L[found]
            ob_m[i] = (O[found] + C[found]) / 2.0
        elif i > 0:
            # Carry forward if no fresh OB this bar
            ob_h[i] = ob_h[i-1]; ob_l[i] = ob_l[i-1]; ob_m[i] = ob_m[i-1]
    ctx.cache[key + "_h"] = ob_h
    ctx.cache[key + "_l"] = ob_l
    ctx.cache[key + "_m"] = ob_m
    ctx.warmup_bars = max(ctx.warmup_bars, smax)

def _ob_eval(df, i, ctx, inputs, p):
    direction = p.get("direction", "long")
    smin, smax = int(p["scan_min"]), int(p["scan_max"])
    k = f"ob_{direction}_{smin}_{smax}"
    hi = float(ctx.cache[k + "_h"][i])
    lo = float(ctx.cache[k + "_l"][i])
    mid = float(ctx.cache[k + "_m"][i])
    # entry_ratio: 0.0 = low (deepest discount), 0.5 = mid (default), 1.0 = high (top of OB)
    # For a Bull OB you usually want LOWER ratios (better fill, bigger MFE before SL).
    # For a Bear OB you usually want HIGHER ratios (sell into premium).
    ratio = max(0.0, min(1.0, float(p.get("entry_ratio", 0.5))))
    entry_px = lo + ratio * (hi - lo)
    return {
        "high":     hi,
        "low":      lo,
        "midpoint": mid,
        "entry":    entry_px,
    }

def _ob_zone(a, b, h, l, direction):
    return {
        "kind": "zone",
        "label": f"Order Block ({direction})",
        "color_hint": "bull" if direction == "long" else "bear",
        "from_idx": int(a), "to_idx": int(b),
        "price_hi": float(h), "price_lo": float(l),
    }

def _ob_artifacts(df, ctx, p):
    """Compress the per-bar OB high/low cache into distinct zone rectangles —
    one box per order block, spanning the bars where it was the active OB."""
    direction = p.get("direction", "long")
    smin, smax = int(p["scan_min"]), int(p["scan_max"])
    k = f"ob_{direction}_{smin}_{smax}"
    hh = ctx.cache.get(k + "_h"); ll = ctx.cache.get(k + "_l")
    if hh is None or ll is None:
        return []
    arts = []
    n = len(hh)
    start = None; cur_h = cur_l = None
    for i in range(n):
        h = float(hh[i]); l = float(ll[i])
        if h <= 0 and l <= 0:                      # no OB established yet
            if start is not None:
                arts.append(_ob_zone(start, i - 1, cur_h, cur_l, direction)); start = None
            continue
        if start is None:
            start, cur_h, cur_l = i, h, l
        elif h != cur_h or l != cur_l:             # a fresh OB replaced the old one
            arts.append(_ob_zone(start, i - 1, cur_h, cur_l, direction))
            start, cur_h, cur_l = i, h, l
    if start is not None:
        arts.append(_ob_zone(start, n - 1, cur_h, cur_l, direction))
    return arts[-40:]                              # cap to keep the chart readable

_register(NodeSpec(
    type="indicator.order_block",
    lane="indicator",
    label="Order Block (SMC)",
    description="The last opposite-color candle. Outputs high / low / midpoint as fixed references, plus a configurable 'entry' (your choice of where in the OB to fill). For Bull OB: low=0 = deepest discount; high=1 = top of zone.",
    outputs=[
        ("high",     PortType.NUMBER),
        ("low",      PortType.NUMBER),
        ("midpoint", PortType.NUMBER),
        ("entry",    PortType.NUMBER),
    ],
    params=[
        {"key": "direction", "label": "OB type",                  "type": "select",
         "default": "long",  "options": ["long", "short"]},
        {"key": "scan_min",  "label": "Scan from (bars back)",    "type": "int",   "default":  3, "min": 1, "max": 50},
        {"key": "scan_max",  "label": "Scan to (bars back)",      "type": "int",   "default": 15, "min": 5, "max": 200},
        {"key": "entry_ratio", "label": "Entry level (0=low, 0.5=mid, 1=high)",
         "type": "float", "default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05},
    ],
))((_ob_prepare, _ob_eval, _ob_artifacts))


# Ichimoku Kinko Hyo — the 5-line Japanese system
def _ichimoku_prepare(df, ctx, p):
    key = f"ichi_{p['tenkan_period']}_{p['kijun_period']}_{p['senkou_b_period']}"
    if key + "_t" in ctx.cache: return
    H, L = df["H"].values, df["L"].values
    def mid_of(period):
        h = pd.Series(H).rolling(int(period), min_periods=1).max()
        l = pd.Series(L).rolling(int(period), min_periods=1).min()
        return ((h + l) / 2.0).to_numpy(copy=True)
    tenkan = mid_of(p["tenkan_period"])
    kijun  = mid_of(p["kijun_period"])
    senkou_a = (tenkan + kijun) / 2.0
    senkou_b = mid_of(p["senkou_b_period"])
    ctx.cache[key + "_t"] = tenkan
    ctx.cache[key + "_k"] = kijun
    ctx.cache[key + "_a"] = senkou_a
    ctx.cache[key + "_b"] = senkou_b
    ctx.warmup_bars = max(ctx.warmup_bars, int(p["senkou_b_period"]))

def _ichimoku_eval(df, i, ctx, inputs, p):
    k = f"ichi_{p['tenkan_period']}_{p['kijun_period']}_{p['senkou_b_period']}"
    return {
        "tenkan":   float(ctx.cache[k + "_t"][i]),
        "kijun":    float(ctx.cache[k + "_k"][i]),
        "senkou_a": float(ctx.cache[k + "_a"][i]),
        "senkou_b": float(ctx.cache[k + "_b"][i]),
    }

_register(NodeSpec(
    type="indicator.ichimoku",
    lane="indicator",
    label="Ichimoku Kinko Hyo",
    description="5-line Japanese system. Outputs Tenkan, Kijun, Senkou A, Senkou B (Kumo cloud). Defaults 9 / 26 / 52.",
    outputs=[
        ("tenkan",   PortType.NUMBER),
        ("kijun",    PortType.NUMBER),
        ("senkou_a", PortType.NUMBER),
        ("senkou_b", PortType.NUMBER),
    ],
    params=[
        {"key": "tenkan_period",   "label": "Tenkan period (conversion)", "type": "int", "default":  9, "min": 5,  "max": 30},
        {"key": "kijun_period",    "label": "Kijun period (base)",        "type": "int", "default": 26, "min": 10, "max": 80},
        {"key": "senkou_b_period", "label": "Senkou B period",            "type": "int", "default": 52, "min": 20, "max": 200},
    ],
))((_ichimoku_prepare, _ichimoku_eval))


# ════════════════════════════════════════════════════════════════════════════
# ALPHA (extras)
# ════════════════════════════════════════════════════════════════════════════

@_register(NodeSpec(
    type="alpha.threshold",
    lane="alpha",
    label="Threshold cross",
    description="Long when wired value crosses above 'long_level'; Short when crosses below 'short_level'.",
    inputs=[("value", PortType.NUMBER)],
    outputs=[("insight", PortType.INSIGHT)],
    params=[
        {"key": "long_level",  "label": "Long cross level",  "type": "float", "default": 30, "min": -1000, "max": 1000},
        {"key": "short_level", "label": "Short cross level", "type": "float", "default": 70, "min": -1000, "max": 1000},
        {"key": "direction",   "label": "Direction",         "type": "select",
         "default": "both",     "options": ["long", "short", "both"]},
    ],
))
def _alpha_threshold(df, i, ctx, inputs, p):
    nid_key = f"_thresh_prev_{ctx.state.get('__current_node__','')}"
    prev = ctx.state.get(nid_key)
    v = inputs["value"]
    ctx.state[nid_key] = v
    if prev is None: return {"insight": None}
    d = p.get("direction", "both")
    if d in ("long",  "both") and prev <= p["long_level"]  and v >  p["long_level"]:   return {"insight": Insight(direction="Bull", bar_idx=i)}
    if d in ("short", "both") and prev >= p["short_level"] and v <  p["short_level"]:  return {"insight": Insight(direction="Bear", bar_idx=i)}
    return {"insight": None}


@_register(NodeSpec(
    type="alpha.engulfing",
    lane="alpha",
    label="Engulfing candle",
    description="Bullish or bearish engulfing pattern (current body covers prior body).",
    outputs=[("insight", PortType.INSIGHT)],
    params=[
        {"key": "direction", "label": "Direction", "type": "select",
         "default": "both", "options": ["long", "short", "both"]},
    ],
))
def _alpha_engulfing(df, i, ctx, inputs, p):
    if i < 1: return {"insight": None}
    O, C = df["O"].values, df["C"].values
    o0, c0 = O[i-1], C[i-1]
    o1, c1 = O[i],   C[i]
    d = p.get("direction", "both")
    if d in ("long", "both")  and c0 < o0 and c1 > o1 and c1 >= o0 and o1 <= c0:
        return {"insight": Insight(direction="Bull", bar_idx=i)}
    if d in ("short", "both") and c0 > o0 and c1 < o1 and c1 <= o0 and o1 >= c0:
        return {"insight": Insight(direction="Bear", bar_idx=i)}
    return {"insight": None}


@_register(NodeSpec(
    type="alpha.liquidity_sweep",
    lane="alpha",
    label="Liquidity sweep",
    description="The real SMC signal: 2+ equal highs/lows are formed, then an impulse candle wicks beyond them but closes BACK inside (failed breakout = liquidity grab).",
    outputs=[("insight", PortType.INSIGHT)],
    params=[
        {"key": "lookback",      "label": "Equal-level lookback (bars)", "type": "int",   "default": 30,  "min": 5,   "max": 200},
        {"key": "count",         "label": "Min equal levels",            "type": "int",   "default": 2,   "min": 2,   "max": 5},
        {"key": "tolerance_pips","label": "Equal tolerance (pips)",      "type": "float", "default": 3,   "min": 0.5, "max": 20},
        {"key": "min_pierce_pips","label": "Min sweep depth (pips)",     "type": "float", "default": 1.0, "min": 0,   "max": 50},
        {"key": "direction",     "label": "Direction",                   "type": "select",
         "default": "both",  "options": ["long", "short", "both"]},
    ],
))
def _alpha_liq_sweep(df, i, ctx, inputs, p):
    lb = int(p["lookback"])
    if i < lb + 2: return {"insight": None}
    pip = ctx.pip
    tol = float(p["tolerance_pips"]) * pip
    min_pierce = float(p["min_pierce_pips"]) * pip
    d = p.get("direction", "both")

    H = df["H"].values; L = df["L"].values; C = df["C"].values
    # Window EXCLUDES the current bar — we need the level to exist BEFORE the sweep
    win_H = H[i-lb:i]
    win_L = L[i-lb:i]

    # ── Bear sweep: equal highs above us, current bar wicks above but closes below
    if d in ("short", "both"):
        top = win_H.max()
        eq_count = int((np.abs(win_H - top) <= tol).sum())
        if eq_count >= int(p["count"]):
            # Sweep test on current bar
            if H[i] >= top + min_pierce and C[i] < top - tol:
                return {"insight": Insight(direction="Bear", bar_idx=i,
                                           meta={"sweep_level": float(top), "type": "equal_highs"})}

    # ── Bull sweep: equal lows below us, current bar wicks below but closes above
    if d in ("long", "both"):
        bot = win_L.min()
        eq_count = int((np.abs(win_L - bot) <= tol).sum())
        if eq_count >= int(p["count"]):
            if L[i] <= bot - min_pierce and C[i] > bot + tol:
                return {"insight": Insight(direction="Bull", bar_idx=i,
                                           meta={"sweep_level": float(bot), "type": "equal_lows"})}

    return {"insight": None}


@_register(NodeSpec(
    type="alpha.fvg",
    lane="alpha",
    label="Fair Value Gap",
    description="3-bar imbalance — gap between bar n-2 and current bar exceeds N pips.",
    outputs=[("insight", PortType.INSIGHT)],
    params=[
        {"key": "min_pips",  "label": "Min gap (pips)", "type": "float", "default": 2.0, "min": 0.5, "max": 50},
        {"key": "direction", "label": "Direction",      "type": "select",
         "default": "both",   "options": ["long", "short", "both"]},
    ],
))
def _alpha_fvg(df, i, ctx, inputs, p):
    if i < 2: return {"insight": None}
    minpx = float(p["min_pips"]) * ctx.pip
    H, L = df["H"].values, df["L"].values
    d = p.get("direction", "both")
    if d in ("long", "both")  and L[i] - H[i-2] >= minpx: return {"insight": Insight(direction="Bull", bar_idx=i)}
    if d in ("short", "both") and L[i-2] - H[i] >= minpx: return {"insight": Insight(direction="Bear", bar_idx=i)}
    return {"insight": None}


def _fvg_artifacts(df, ctx, p):
    """Each 3-bar imbalance becomes a gap rectangle, drawn forward until it's
    likely filled (~10 bars)."""
    minpx = float(p["min_pips"]) * ctx.pip
    H, L = df["H"].values, df["L"].values
    d = p.get("direction", "both")
    n = len(df); arts = []
    for i in range(2, n):
        if d in ("long", "both") and L[i] - H[i-2] >= minpx:
            arts.append({"kind": "zone", "label": "FVG (bull)", "color_hint": "bull",
                         "from_idx": i - 2, "to_idx": min(n - 1, i + 10),
                         "price_hi": float(L[i]), "price_lo": float(H[i-2])})
        elif d in ("short", "both") and L[i-2] - H[i] >= minpx:
            arts.append({"kind": "zone", "label": "FVG (bear)", "color_hint": "bear",
                         "from_idx": i - 2, "to_idx": min(n - 1, i + 10),
                         "price_hi": float(L[i-2]), "price_lo": float(H[i])})
    return arts[-60:]


def _sweep_artifacts(df, ctx, p):
    """Mark each swept liquidity level (the equal-high/low that got pierced)."""
    lb = int(p["lookback"]); pip = ctx.pip
    tol = float(p["tolerance_pips"]) * pip
    min_pierce = float(p["min_pierce_pips"]) * pip
    d = p.get("direction", "both")
    H = df["H"].values; L = df["L"].values; C = df["C"].values
    n = len(df); arts = []
    for i in range(lb + 2, n):
        win_H = H[i-lb:i]; win_L = L[i-lb:i]
        if d in ("short", "both"):
            top = win_H.max()
            if int((np.abs(win_H - top) <= tol).sum()) >= int(p["count"]) \
               and H[i] >= top + min_pierce and C[i] < top - tol:
                arts.append({"kind": "level", "label": "Liquidity swept (highs)",
                             "color_hint": "bear", "at_idx": i, "price": float(top)})
                continue
        if d in ("long", "both"):
            bot = win_L.min()
            if int((np.abs(win_L - bot) <= tol).sum()) >= int(p["count"]) \
               and L[i] <= bot - min_pierce and C[i] > bot + tol:
                arts.append({"kind": "level", "label": "Liquidity swept (lows)",
                             "color_hint": "bull", "at_idx": i, "price": float(bot)})
    return arts[-40:]


# Attach artifact emitters to the decorator-registered alpha nodes.
NODE_LIBRARY["alpha.fvg"].artifacts_fn = _fvg_artifacts
NODE_LIBRARY["alpha.liquidity_sweep"].artifacts_fn = _sweep_artifacts


@_register(NodeSpec(
    type="alpha.combine_and",
    lane="alpha",
    label="Combine (AND)",
    description="Both wired insights must fire on the same bar with the same direction.",
    inputs=[("a", PortType.INSIGHT), ("b", PortType.INSIGHT)],
    outputs=[("insight", PortType.INSIGHT)],
    params=[],
))
def _alpha_and(df, i, ctx, inputs, p):
    a, b = inputs["a"], inputs["b"]
    if a is None or b is None: return {"insight": None}
    if a.direction != b.direction: return {"insight": None}
    return {"insight": Insight(direction=a.direction, bar_idx=i,
                               confidence=min(a.confidence, b.confidence))}


@_register(NodeSpec(
    type="alpha.combine_or",
    lane="alpha",
    label="Combine (OR)",
    description="Either wired insight fires the combined output (prefers 'a' if both fire).",
    inputs=[("a", PortType.INSIGHT), ("b", PortType.INSIGHT)],
    outputs=[("insight", PortType.INSIGHT)],
    params=[],
))
def _alpha_or(df, i, ctx, inputs, p):
    a, b = inputs["a"], inputs["b"]
    if a is not None: return {"insight": a}
    if b is not None: return {"insight": b}
    return {"insight": None}


# ════════════════════════════════════════════════════════════════════════════
# FILTER lane — pass an Insight through or block it.
# ════════════════════════════════════════════════════════════════════════════

@_register(NodeSpec(
    type="filter.session",
    lane="filter",
    label="Session hours",
    description="Block insights outside this time-of-day window (server local).",
    inputs=[("insight", PortType.INSIGHT)],
    outputs=[("insight", PortType.INSIGHT)],
    params=[
        {"key": "start_hour", "label": "Start hour", "type": "int", "default": 7,  "min": 0, "max": 23},
        {"key": "end_hour",   "label": "End hour",   "type": "int", "default": 17, "min": 1, "max": 24},
    ],
))
def _filter_session(df, i, ctx, inputs, p):
    ins = inputs["insight"]
    if ins is None: return {"insight": None}
    h = int(df["time"].dt.hour.iloc[i])
    if int(p["start_hour"]) <= h < int(p["end_hour"]):
        return {"insight": ins}
    return {"insight": None}


@_register(NodeSpec(
    type="filter.threshold",
    lane="filter",
    label="Value threshold",
    description="Pass insight only if wired value is above 'min' AND below 'max'. Wire ADX, ATR, etc.",
    inputs=[("insight", PortType.INSIGHT), ("value", PortType.NUMBER)],
    outputs=[("insight", PortType.INSIGHT)],
    params=[
        {"key": "min", "label": "Min (or -inf)", "type": "float", "default": 25,    "min": -1e6, "max": 1e6},
        {"key": "max", "label": "Max (or +inf)", "type": "float", "default": 1e6,   "min": -1e6, "max": 1e6},
    ],
))
def _filter_threshold(df, i, ctx, inputs, p):
    ins = inputs["insight"]
    if ins is None: return {"insight": None}
    v = inputs["value"]
    if float(p["min"]) <= v <= float(p["max"]):
        return {"insight": ins}
    return {"insight": None}


@_register(NodeSpec(
    type="filter.cooldown",
    lane="filter",
    label="Cooldown",
    description="Block new insights for N bars after the last one passed through.",
    inputs=[("insight", PortType.INSIGHT)],
    outputs=[("insight", PortType.INSIGHT)],
    params=[{"key": "bars", "label": "Cooldown bars", "type": "int", "default": 10, "min": 1, "max": 500}],
))
def _filter_cooldown(df, i, ctx, inputs, p):
    ins = inputs["insight"]
    if ins is None: return {"insight": None}
    nid = ctx.state.get("__current_node__", "cd")
    key = f"_cd_last_{nid}"
    last = ctx.state.get(key, -10**9)
    if i - last < int(p["bars"]):
        return {"insight": None}
    ctx.state[key] = i
    return {"insight": ins}


# ════════════════════════════════════════════════════════════════════════════
# SIZING (extras)
# ════════════════════════════════════════════════════════════════════════════

@_register(NodeSpec(
    type="sizing.vol_parity",
    lane="sizing",
    label="Vol-parity target",
    description="Size so realized vol of position matches a target annualized vol — multi-asset friendly.",
    inputs=[("insight", PortType.INSIGHT), ("atr", PortType.NUMBER)],
    outputs=[("target", PortType.TARGET)],
    params=[
        {"key": "target_vol_pct", "label": "Target annual vol (%)", "type": "float",
         "default": 15.0, "min": 1, "max": 60, "step": 0.5},
        {"key": "bars_per_year",  "label": "Bars per year",         "type": "int",
         "default": 9000, "min": 250, "max": 100000, "step": 250},
    ],
))
def _sizing_vol_parity(df, i, ctx, inputs, p):
    ins = inputs["insight"]
    if ins is None: return {"target": None}
    atr   = float(inputs["atr"])
    entry = float(df["C"].values[i])
    if entry <= 0 or atr <= 0: return {"target": None}
    bars_per_year = float(p["bars_per_year"])
    realized_vol  = (atr / entry) * (bars_per_year ** 0.5)
    target_vol    = float(p["target_vol_pct"]) / 100.0
    weight        = max(0.0, min(1.0, target_vol / max(realized_vol, 1e-6)))
    return {"target": PortfolioTarget(insight=ins, qty=weight, entry_px=entry,
                                      meta={"risk_pct": weight * 0.01,
                                            "vol_parity_weight": weight,
                                            "realized_vol": realized_vol})}


# ════════════════════════════════════════════════════════════════════════════
# RISK (extras)
# ════════════════════════════════════════════════════════════════════════════

@_register(NodeSpec(
    type="risk.structure_stop",
    lane="risk",
    label="Structure stop",
    description="SL beyond the swing low (Bull) / high (Bear). Wire a Swing-high/low indicator.",
    inputs=[("target", PortType.TARGET), ("swing", PortType.NUMBER)],
    outputs=[("adjusted", PortType.ADJUSTED)],
    params=[{"key": "buf_pips", "label": "Buffer (pips)", "type": "float",
             "default": 2.0, "min": 0, "max": 50}],
))
def _risk_structure(df, i, ctx, inputs, p):
    t = inputs["target"]
    if t is None: return {"adjusted": None}
    buf = float(p["buf_pips"]) * ctx.pip
    swing = float(inputs["swing"])
    sl = swing - buf if t.insight.direction == "Bull" else swing + buf
    return {"adjusted": AdjustedTarget(target=t, sl_px=sl)}


# ════════════════════════════════════════════════════════════════════════════
# EXIT (extras)
# ════════════════════════════════════════════════════════════════════════════

@_register(NodeSpec(
    type="exit.breakeven_at_r",
    lane="exit",
    label="Break-even at R",
    description="Move SL to break-even when price reaches X×R in profit. Stacks with target/trail.",
    inputs=[("adjusted", PortType.ADJUSTED)],
    outputs=[("adjusted", PortType.ADJUSTED)],
    params=[{"key": "be_at_r", "label": "Move-to-BE at R", "type": "float",
             "default": 1.0, "min": 0.2, "max": 5.0, "step": 0.1}],
))
def _exit_breakeven(df, i, ctx, inputs, p):
    adj = inputs["adjusted"]
    if adj is None: return {"adjusted": None}
    meta = dict(adj.target.meta); meta["be_at_r"] = float(p["be_at_r"])
    adj.target.meta = meta
    return {"adjusted": adj}


@_register(NodeSpec(
    type="exit.time_exit",
    lane="exit",
    label="Time exit",
    description="Close the trade after N bars regardless of price. Stacks with other exits.",
    inputs=[("adjusted", PortType.ADJUSTED)],
    outputs=[("adjusted", PortType.ADJUSTED)],
    params=[{"key": "bars", "label": "Bars in trade", "type": "int",
             "default": 50, "min": 1, "max": 1000}],
))
def _exit_time(df, i, ctx, inputs, p):
    adj = inputs["adjusted"]
    if adj is None: return {"adjusted": None}
    meta = dict(adj.target.meta); meta["time_exit_bars"] = int(p["bars"])
    adj.target.meta = meta
    return {"adjusted": adj}


# ════════════════════════════════════════════════════════════════════════════
# EXECUTION (extras)
# ════════════════════════════════════════════════════════════════════════════

@_register(NodeSpec(
    type="execution.limit_at",
    lane="execution",
    label="Limit at price",
    description="Place a limit at a wired number (e.g., EMA value, OB midpoint).",
    inputs=[("adjusted", PortType.ADJUSTED), ("price", PortType.NUMBER)],
    outputs=[("order", PortType.ORDER)],
    params=[{"key": "expiry_bars", "label": "Expiry (bars)", "type": "int",
             "default": 20, "min": 1, "max": 500}],
))
def _exec_limit_at(df, i, ctx, inputs, p):
    adj = inputs["adjusted"]
    if adj is None: return {"order": None}
    # Override the entry price with the wired number; recompute risk + sl scaled
    new_entry = float(inputs["price"])
    direction = adj.target.insight.direction
    risk_old  = abs(adj.target.entry_px - adj.sl_px)
    new_sl    = new_entry - risk_old if direction == "Bull" else new_entry + risk_old
    adj.target.entry_px = new_entry
    adj.sl_px           = new_sl
    return {"order": OrderIntent(adjusted=adj, order_type="limit",
                                 expiry_bars=int(p["expiry_bars"]))}
