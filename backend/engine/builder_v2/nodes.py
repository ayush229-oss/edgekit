"""
v2 node library — strict 5-lane decomposition with typed I/O.

Each node declares:
    lane         "universe" | "indicator" | "alpha" | "sizing" | "risk" | "exit" | "execution"
    inputs       list of (port_name, PortType) — what the node accepts
    outputs      list of (port_name, PortType) — what the node emits
    params       user-editable ParamSpecs
    fn           the implementation

Lifecycle (driven by the engine):
    prepare(df, ctx, params)    — called ONCE before the bar loop; precompute series
    eval(df, i, ctx, inputs, params) — called per bar with already-resolved inputs

A node is "pure" w.r.t. the bar index: it may only read df[:i+1]. The engine
enforces this by passing a frozen view (see safety.py).

This v1 of the library covers Donchian + EMA-cross + the legacy templates,
which validates the architecture end-to-end.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from .types import PortType, Insight, PortfolioTarget, AdjustedTarget, OrderIntent, RunContext


Lane = str  # "universe" | "indicator" | "alpha" | "sizing" | "risk" | "exit" | "execution"


@dataclass
class NodeSpec:
    type:        str
    lane:        Lane
    label:       str
    description: str
    inputs:      List[Tuple[str, PortType]] = field(default_factory=list)
    outputs:     List[Tuple[str, PortType]] = field(default_factory=list)
    params:      List[Dict[str, Any]]       = field(default_factory=list)
    prepare_fn:  Optional[Callable] = None    # (df, ctx, params) -> None  (cache fills)
    eval_fn:     Optional[Callable] = None    # see lane-specific signatures below
    artifacts_fn: Optional[Callable] = None   # (df, ctx, params) -> List[dict]  (chart structures)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type":        self.type,
            "lane":        self.lane,
            "label":       self.label,
            "description": self.description,
            "inputs":      [{"name": n, "type": t.value} for n, t in self.inputs],
            "outputs":     [{"name": n, "type": t.value} for n, t in self.outputs],
            "params":      self.params,
        }


NODE_LIBRARY: Dict[str, NodeSpec] = {}


def _register(spec: NodeSpec):
    def deco(fns):
        # fns may be (prepare, eval), (prepare, eval, artifacts), or just eval
        if isinstance(fns, tuple):
            if len(fns) == 3:
                spec.prepare_fn, spec.eval_fn, spec.artifacts_fn = fns
            else:
                spec.prepare_fn, spec.eval_fn = fns
        else:
            spec.eval_fn = fns
        NODE_LIBRARY[spec.type] = spec
        return fns
    return deco


# ── Indicator helpers (kept inline for self-containment) ──────────────────
def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    alpha = 2.0 / (period + 1)
    out   = np.zeros_like(arr, dtype=float)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


def _atr(df: pd.DataFrame, period: int) -> np.ndarray:
    H, L, C = df["H"].values, df["L"].values, df["C"].values
    prev_c  = np.concatenate(([C[0]], C[:-1]))
    tr      = np.maximum.reduce([H - L, np.abs(H - prev_c), np.abs(L - prev_c)])
    return pd.Series(tr).ewm(alpha=1/period, adjust=False).mean().values


def _donchian(df: pd.DataFrame, period: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Upper / lower Donchian channel — rolling N-bar high/low EXCLUDING the
    current bar. Without the shift, close can never exceed upper (since
    upper IS the current bar's high) and breakouts never fire.
    """
    H, L = df["H"].values, df["L"].values
    upper = pd.Series(H).shift(1).rolling(period, min_periods=1).max().to_numpy(copy=True)
    lower = pd.Series(L).shift(1).rolling(period, min_periods=1).min().to_numpy(copy=True)
    # First bar is NaN after shift — backfill with same bar's H/L so warmup is benign.
    upper[0] = H[0]; lower[0] = L[0]
    return upper, lower


# ════════════════════════════════════════════════════════════════════════════
# UNIVERSE
# ════════════════════════════════════════════════════════════════════════════

