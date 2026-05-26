"""
VWAP Pullback — intraday classic for index/equity day traders.

Logic:
  - Define daily uptrend = price has been above VWAP for >= N bars today
  - Pullback = price touches VWAP from above
  - Bounce entry = first bullish close back above VWAP after the touch
  - Mirror for shorts (downtrend below VWAP)

SL = recent swing low / high. TPs in R-multiples.
"""
from __future__ import annotations
from typing import List, Dict, Any
import pandas as pd

from .base import Strategy, ParamSpec
from ..core import indicators as ind


class VWAPPullback(Strategy):
    name        = "VWAP Pullback"
    description = ("Intraday trend-pullback. Trade the bounce when price re-tests VWAP "
                   "in the direction of the day's bias. Volume-aware.")
    timeframes  = ["M5", "M15", "M30"]
    instruments = ["NIFTY", "BANKNIFTY", "SPX", "AAPL"]

    param_schema = [
        ParamSpec("min_bars_with_trend", "Bars in trend before signal", "int", 10,
                  min=3, max=40, step=1,
                  description="Price must spend ≥ this many bars on one side of VWAP first.",
                  group="Trend"),
        ParamSpec("atr_period",   "ATR period",       "int",   14,  min=5,  max=50, step=1, group="Risk"),
        ParamSpec("sl_atr_mult",  "SL = ATR ×",       "float", 1.0, min=0.3, max=3.0, step=0.1, group="Risk"),
        ParamSpec("pip", "Pip size", "float", 0.01, min=0.00001, max=100.0, step=0.00001, group="Advanced"),
    ]

    def detect(self, df: pd.DataFrame, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        if "V" not in df.columns:
            # VWAP cannot be computed without volume — degrade gracefully
            return []

        p   = self.validate_params(params)
        v   = ind.vwap(df)
        a   = ind.atr(df, p["atr_period"])
        sl_mult = p["sl_atr_mult"]
        n_trend = p["min_bars_with_trend"]
        tps_param = params.get("tps") or [(1.5, 0.5), (2.5, 0.5)]

        Cv, O = df["C"].values, df["O"].values
        v_arr = v.values
        above = (Cv > v_arr).astype(int)
        below = (Cv < v_arr).astype(int)

        # Rolling counts of bars-above / bars-below within the same day
        day = df["time"].dt.date
        above_run = pd.Series(above).groupby(day.values).cumsum().values
        below_run = pd.Series(below).groupby(day.values).cumsum().values

        setups: list[dict] = []
        n = len(df)
        for i in range(p["atr_period"] + 1, n - 1):
            if pd.isna(a.iloc[i]) or a.iloc[i] <= 0 or pd.isna(v_arr[i]):
                continue
            sl_dist = a.iloc[i] * sl_mult

            # Bull pullback: trend up for n_trend bars, prior bar tagged or below VWAP,
            # this bar closes back above
            if above_run[i] >= n_trend and Cv[i - 1] <= v_arr[i - 1] and Cv[i] > v_arr[i]:
                entry = O[i + 1]
                tp_prices = [(entry + r * sl_dist, q) for r, q in tps_param]
                setups.append(dict(
                    signal_idx=i+1, direction="Bull",
                    entry=entry, sl=entry - sl_dist, risk=sl_dist,
                    tps=tp_prices, liq_level=float(v_arr[i]),
                    meta={"vwap": float(v_arr[i])},
                ))
            elif below_run[i] >= n_trend and Cv[i - 1] >= v_arr[i - 1] and Cv[i] < v_arr[i]:
                entry = O[i + 1]
                tp_prices = [(entry - r * sl_dist, q) for r, q in tps_param]
                setups.append(dict(
                    signal_idx=i+1, direction="Bear",
                    entry=entry, sl=entry + sl_dist, risk=sl_dist,
                    tps=tp_prices, liq_level=float(v_arr[i]),
                    meta={"vwap": float(v_arr[i])},
                ))
        return setups
