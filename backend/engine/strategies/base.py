"""
Abstract base for all Edgekit strategy templates.

Each template subclasses Strategy, declares its tunable parameters via
`param_schema` (used by the form-wizard UI), and implements `detect()`
which scans an OHLCV DataFrame and returns a list of setup dicts ready
to feed into the universal simulator.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Literal, Optional
import pandas as pd


# ─── Parameter schema (drives the form wizard UI) ────────────────────────────
@dataclass
class ParamSpec:
    """One tunable parameter of a strategy."""
    key:         str
    label:       str
    type:        Literal["int", "float", "select", "bool"]
    default:     Any
    min:         Optional[float] = None
    max:         Optional[float] = None
    step:        Optional[float] = None
    options:     Optional[List[Any]] = None      # for type == "select"
    description: str = ""
    group:       str = "General"                 # for visual sectioning


# ─── Strategy base class ─────────────────────────────────────────────────────
class Strategy(ABC):
    """All strategy templates inherit from this."""

    # Class-level metadata — subclasses override
    name: str             = "Unnamed"
    description: str      = ""
    timeframes: List[str] = ["M5", "M15", "H1"]
    instruments: List[str] = ["XAUUSD"]   # informational; strategies are instrument-agnostic
    param_schema: List[ParamSpec] = []

    @classmethod
    def default_params(cls) -> Dict[str, Any]:
        return {p.key: p.default for p in cls.param_schema}

    @classmethod
    def validate_params(cls, params: Dict[str, Any]) -> Dict[str, Any]:
        """Fill missing keys with defaults; clamp numerics to declared ranges."""
        out = cls.default_params()
        for p in cls.param_schema:
            if p.key in params and params[p.key] is not None:
                v = params[p.key]
                if p.type in ("int", "float"):
                    if p.min is not None: v = max(p.min, v)
                    if p.max is not None: v = min(p.max, v)
                    v = int(v) if p.type == "int" else float(v)
                out[p.key] = v
        return out

    @abstractmethod
    def detect(self, df: pd.DataFrame, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Scan df and return a list of setup dicts. Each setup MUST include:
            signal_idx: int
            direction:  'Bull' | 'Bear'
            entry:      float
            sl:         float
            risk:       float       (|entry - sl|)
            tps:        list[(price, qty_fraction)]   sorted by R ascending
        Optional:
            liq_level:  float   (used by default dedup)
            meta:       dict    (anything else for UI display)
        """
        ...
