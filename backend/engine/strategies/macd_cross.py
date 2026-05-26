"""
MACD Crossover — momentum confirmation entry.

Logic:
  Bull: MACD line crosses ABOVE signal line, both above zero (or filter off) → buy
  Bear: MACD line crosses BELOW signal line, both below zero (or filter off) → sell

Standard 12/26/9 by default. ATR stop, R-multiple TPs.
"""
from __future__ import annotations
from typing import List, Dict, Any
import pandas as pd

from .base import Strategy, ParamSpec
from ..core import indicators as ind


class MACDCross(Strategy):
    name        = "MACD Crossover (Momentum)"
    description = ("Trade MACD line crossing its signal line. Optional zero-line filter "
                   "to avoid mean-reverting whips. Momentum follower.")
    timeframes  = ["H1", "H4", "D1"]
    instruments = ["XAUUSD", "BTCUSD", "EURUSD", "AAPL"]

    param_schema = [
        ParamSpec("fast",       "Fast EMA",        "int",   12, min=5,  max=30,  step=1, group="MACD"),
        ParamSpec("slow",       "Slow EMA",        "int",   26, min=15, max=60,  step=1, group="MACD"),
        ParamSpec("signal",     "Signal EMA",      "int",   9,  min=3,  max=20,  step=1, group="MACD"),
        ParamSpec("zero_filter","Zero-line filter","bool",  True,
                  description="If on, longs only when MACD > 0, shorts only when MACD < 0.",
                  group="Filter"),
        ParamSpec("atr_period", "ATR period",      "int",   14, min=5,  max=50,  step=1, group="Risk"),
        ParamSpec("sl_atr_mult","SL = ATR ×",      "float", 1.5, min=0.5, max=5.0, step=0.1, group="Risk"),
        ParamSpec("pip", "Pip size", "float", 0.10, min=0.00001, max=10.0, step=0.00001, group="Advanced"),
    ]

    def detect(self, df: pd.DataFrame, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        p = self.validate_params(params)
        if p["fast"] >= p["slow"]:
            return []
        m   = ind.macd(df["C"], p["fast"], p["slow"], p["signal"])
        a   = ind.atr(df, p["atr_period"])
        sl_mult = p["sl_atr_mult"]
        use_zero = bool(p["zero_filter"])
        tps_param = params.get("tps") or [(2.0, 0.5), (3.0, 0.5)]

        macd_l, sig_l = m["macd"], m["signal"]
        prev_below = macd_l.shift(1) < sig_l.shift(1)
        cur_above  = macd_l > sig_l
        bull = prev_below & cur_above
        bear = (~prev_below) & (~cur_above) & (macd_l.shift(1) > sig_l.shift(1))

        O = df["O"].values
        setups: list[dict] = []
        n = len(df)
        for i in range(max(p["slow"], p["atr_period"]) + p["signal"] + 1, n - 1):
            if pd.isna(a.iloc[i]) or a.iloc[i] <= 0:
                continue
            sl_dist = a.iloc[i] * sl_mult

            if bull.iloc[i]:
                if use_zero and macd_l.iloc[i] < 0:
                    continue
                entry = O[i + 1]
                tp_prices = [(entry + r * sl_dist, q) for r, q in tps_param]
                setups.append(dict(
                    signal_idx=i+1, direction="Bull",
                    entry=entry, sl=entry - sl_dist, risk=sl_dist,
                    tps=tp_prices, liq_level=float(macd_l.iloc[i]),
                    meta={"macd": float(macd_l.iloc[i])},
                ))
            elif bear.iloc[i]:
                if use_zero and macd_l.iloc[i] > 0:
                    continue
                entry = O[i + 1]
                tp_prices = [(entry - r * sl_dist, q) for r, q in tps_param]
                setups.append(dict(
                    signal_idx=i+1, direction="Bear",
                    entry=entry, sl=entry + sl_dist, risk=sl_dist,
                    tps=tp_prices, liq_level=float(macd_l.iloc[i]),
                    meta={"macd": float(macd_l.iloc[i])},
                ))
        return setups
