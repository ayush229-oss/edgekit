"""
Supertrend Flip — very popular in Indian retail (Streak, TradingView).

Logic:
  Bull: Supertrend direction flips from -1 to +1 → buy next-bar open
  Bear: Supertrend direction flips from +1 to -1 → sell next-bar open

SL = current supertrend value. Engine handles TP ladder + trailing.
"""
from __future__ import annotations
from typing import List, Dict, Any
import pandas as pd

from .base import Strategy, ParamSpec
from ..core import indicators as ind


class SupertrendFlip(Strategy):
    name        = "Supertrend Flip"
    description = ("Flip-based trend follower. Enter when Supertrend changes direction. "
                   "SL anchored to the indicator itself. Hugely popular in Indian retail.")
    timeframes  = ["M15", "H1", "H4", "D1"]
    instruments = ["NIFTY", "BANKNIFTY", "XAUUSD", "BTCUSD"]

    param_schema = [
        ParamSpec("st_period",   "Supertrend period", "int",   10, min=5,  max=30, step=1, group="Indicator"),
        ParamSpec("st_mult",     "Supertrend multiplier", "float", 3.0, min=1.0, max=6.0, step=0.1, group="Indicator"),
        ParamSpec("pip", "Pip size", "float", 0.10, min=0.00001, max=10.0, step=0.00001, group="Advanced"),
    ]

    def detect(self, df: pd.DataFrame, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        p   = self.validate_params(params)
        st  = ind.supertrend(df, p["st_period"], p["st_mult"])
        tps_param = params.get("tps") or [(2.0, 0.4), (3.0, 0.3), (5.0, 0.3)]

        O = df["O"].values
        n = len(df)
        st_val = st["supertrend"].values
        st_dir = st["direction"].values

        setups: list[dict] = []
        for i in range(p["st_period"] + 2, n - 1):
            if pd.isna(st_val[i]) or pd.isna(st_val[i - 1]):
                continue
            prev_dir = st_dir[i - 1]
            cur_dir  = st_dir[i]
            if prev_dir == cur_dir:
                continue

            entry = O[i + 1]
            if cur_dir == 1:
                sl = float(st_val[i])
                risk = entry - sl
                if risk <= 0: continue
                tp_prices = [(entry + r * risk, q) for r, q in tps_param]
                setups.append(dict(
                    signal_idx=i+1, direction="Bull",
                    entry=entry, sl=sl, risk=risk,
                    tps=tp_prices, liq_level=float(st_val[i]),
                    meta={"supertrend": float(st_val[i])},
                ))
            elif cur_dir == -1:
                sl = float(st_val[i])
                risk = sl - entry
                if risk <= 0: continue
                tp_prices = [(entry - r * risk, q) for r, q in tps_param]
                setups.append(dict(
                    signal_idx=i+1, direction="Bear",
                    entry=entry, sl=sl, risk=risk,
                    tps=tp_prices, liq_level=float(st_val[i]),
                    meta={"supertrend": float(st_val[i])},
                ))
        return setups
