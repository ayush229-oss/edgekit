"""
Liquidity Grab + Engulfing — accessible SMC for beginners.

Logic (bull, bear is mirror):
  1. Price sweeps below a recent N-bar low (liquidity grab)
  2. Same or next candle is a BULLISH ENGULFING of the prior candle's body
  3. Buy market on confirmation candle close (next-bar open)

SL just below sweep low. TPs in R-multiples.
"""
from __future__ import annotations
from typing import List, Dict, Any
import pandas as pd

from .base import Strategy, ParamSpec


class LiquidityGrabEngulfing(Strategy):
    name        = "Liquidity Grab + Engulfing"
    description = ("Simplified SMC. Sweep an N-bar low/high then confirm with an "
                   "engulfing candle. Easier to spot than OB+FVG.")
    timeframes  = ["M15", "H1", "H4"]
    instruments = ["XAUUSD", "EURUSD", "BTCUSD"]

    param_schema = [
        ParamSpec("lookback", "Liquidity lookback (bars)", "int", 20, min=5, max=80, step=1,
                  description="Look this many bars back to find the level to sweep.",
                  group="Detection"),
        ParamSpec("sl_buffer_pips", "SL buffer (pips)", "float", 3.0, min=0.0, max=50.0, step=0.5,
                  description="Extra pips below sweep low / above sweep high.",
                  group="Risk"),
        ParamSpec("pip", "Pip size", "float", 0.10, min=0.00001, max=10.0, step=0.00001, group="Advanced"),
    ]

    def detect(self, df: pd.DataFrame, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        p          = self.validate_params(params)
        lb         = p["lookback"]
        buf        = p["sl_buffer_pips"] * p["pip"]
        tps_param  = params.get("tps") or [(2.0, 0.4), (3.0, 0.3), (5.0, 0.3)]

        O, H, L, Cv = df["O"].values, df["H"].values, df["L"].values, df["C"].values
        n = len(df)

        setups: list[dict] = []
        for i in range(lb + 1, n - 1):
            prior_low  = L[i - lb:i].min()
            prior_high = H[i - lb:i].max()

            # Bull liquidity grab: this bar's low < prior_low AND bullish engulfing
            grabbed_low = L[i] < prior_low
            engulf_bull = (
                Cv[i] > O[i]                          # bullish bar
                and O[i] <= Cv[i - 1]                 # opened at/below prior close
                and Cv[i] >= O[i - 1]                 # closed at/above prior open
            )
            if grabbed_low and engulf_bull:
                entry = O[i + 1]
                sl    = L[i] - buf
                risk  = entry - sl
                if risk > 0:
                    tp_prices = [(entry + r * risk, q) for r, q in tps_param]
                    setups.append(dict(
                        signal_idx=i+1, direction="Bull",
                        entry=entry, sl=sl, risk=risk,
                        tps=tp_prices, liq_level=float(prior_low),
                        meta={"swept_low": float(prior_low)},
                    ))

            # Bear liquidity grab
            grabbed_high = H[i] > prior_high
            engulf_bear = (
                Cv[i] < O[i]
                and O[i] >= Cv[i - 1]
                and Cv[i] <= O[i - 1]
            )
            if grabbed_high and engulf_bear:
                entry = O[i + 1]
                sl    = H[i] + buf
                risk  = sl - entry
                if risk > 0:
                    tp_prices = [(entry - r * risk, q) for r, q in tps_param]
                    setups.append(dict(
                        signal_idx=i+1, direction="Bear",
                        entry=entry, sl=sl, risk=risk,
                        tps=tp_prices, liq_level=float(prior_high),
                        meta={"swept_high": float(prior_high)},
                    ))

        return setups