@_register(NodeSpec(
    type="universe.single_asset",
    lane="universe",
    label="Single asset",
    description="Trade exactly one instrument. The default — switch to multi_asset for portfolios.",
    outputs=[("symbol", PortType.SYMBOL)],
    params=[
        {"key": "ticker",    "label": "Ticker",    "type": "string", "default": "XAUUSD"},
        {"key": "timeframe", "label": "Timeframe", "type": "select", "default": "M15",
         "options": ["M1","M5","M15","M30","H1","H4","D1"]},
    ],
))
def _univ_single(df, i, ctx, inputs, p):
    return {"symbol": (p["ticker"], p["timeframe"])}


# ════════════════════════════════════════════════════════════════════════════
# INDICATORS — pure compute, output series. Cached once in prepare().
# ════════════════════════════════════════════════════════════════════════════

def _ema_prepare(df, ctx, p):
    key = f"ema_{p['period']}"
    if key not in ctx.cache:
        ctx.cache[key] = _ema(df["C"].values, int(p["period"]))
    ctx.warmup_bars = max(ctx.warmup_bars, int(p["period"]))

def _ema_eval(df, i, ctx, inputs, p):
    return {"value": float(ctx.cache[f"ema_{p['period']}"][i])}

_register(NodeSpec(
    type="indicator.ema",
    lane="indicator",
    label="EMA",
    description="Exponential moving average of close.",
    outputs=[("value", PortType.NUMBER)],
    params=[{"key": "period", "label": "Period", "type": "int", "default": 20, "min": 2, "max": 400}],
))((_ema_prepare, _ema_eval))


def _atr_prepare(df, ctx, p):
    key = f"atr_{p['period']}"
    if key not in ctx.cache:
        ctx.cache[key] = _atr(df, int(p["period"]))
    ctx.warmup_bars = max(ctx.warmup_bars, int(p["period"]))

def _atr_eval(df, i, ctx, inputs, p):
    return {"value": float(ctx.cache[f"atr_{p['period']}"][i])}

_register(NodeSpec(
    type="indicator.atr",
    lane="indicator",
    label="ATR",
    description="Average True Range — volatility scalar used by sizing / risk / trailing.",
    outputs=[("value", PortType.NUMBER)],
    params=[{"key": "period", "label": "Period", "type": "int", "default": 14, "min": 2, "max": 100}],
))((_atr_prepare, _atr_eval))


def _donch_prepare(df, ctx, p):
    key_u = f"donch_u_{p['period']}"
    key_l = f"donch_l_{p['period']}"
    if key_u not in ctx.cache:
        u, l = _donchian(df, int(p["period"]))
        ctx.cache[key_u], ctx.cache[key_l] = u, l
    ctx.warmup_bars = max(ctx.warmup_bars, int(p["period"]))

def _donch_eval(df, i, ctx, inputs, p):
    return {
        "upper": float(ctx.cache[f"donch_u_{p['period']}"][i]),
        "lower": float(ctx.cache[f"donch_l_{p['period']}"][i]),
    }

_register(NodeSpec(
    type="indicator.donchian",
    lane="indicator",
    label="Donchian channel",
    description="Rolling N-bar high / low. Classic trend-following breakout band.",
    outputs=[("upper", PortType.NUMBER), ("lower", PortType.NUMBER)],
    params=[{"key": "period", "label": "Period", "type": "int", "default": 20, "min": 5, "max": 200}],
))((_donch_prepare, _donch_eval))


# ════════════════════════════════════════════════════════════════════════════
# ALPHA — consumes indicators, emits Insight (or None)
# ════════════════════════════════════════════════════════════════════════════

@_register(NodeSpec(
    type="alpha.channel_break",
    lane="alpha",
    label="Channel breakout",
    description="Long when close crosses above the upper line; Short when crosses below the lower line.",
    inputs=[("upper", PortType.NUMBER), ("lower", PortType.NUMBER)],
    outputs=[("insight", PortType.INSIGHT)],
    params=[
        {"key": "direction", "label": "Direction", "type": "select",
         "default": "both", "options": ["long", "short", "both"]},
    ],
))
def _alpha_channel(df, i, ctx, inputs, p):
    if i < 1: return {"insight": None}
    C = df["C"].values
    u  = inputs["upper"]
    l  = inputs["lower"]
    # Need previous-bar values — pull from cached series via input wires.
    # Inputs carry the CURRENT bar; we read prior bar via the source's series cache.
    # For now do a robust comparison using prev close vs prev band stored on ctx.
    prev_key = f"_alpha_channel_prev_{ctx.state.get('__current_node__','')}"
    prev = ctx.state.get(prev_key, (C[i-1], u, l))
    ctx.state[prev_key] = (C[i], u, l)
    pc, pu, pl = prev
    d = p.get("direction", "both")
    if d in ("long", "both")  and C[i] > u and pc <= pu:
        return {"insight": Insight(direction="Bull", bar_idx=i)}
    if d in ("short", "both") and C[i] < l and pc >= pl:
        return {"insight": Insight(direction="Bear", bar_idx=i)}
    return {"insight": None}


