"""
Bollinger Band Bounce — mean-reversion fade off the bands.

Logic:
  Bull: close touches/breaches lower band, then closes BACK inside → buy next-bar open
  Bear: close touches/breaches upper band, then closes BACK inside → sell next-bar open

SL just past the band wick + buffer; TPs return toward the middle band and beyond.
"""
from __future__ import annotations
from typing import List, Dict, Any
import pandas as pd

from .base import Strategy, ParamSpec
from ..core import indicators as ind


class BollingerBounce(Strategy):
    name        = "Bollinger Band Bounce"
    description = ("Fade extremes back to the middle. Long after a lower-band wick that "
                   "closes back inside; mirror for shorts. Mean reversion classic.")
    timeframes  = ["M15", "H1", "H4"]
    instruments = ["XAUUSD", "EURUSD", "BTCUSD"]

    param_schema = [
        ParamSpec("bb_period", "BB period",       "int",   20,  min=10, max=50,  step=1, group="Indicator"),
        ParamSpec("bb_stdev",  "BB std-dev",      "float", 2.0, min=1.0, max=3.5, step=0.1, group="Indicator"),
        ParamSpec("atr_period","ATR period",      "int",   14,  min=5,  max=50,  step=1, group="Risk"),
        ParamSpec("sl_atr_mult","SL = ATR ×",     "float", 1.2, min=0.5, max=4.0, step=0.1, group="Risk"),
        ParamSpec("require_close_inside", "Close back inside band required", "bool", True,
                  description="Stricter signal — close must return inside the band.", group="Filter"),
        ParamSpec("pip", "Pip size", "float", 0.10, min=0.00001, max=10.0, step=0.00001, group="Advanced"),
    ]

    def detect(self, df: pd.DataFrame, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        p          = self.validate_params(params)
        bb         = ind.bollinger(df["C"], p["bb_period"], p["bb_stdev"])
        a          = ind.atr(df, p["atr_period"])
        sl_mult    = p["sl_atr_mult"]
        strict     = bool(p["require_close_inside"])
        tps_param  = params.get("tps") or [(1.5, 0.5), (2.5, 0.5)]

        L, H, Cv, O = df["L"].values, df["H"].values, df["C"].values, df["O"].values
        upper = bb["upper"].values
        lower = bb["lower"].values

        setups: list[dict] = []
        n = len(df)
        for i in range(p["bb_period"] + 1, n - 1):
            if pd.isna(a.iloc[i]) or a.iloc[i] <= 0:
                continue
            sl_dist = a.iloc[i] * sl_mult

            # Bull: low pierced lower band, close back above it
            pierced_low  = L[i] < lower[i]
            close_inside = Cv[i] > lower[i] if strict else True
            if pierced_low and close_inside:
                entry = O[i + 1]
                tp_prices = [(entry + r * sl_dist, q) for r, q in tps_param]
                setups.append(dict(
                    signal_idx=i+1, direction="Bull",
                    entry=entry, sl=entry - sl_dist, risk=sl_dist,
                    tps=tp_prices, liq_level=float(lower[i]),
                    meta={"band_low": float(lower[i])},
                ))

            # Bear: high pierced upper band, close back below
            pierced_high  = H[i] > upper[i]
            close_inside2 = Cv[i] < upper[i] if strict else True
            if pierced_high and close_inside2:
                entry = O[i + 1]
                tp_prices = [(entry - r * sl_dist, q) for r, q in tps_param]
                setups.append(dict(
                    signal_idx=i+1, direction="Bear",
                    entry=entry, sl=entry + sl_dist, risk=sl_dist,
                    tps=tp_prices, liq_level=float(upper[i]),
                    meta={"band_high": float(upper[i])},
                ))
        return setups
