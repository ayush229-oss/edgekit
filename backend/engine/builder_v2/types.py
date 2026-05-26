"""
Typed data contracts for the v2 graph engine.

The 5-lane model passes specific dataclasses between lanes, not loose dicts:

    Universe          → list[Symbol]           (which assets to scan)
    Alpha             → Insight                (direction + confidence)
    Sizing            → PortfolioTarget        (qty)
    Risk + Exit       → AdjustedTarget         (final qty + stop levels)
    Execution         → OrderIntent            (wire-format order)

Wires between nodes carry one of these PortTypes. The graph validator
rejects connections that mix incompatible types, so a "bool/direction"
output cannot be wired to a "number series" input.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional


# ── Port types — color-coded in the UI, validated in the engine ────────────
class PortType(str, Enum):
    NUMBER     = "number"       # scalar (one value per bar)
    SERIES     = "series"       # np.ndarray (full bar-history)
    DIRECTION  = "direction"    # "Bull" | "Bear" | None
    INSIGHT    = "insight"      # full Insight object
    TARGET     = "target"       # PortfolioTarget object
    ADJUSTED   = "adjusted"     # AdjustedTarget object
    ORDER      = "order"        # OrderIntent object
    SYMBOL     = "symbol"       # one tradable instrument
    CONTEXT    = "context"      # shared config (pip, commission, slippage)


# ── Universe ───────────────────────────────────────────────────────────────
@dataclass
class Symbol:
    ticker:    str                  # "XAUUSD"
    timeframe: str                  # "M15"
    pip:       float                # 0.10 for XAUUSD


# ── Alpha output: a trading signal ─────────────────────────────────────────
@dataclass
class Insight:
    direction:  Literal["Bull", "Bear"]
    bar_idx:    int                                 # the bar this insight fires on
    confidence: float = 1.0                         # 0..1, used by sizing for weighting
    meta:       Dict[str, Any] = field(default_factory=dict)


# ── Sizing output: how much, before risk overrides ─────────────────────────
@dataclass
class PortfolioTarget:
    insight:    Insight
    qty:        float                               # position units (already direction-signed)
    entry_px:   float
    meta:       Dict[str, Any] = field(default_factory=dict)


# ── Risk/Exit overlay: final SL, plus any trailing config ──────────────────
@dataclass
class AdjustedTarget:
    target:        PortfolioTarget
    sl_px:         float
    trail_mode:    Literal["none", "candle", "atr", "pips", "swing", "chandelier"] = "none"
    trail_params:  Dict[str, Any] = field(default_factory=dict)
    target_r:      Optional[float] = None
    close_pct:     float = 1.0                      # how much to close at target_r

    @property
    def risk(self) -> float:
        return abs(self.target.entry_px - self.sl_px)


# ── Execution output: a setup the simulator can consume ────────────────────
@dataclass
class OrderIntent:
    adjusted:     AdjustedTarget
    order_type:   Literal["market", "limit", "stop", "bracket"] = "limit"
    time_in_force: Literal["GTC", "DAY", "IOC"] = "GTC"
    expiry_bars:  Optional[int] = None

    def to_setup(self) -> Dict[str, Any]:
        """Render as a setup dict the existing simulator already understands."""
        adj  = self.adjusted
        tgt  = adj.target
        ins  = tgt.insight
        return {
            "signal_idx": ins.bar_idx,
            "direction":  ins.direction,
            "entry":      float(tgt.entry_px),
            "sl":         float(adj.sl_px),
            "risk":       float(adj.risk),
            "liq_level":  float(tgt.entry_px),
            "tps":        [],
            "qty":        float(tgt.qty),
            "meta":       {**ins.meta, **tgt.meta, "source": "graph_v2"},
        }


# ── Shared per-run context (the "config node" pattern from Node-RED) ───────
@dataclass
class RunContext:
    """
    Single mutable bag shared across all nodes in a single backtest run.
    Holds the precomputed indicator cache, account state, costs, and any
    stateful filter slots (cooldown, daily-loss tracker, etc.).
    """
    pip:           float = 0.10
    equity:        float = 100.0
    commission:    float = 0.0        # per trade, in account currency
    slippage_pips: float = 0.0        # symmetric, applied to entry + exit
    warmup_bars:   int   = 0          # set by max(period) across indicators

    # Indicator cache: key → np.ndarray. Pre-filled before bar loop starts.
    cache: Dict[str, Any] = field(default_factory=dict)
    # Stateful per-node slots (e.g. cooldown last-fired bar)
    state: Dict[str, Any] = field(default_factory=dict)