@_register(NodeSpec(
    type="alpha.crossover",
    lane="alpha",
    label="Crossover",
    description="Long when A crosses above B; Short when A crosses below B. Wire any two number sources.",
    inputs=[("a", PortType.NUMBER), ("b", PortType.NUMBER)],
    outputs=[("insight", PortType.INSIGHT)],
    params=[
        {"key": "direction", "label": "Direction", "type": "select",
         "default": "both", "options": ["long", "short", "both"]},
    ],
))
def _alpha_crossover(df, i, ctx, inputs, p):
    nid_key = f"_xover_prev_{ctx.state.get('__current_node__','')}"
    prev = ctx.state.get(nid_key)
    a, b = inputs["a"], inputs["b"]
    ctx.state[nid_key] = (a, b)
    if prev is None: return {"insight": None}
    pa, pb = prev
    d = p.get("direction", "both")
    if d in ("long", "both")  and pa <= pb and a > b: return {"insight": Insight(direction="Bull", bar_idx=i)}
    if d in ("short", "both") and pa >= pb and a < b: return {"insight": Insight(direction="Bear", bar_idx=i)}
    return {"insight": None}


# ════════════════════════════════════════════════════════════════════════════
# SIZING — consumes Insight + (optional) volatility, emits PortfolioTarget
# ════════════════════════════════════════════════════════════════════════════

@_register(NodeSpec(
    type="sizing.fixed_pct",
    lane="sizing",
    label="Fixed risk %",
    description="Risk a fixed percentage of equity per trade. Sizing falls out of (risk × equity) / SL distance.",
    inputs=[("insight", PortType.INSIGHT)],
    outputs=[("target", PortType.TARGET)],
    params=[
        {"key": "risk_pct", "label": "Risk per trade (%)", "type": "float",
         "default": 1.0, "min": 0.1, "max": 10.0, "step": 0.1},
    ],
))
def _sizing_fixed(df, i, ctx, inputs, p):
    ins = inputs["insight"]
    if ins is None: return {"target": None}
    entry = float(df["C"].values[i])
    # qty is left as a notional 1.0 — the downstream simulator already does risk_pct
    # math on the equity curve. Sizing nodes set the "intent"; risk_pct here just
    # tags the target's meta so the run-level config can pick it up.
    return {"target": PortfolioTarget(insight=ins, qty=1.0, entry_px=entry,
                                      meta={"risk_pct": float(p["risk_pct"]) / 100.0})}


@_register(NodeSpec(
    type="sizing.atr_target",
    lane="sizing",
    label="ATR-target sizing",
    description="Size so that (ATR × multiplier) movement equals the configured risk %.",
    inputs=[("insight", PortType.INSIGHT), ("atr", PortType.NUMBER)],
    outputs=[("target", PortType.TARGET)],
    params=[
        {"key": "risk_pct", "label": "Risk per trade (%)", "type": "float",
         "default": 1.0, "min": 0.1, "max": 10.0, "step": 0.1},
        {"key": "atr_mult", "label": "ATR multiplier",     "type": "float",
         "default": 2.0, "min": 0.5, "max": 6.0, "step": 0.1},
    ],
))
def _sizing_atr_target(df, i, ctx, inputs, p):
    ins = inputs["insight"]
    if ins is None: return {"target": None}
    entry = float(df["C"].values[i])
    return {"target": PortfolioTarget(insight=ins, qty=1.0, entry_px=entry,
                                      meta={"risk_pct": float(p["risk_pct"]) / 100.0,
                                            "atr_at_entry": float(inputs["atr"]),
                                            "atr_mult":    float(p["atr_mult"])})}


