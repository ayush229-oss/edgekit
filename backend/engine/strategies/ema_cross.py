"""
EMA Crossover — classic trend-following template.

Logic:
  Bull: fast EMA crosses ABOVE slow EMA AND close > slow EMA  → buy next-bar open
  Bear: fast EMA crosses BELOW slow EMA AND close < slow EMA  → sell next-bar open

  SL  = ATR * sl_atr_mult below/above entry
  TPs = list of (R-multiple, qty fraction) ladder

This template proves the engine architecture works for non-SMC strategies.
"""
from __future__ import annotations
from typing import List, Dict, Any
import pandas as pd

from .base import Strategy, ParamSpec
from ..core import indicators as ind


class EMACrossover(Strategy):
    name        = "EMA Crossover (Trend Follow)"
    description = ("Buy when the fast EMA crosses above the slow EMA in an uptrend "
                   "(close > slow EMA). Stop-loss anchored to ATR. Classic trend-following.")
    timeframes  = ["M15", "H1", "H4", "D1"]
    instruments = ["XAUUSD", "EURUSD", "BTCUSD", "NIFTY", "SPX"]

    param_schema = [
        ParamSpec("fast_ema",     "Fast EMA period",          "int",   9,   min=2,  max=50,  step=1,
                  description="Shorter EMA — reacts faster to price.",
                  group="Indicator"),
        ParamSpec("slow_ema",     "Slow EMA period",          "int",   21,  min=10, max=200, step=1,
                  description="Longer EMA — defines the trend.",
                  group="Indicator"),
        ParamSpec("atr_period",   "ATR period",               "int",   14,  min=5,  max=50,  step=1,
                  description="Used for stop-loss sizing.",
                  group="Risk"),
        ParamSpec("sl_atr_mult",  "SL = ATR ×",               "float", 1.5, min=0.5, max=5.0, step=0.1,
                  description="Stop-loss distance as a multiple of ATR.",
                  group="Risk"),
        ParamSpec("trend_filter", "Require trend confirmation","bool", True,
                  description="If on, only longs above slow EMA / shorts below.",
                  group="Filter"),
        ParamSpec("pip",          "Pip size",                  "float", 0.10,
                  min=0.00001, max=10.0, step=0.00001,
                  description="Auto-detected from data when uploading.",
                  group="Advanced"),
    ]

    def detect(self, df: pd.DataFrame, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        p           = self.validate_params(params)
        fast_p      = p["fast_ema"]
        slow_p      = p["slow_ema"]
        atr_p       = p["atr_period"]
        sl_mult     = p["sl_atr_mult"]
        use_filter  = bool(p["trend_filter"])
        tps_param   = params.get("tps") or [(2.0, 0.5), (3.0, 0.5)]

        if fast_p >= slow_p:
            return []                              # invalid combo

        fast = ind.ema(df["C"], fast_p)
        slow = ind.ema(df["C"], slow_p)
        a    = ind.atr(df, atr_p)

        # Cross detection — current bar vs previous bar relationship
        prev_above = fast.shift(1) > slow.shift(1)
        cur_above  = fast > slow
        bull_cross = cur_above & ~prev_above
        bear_cross = ~cur_above & prev_above

        setups: list[dict] = []
        n  = len(df)
        O  = df["O"].values
        Cv = df["C"].values

        for i in range(max(slow_p, atr_p) + 1, n - 1):
            if pd.isna(a.iloc[i]) or a.iloc[i] <= 0:
                continue
            sl_distance = a.iloc[i] * sl_mult

            if bull_cross.iloc[i]:
                if use_filter and Cv[i] <= slow.iloc[i]:
                    continue
                entry      = O[i + 1]              # next-bar open fill
                tp_prices  = [(entry + r * sl_distance, q) for r, q in tps_param]
                setups.append(dict(
                    signal_idx = i + 1,
                    direction  = "Bull",
                    entry      = entry,
                    sl         = entry - sl_distance,
                    risk       = sl_distance,
                    tps        = tp_prices,
                    liq_level  = float(slow.iloc[i]),   # used only for dedup
                    meta       = {"fast": float(fast.iloc[i]),
                                  "slow": float(slow.iloc[i]),
                                  "atr":  float(a.iloc[i])},
                ))
            elif bear_cross.iloc[i]:
                if use_filter and Cv[i] >= slow.iloc[i]:
                    continue
                entry     = O[i + 1]
                tp_prices = [(entry - r * sl_distance, q) for r, q in tps_param]
                setups.append(dict(
                    signal_idx = i + 1,
                    direction  = "Bear",
                    entry      = entry,
                    sl         = entry + sl_distance,
                    risk       = sl_distance,
                    tps        = tp_prices,
                    liq_level  = float(slow.iloc[i]),
                    meta       = {"fast": float(fast.iloc[i]),
                                  "slow": float(slow.iloc[i]),
                                  "atr":  float(a.iloc[i])},
                ))

        return setups
