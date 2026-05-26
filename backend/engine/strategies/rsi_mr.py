"""
RSI Mean Reversion — classic oversold-bounce / overbought-fade.

Logic:
  Bull: RSI crosses BACK ABOVE oversold (default 30) → buy next-bar open
  Bear: RSI crosses BACK BELOW overbought (default 70) → sell next-bar open

Optional trend filter (price vs long EMA) keeps you with-trend.
SL anchored to ATR; TPs in R-multiples.
"""
from __future__ import annotations
from typing import List, Dict, Any
import pandas as pd

from .base import Strategy, ParamSpec
from ..core import indicators as ind


class RSIMeanReversion(Strategy):
    name        = "RSI Mean Reversion"
    description = ("Fade oversold and overbought extremes. Enter when RSI crosses back "
                   "into neutral territory. Tight ATR stop, R-multiple targets.")
    timeframes  = ["M15", "H1", "H4", "D1"]
    instruments = ["XAUUSD", "EURUSD", "BTCUSD", "AAPL", "NIFTY"]

    param_schema = [
        ParamSpec("rsi_period",   "RSI period",         "int",   14, min=5,  max=30,  step=1,
                  description="Lookback for RSI calculation.", group="Indicator"),
        ParamSpec("oversold",     "Oversold level",     "int",   30, min=10, max=40,  step=1,
                  description="RSI below this = oversold (long signal zone).",
                  group="Indicator"),
        ParamSpec("overbought",   "Overbought level",   "int",   70, min=60, max=90,  step=1,
                  description="RSI above this = overbought (short signal zone).",
                  group="Indicator"),
        ParamSpec("atr_period",   "ATR period",         "int",   14, min=5,  max=50,  step=1,
                  group="Risk"),
        ParamSpec("sl_atr_mult",  "SL = ATR ×",         "float", 1.5, min=0.5, max=5.0, step=0.1,
                  group="Risk"),
        ParamSpec("use_trend_filter", "With-trend only", "bool", False,
                  description="If ON, only longs above 200 EMA, shorts below.", group="Filter"),
        ParamSpec("trend_ema",    "Trend EMA period",   "int",   200, min=50, max=400, step=10,
                  description="Used only when trend filter is on.", group="Filter"),
        ParamSpec("pip",          "Pip size",           "float", 0.10, min=0.00001, max=10.0, step=0.00001,
                  group="Advanced"),
    ]

    def detect(self, df: pd.DataFrame, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        p = self.validate_params(params)
        rsi_p, os_, ob_ = p["rsi_period"], p["oversold"], p["overbought"]
        atr_p, sl_mult  = p["atr_period"], p["sl_atr_mult"]
        use_filter      = bool(p["use_trend_filter"])
        trend_p         = p["trend_ema"]
        tps_param       = params.get("tps") or [(2.0, 0.5), (3.0, 0.5)]

        if os_ >= ob_:
            return []

        r     = ind.rsi(df["C"], rsi_p)
        a     = ind.atr(df, atr_p)
        trend = ind.ema(df["C"], trend_p) if use_filter else None

        prev_below = r.shift(1) < os_
        cur_above  = r >= os_
        bull_sig   = prev_below & cur_above

        prev_above = r.shift(1) > ob_
        cur_below  = r <= ob_
        bear_sig   = prev_above & cur_below

        setups: list[dict] = []
        O  = df["O"].values
        Cv = df["C"].values
        n  = len(df)

        for i in range(max(rsi_p, atr_p, trend_p if use_filter else 0) + 1, n - 1):
            if pd.isna(a.iloc[i]) or a.iloc[i] <= 0:
                continue
            sl_dist = a.iloc[i] * sl_mult

            if bull_sig.iloc[i]:
                if use_filter and Cv[i] < trend.iloc[i]:
                    continue
                entry = O[i + 1]
                tp_prices = [(entry + r_ * sl_dist, q) for r_, q in tps_param]
                setups.append(dict(
                    signal_idx=i+1, direction="Bull",
                    entry=entry, sl=entry - sl_dist, risk=sl_dist,
                    tps=tp_prices, liq_level=float(r.iloc[i]),
                    meta={"rsi": float(r.iloc[i])},
                ))
            elif bear_sig.iloc[i]:
                if use_filter and Cv[i] > trend.iloc[i]:
                    continue
                entry = O[i + 1]
                tp_prices = [(entry - r_ * sl_dist, q) for r_, q in tps_param]
                setups.append(dict(
                    signal_idx=i+1, direction="Bear",
                    entry=entry, sl=entry + sl_dist, risk=sl_dist,
                    tps=tp_prices, liq_level=float(r.iloc[i]),
                    meta={"rsi": float(r.iloc[i])},
                ))
        return setups