# ════════════════════════════════════════════════════════════════════════════
# RISK — consumes PortfolioTarget, emits AdjustedTarget (with SL set)
# ════════════════════════════════════════════════════════════════════════════

@_register(NodeSpec(
    type="risk.fixed_pips",
    lane="risk",
    label="Fixed pips SL",
    description="Initial stop a fixed pip distance from entry.",
    inputs=[("target", PortType.TARGET)],
    outputs=[("adjusted", PortType.ADJUSTED)],
    params=[{"key": "pips", "label": "SL distance (pips)", "type": "float",
             "default": 15, "min": 1, "max": 500}],
))
def _risk_fixed(df, i, ctx, inputs, p):
    t = inputs["target"]
    if t is None: return {"adjusted": None}
    d = float(p["pips"]) * ctx.pip
    sl = t.entry_px - d if t.insight.direction == "Bull" else t.entry_px + d
    return {"adjusted": AdjustedTarget(target=t, sl_px=sl)}


@_register(NodeSpec(
    type="risk.atr_stop",
    lane="risk",
    label="ATR stop",
    description="Initial stop is N × ATR away from entry.",
    inputs=[("target", PortType.TARGET), ("atr", PortType.NUMBER)],
    outputs=[("adjusted", PortType.ADJUSTED)],
    params=[{"key": "mult", "label": "ATR multiplier", "type": "float",
             "default": 2.0, "min": 0.5, "max": 6.0, "step": 0.1}],
))
def _risk_atr(df, i, ctx, inputs, p):
    t = inputs["target"]
    if t is None: return {"adjusted": None}
    d = float(inputs["atr"]) * float(p["mult"])
    sl = t.entry_px - d if t.insight.direction == "Bull" else t.entry_px + d
    return {"adjusted": AdjustedTarget(target=t, sl_px=sl)}


# ════════════════════════════════════════════════════════════════════════════
# EXIT — adds target_r + trail config to AdjustedTarget (chained over risk)
# ════════════════════════════════════════════════════════════════════════════

@_register(NodeSpec(
    type="exit.target_and_trail",
    lane="exit",
    label="Target R + trail",
    description="Reach target_r × risk → optionally partial-close + start trailing.",
    inputs=[("adjusted", PortType.ADJUSTED)],
    outputs=[("adjusted", PortType.ADJUSTED)],
    params=[
        {"key": "target_r",   "label": "Target R:R",       "type": "float", "default": 3.0, "min": 1, "max": 10, "step": 0.5},
        {"key": "close_pct",  "label": "Close at target",  "type": "float", "default": 0.5, "min": 0, "max": 1, "step": 0.05},
        {"key": "trail_mode", "label": "Trail mode",       "type": "select",
         "default": "candle", "options": ["none", "candle", "atr", "pips", "swing"]},
        {"key": "trail_buf",  "label": "Trail buffer pips","type": "float", "default": 1.0, "min": 0, "max": 20},
    ],
))
def _exit_target_trail(df, i, ctx, inputs, p):
    adj = inputs["adjusted"]
    if adj is None: return {"adjusted": None}
    adj.target_r     = float(p["target_r"])
    adj.close_pct    = float(p["close_pct"])
    adj.trail_mode   = p["trail_mode"]
    adj.trail_params = {"buf_pips": float(p["trail_buf"])}
    return {"adjusted": adj}


# ════════════════════════════════════════════════════════════════════════════
# EXECUTION — consumes AdjustedTarget, emits OrderIntent
# ════════════════════════════════════════════════════════════════════════════

@_register(NodeSpec(
    type="execution.market",
    lane="execution",
    label="Market order",
    description="Submit at next bar — limit at current close (engine fills when price touches).",
    inputs=[("adjusted", PortType.ADJUSTED)],
    outputs=[("order", PortType.ORDER)],
    params=[
        {"key": "expiry_bars", "label": "Expiry (bars)", "type": "int",
         "default": 20, "min": 1, "max": 500},
    ],
))
def _exec_market(df, i, ctx, inputs, p):
    adj = inputs["adjusted"]
    if adj is None: return {"order": None}
    return {"order": OrderIntent(adjusted=adj, order_type="limit",
                                 expiry_bars=int(p["expiry_bars"]))}
