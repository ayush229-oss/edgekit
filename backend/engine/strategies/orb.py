"""
Opening Range Breakout (ORB) — intraday classic, very popular for index futures
and US/Indian equities. Adapts to any session-based market.

Logic:
  - At the start of each trading day, identify the first N bars (default 3)
  - That window's HIGH / LOW = the opening range
  - During the rest of the day, a close above range high → buy
  - A close below range low → sell
  - SL = opposite end of the range (asymmetric — naturally good R:R)
"""
from __future__ import annotations
from typing import List, Dict, Any
import pandas as pd

from .base import Strategy, ParamSpec


class OpeningRangeBreakout(Strategy):
    name        = "Opening Range Breakout"
    description = ("Mark the first N bars of each day as the opening range. Trade the "
                   "first breakout in either direction. SL = opposite end of the range.")
    timeframes  = ["M5", "M15", "M30"]
    instruments = ["NIFTY", "BANKNIFTY", "SPX", "NDX", "XAUUSD"]

    param_schema = [
        ParamSpec("range_bars",  "Opening range bars", "int",   3,   min=1, max=12, step=1,
                  description="How many bars define the opening range.",
                  group="Range"),
        ParamSpec("session_start", "Session start hour", "int", 9,   min=0, max=23, step=1,
                  description="Hour (broker time) when the trading day begins.",
                  group="Range"),
        ParamSpec("max_signals_per_day", "Max trades per day", "int", 1, min=1, max=4, step=1,
                  description="Cap entries per day to avoid chop.",
                  group="Filter"),
        ParamSpec("min_range_pips", "Min range (pips)", "float", 0.0, min=0.0, max=500.0, step=1.0,
                  description="Skip days with a too-small opening range. 0 = off.",
                  group="Filter"),
        ParamSpec("pip", "Pip size", "float", 1.0, min=0.00001, max=100.0, step=0.00001, group="Advanced"),
    ]

    def detect(self, df: pd.DataFrame, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        p          = self.validate_params(params)
        rng_bars   = p["range_bars"]
        sess_h     = p["session_start"]
        max_sig    = p["max_signals_per_day"]
        min_range  = p["min_range_pips"] * p["pip"]
        tps_param  = params.get("tps") or [(1.0, 0.5), (2.0, 0.5)]

        H, L, Cv, O = df["H"].values, df["L"].values, df["C"].values, df["O"].values
        times = df["time"]
        dates = times.dt.date
        hours = times.dt.hour.values

        setups: list[dict] = []
        n = len(df)
        i = 0
        while i < n:
            cur_date  = dates.iloc[i]
            # Walk to session start of this date
            while i < n and (dates.iloc[i] != cur_date or hours[i] < sess_h):
                i += 1
            if i >= n: break
            session_start_i = i
            day_end_i       = i
            while day_end_i < n and dates.iloc[day_end_i] == cur_date:
                day_end_i += 1
            # Opening range
            if session_start_i + rng_bars > day_end_i:
                i = day_end_i; continue
            r_hi = H[session_start_i : session_start_i + rng_bars].max()
            r_lo = L[session_start_i : session_start_i + rng_bars].min()
            if r_hi - r_lo < min_range:
                i = day_end_i; continue
            risk = r_hi - r_lo
            if risk <= 0:
                i = day_end_i; continue

            sigs_today = 0
            for j in range(session_start_i + rng_bars, day_end_i):
                if sigs_today >= max_sig: break
                if Cv[j] > r_hi and j + 1 < n:
                    entry = O[j + 1]
                    tp_prices = [(entry + r * risk, q) for r, q in tps_param]
                    setups.append(dict(
                        signal_idx=j+1, direction="Bull",
                        entry=entry, sl=r_lo, risk=entry - r_lo,
                        tps=tp_prices, liq_level=float(r_hi),
                        meta={"range_high": float(r_hi), "range_low": float(r_lo)},
                    ))
                    sigs_today += 1
                elif Cv[j] < r_lo and j + 1 < n:
                    entry = O[j + 1]
                    tp_prices = [(entry - r * risk, q) for r, q in tps_param]
                    setups.append(dict(
                        signal_idx=j+1, direction="Bear",
                        entry=entry, sl=r_hi, risk=r_hi - entry,
                        tps=tp_prices, liq_level=float(r_lo),
                        meta={"range_high": float(r_hi), "range_low": float(r_lo)},
                    ))
                    sigs_today += 1
            i = day_end_i
        return setups
