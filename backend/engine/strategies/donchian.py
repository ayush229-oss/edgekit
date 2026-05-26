"""
Donchian Breakout — Turtle-trader classic.

Logic:
  Bull: close > rolling N-bar high  → buy next-bar open
  Bear: close < rolling N-bar low   → sell next-bar open

ATR-based SL. Optional trend-quality filter (entry must close above ATR-scaled
distance above the average to avoid weak breakouts).
"""
from __future__ import annotations
from typing import List, Dict, Any
import pandas as pd

from .base import Strategy, ParamSpec
from ..core import indicators as ind


class DonchianBreakout(Strategy):
    name        = "Donchian Channel Breakout"
    description = ("Buy fresh highs, sell fresh lows. Trend-follower's bread and butter — "
                   "low win rate, big winners. Famous Turtle-trader logic.")
    timeframes  = ["H1", "H4", "D1"]
    instruments = ["XAUUSD", "EURUSD", "BTCUSD", "NIFTY"]

    param_schema = [
        ParamSpec("channel_period", "Channel period (bars)", "int",   20, min=5, max=100, step=1,
                  description="Donchian uses the highest high / lowest low over N bars.",
                  group="Indicator"),
        ParamSpec("atr_period",     "ATR period",            "int",   14, min=5, max=50, step=1, group="Risk"),
        ParamSpec("sl_atr_mult",    "SL = ATR ×",            "float", 2.0, min=0.5, max=5.0, step=0.1, group="Risk"),
        ParamSpec("min_atr_pips",   "Min ATR pips (filter)", "float", 0.0, min=0.0, max=200.0, step=1.0,
                  description="Skip flat markets — ATR must exceed this (in pips). 0 = off.",
                  group="Filter"),
        ParamSpec("pip", "Pip size", "float", 0.10, min=0.00001, max=10.0, step=0.00001, group="Advanced"),
    ]

    def detect(self, df: pd.DataFrame, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        p          = self.validate_params(params)
        period     = p["channel_period"]
        atr_p      = p["atr_period"]
        sl_mult    = p["sl_atr_mult"]
        pip        = p["pip"]
        min_atr    = p["min_atr_pips"] * pip
        tps_param  = params.get("tps") or [(2.0, 0.4), (3.0, 0.4), (5.0, 0.2)]

        H, L, Cv, O = df["H"].values, df["L"].values, df["C"].values, df["O"].values
        a = ind.atr(df, atr_p)

        # Prior-bar channel = highest of [i-period .. i-1]
        upper = df["H"].rolling(period).max().shift(1).values
        lower = df["L"].rolling(period).min().shift(1).values

        setups: list[dict] = []
        n = len(df)
        for i in range(max(period, atr_p) + 1, n - 1):
            if pd.isna(a.iloc[i]) or a.iloc[i] <= 0 or pd.isna(upper[i]):
                continue
            if min_atr > 0 and a.iloc[i] < min_atr:
                continue
            sl_dist = a.iloc[i] * sl_mult

            if Cv[i] > upper[i]:
                entry = O[i + 1]
                tp_prices = [(entry + r * sl_dist, q) for r, q in tps_param]
                setups.append(dict(
                    signal_idx=i+1, direction="Bull",
                    entry=entry, sl=entry - sl_dist, risk=sl_dist,
                    tps=tp_prices, liq_level=float(upper[i]),
                    meta={"channel_high": float(upper[i])},
                ))
            elif Cv[i] < lower[i]:
                entry = O[i + 1]
                tp_prices = [(entry - r * sl_dist, q) for r, q in tps_param]
                setups.append(dict(
                    signal_idx=i+1, direction="Bear",
                    entry=entry, sl=entry + sl_dist, risk=sl_dist,
                    tps=tp_prices, liq_level=float(lower[i]),
                    meta={"channel_low": float(lower[i])},
                ))
        return setups
