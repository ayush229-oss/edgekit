"""
OB + FVG + Liquidity Sweep — flagship SMC strategy.

Logic (bull setup, bear is mirrored):
  1. Liquidity forms — 2+ equal highs within scan_window
  2. Sweep — impulse breaks the equal-highs level
  3. FVG — gap of >= fvg_min pips between bar [i-2] and the sweep bar [i]
  4. OB — first bearish candle in the lookback 3..ob_lookback bars before sweep
  5. Entry — limit at OB midpoint (or OB edge, depending on sl_mode)
  6. SL — sl_pips behind entry/edge
  7. TPs — list of (R-multiple, qty fraction) ladder
"""
from __future__ import annotations
from typing import List, Dict, Any
import pandas as pd

from .base import Strategy, ParamSpec


class OBFVGLiquidity(Strategy):
    name        = "OB + FVG + Liquidity Sweep"
    description = ("Smart Money Concepts: detect a stop-hunt sweep of equal highs/lows, "
                   "verify a Fair Value Gap, then enter on retrace into the Order Block.")
    timeframes  = ["M5", "M15", "H1"]
    instruments = ["XAUUSD", "EURUSD", "GBPUSD", "BTCUSD"]

    param_schema = [
        # ── Detection ────────────────────────────────────────────────────
        ParamSpec("liq_pips",     "Liquidity tolerance (pips)",  "int",   10, min=1,   max=50,  step=1,
                  description="How close two highs/lows must be to count as 'equal'.",
                  group="Detection"),
        ParamSpec("liq_window",   "Scan window (bars)",           "int",   20, min=5,   max=200, step=5,
                  description="How far back to scan for equal highs/lows.",
                  group="Detection"),
        ParamSpec("ob_lookback",  "OB lookback (bars)",           "int",   10, min=3,   max=30,  step=1,
                  description="How far back from the sweep to hunt the Order Block.",
                  group="Detection"),
        ParamSpec("fvg_min_pips", "FVG minimum gap (pips)",       "float",  2.0, min=0.5, max=20.0, step=0.5,
                  description="Minimum size of the Fair Value Gap.",
                  group="Detection"),
        ParamSpec("min_touches",  "Min equal-level touches",      "int",   2,  min=2,   max=5,   step=1,
                  description="Number of equal highs/lows required.",
                  group="Detection"),
        # ── Entry & SL ───────────────────────────────────────────────────
        ParamSpec("sl_mode",      "SL anchor",                    "select", "midpoint",
                  options=["midpoint", "edge"],
                  description="midpoint = tight SL just past entry. edge = wider SL behind OB wick.",
                  group="Entry & SL"),
        ParamSpec("sl_pips",      "SL distance (pips)",           "int",   6,  min=2,   max=50,  step=1,
                  description="Stop-loss distance from anchor.",
                  group="Entry & SL"),
        # ── Pip size (instrument-specific, default = XAUUSD) ──────────────
        ParamSpec("pip",          "Pip size",                     "float", 0.10, min=0.00001, max=10.0, step=0.00001,
                  description="Auto-detected from symbol when uploading data.",
                  group="Advanced"),
    ]

    def detect(self, df: pd.DataFrame, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        p           = self.validate_params(params)
        pip         = p["pip"]
        liq_tol     = p["liq_pips"]     * pip
        fvg_min     = p["fvg_min_pips"] * pip
        sl_distance = p["sl_pips"]      * pip
        sl_mode     = p["sl_mode"]
        ob_lookback = p["ob_lookback"]
        liq_window  = p["liq_window"]
        min_touches = p["min_touches"]
        tps_param   = params.get("tps") or [(3.0, 0.33), (4.0, 0.33), (5.0, 0.34)]

        O, H, L, C = df["O"].values, df["H"].values, df["L"].values, df["C"].values
        n = len(df)
        setups = []
        scan_len = ob_lookback + liq_window + 5

        for i in range(scan_len, n - 1):
            ss = max(0, i - liq_window - ob_lookback - 5)

            # ── Bull setup ──────────────────────────────────────────────
            ref_h   = H[ss:i - 2].max() if i - 2 > ss else 0.0
            eq_h    = sum(1 for j in range(ss, i - 2) if abs(H[j] - ref_h) <= liq_tol)
            imp_hi  = max(H[i], H[i - 1], H[i - 2])
            bull_ok = eq_h >= min_touches and imp_hi > ref_h

            if bull_ok and H[i - 2] < L[i] and (L[i] - H[i - 2]) >= fvg_min:
                for k in range(1, ob_lookback + 1):
                    oi = i - 2 - k
                    if oi < 1: break
                    if C[oi] < O[oi]:                             # bearish OB
                        ob_top = max(O[oi], C[oi])
                        ob_bot = min(O[oi], C[oi])
                        entry  = (ob_top + ob_bot) / 2.0
                        risk   = ((ob_top - ob_bot) / 2.0 + sl_distance
                                  if sl_mode == "edge" else sl_distance)
                        if risk > 0:
                            tp_prices = [(entry + r * risk, q) for r, q in tps_param]
                            setups.append(dict(
                                signal_idx = i,
                                direction  = "Bull",
                                entry      = entry,
                                sl         = entry - risk,
                                risk       = risk,
                                tps        = tp_prices,
                                liq_level  = ref_h,
                                meta       = {"liq_touches": eq_h, "ob_bar": oi},
                            ))
                        break

            # ── Bear setup ──────────────────────────────────────────────
            ref_l   = L[ss:i - 2].min() if i - 2 > ss else 0.0
            eq_l    = sum(1 for j in range(ss, i - 2) if abs(L[j] - ref_l) <= liq_tol)
            imp_lo  = min(L[i], L[i - 1], L[i - 2])
            bear_ok = eq_l >= min_touches and imp_lo < ref_l

            if bear_ok and L[i - 2] > H[i] and (L[i - 2] - H[i]) >= fvg_min:
                for k in range(1, ob_lookback + 1):
                    oi = i - 2 - k
                    if oi < 1: break
                    if C[oi] > O[oi]:                             # bullish OB
                        ob_top = max(O[oi], C[oi])
                        ob_bot = min(O[oi], C[oi])
                        entry  = (ob_top + ob_bot) / 2.0
                        risk   = ((ob_top - ob_bot) / 2.0 + sl_distance
                                  if sl_mode == "edge" else sl_distance)
                        if risk > 0:
                            tp_prices = [(entry - r * risk, q) for r, q in tps_param]
                            setups.append(dict(
                                signal_idx = i,
                                direction  = "Bear",
                                entry      = entry,
                                sl         = entry + risk,
                                risk       = risk,
                                tps        = tp_prices,
                                liq_level  = ref_l,
                                meta       = {"liq_touches": eq_l, "ob_bar": oi},
                            ))
                        break

        return setups
