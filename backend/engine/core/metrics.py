"""
Strategy-agnostic performance metrics for a completed trade log.
"""
from __future__ import annotations
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd


def compute_metrics(
    tdf: pd.DataFrame,
    *,
    initial_equity: float = 100.0,
    risk_pct: float = 0.01,
    max_risk_usd: float = 600.0,
) -> Optional[Dict[str, Any]]:
    """
    Compute headline + supporting metrics for a trade log.

    Returns None when the log has no resolved trades.
    """
    if tdf is None or tdf.empty:
        return None
    res = tdf[tdf["result"] != "Unresolved"].copy()
    if res.empty:
        return None

    pnl    = res["pnl_r"].values
    wins   = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    wr     = len(wins) / len(pnl) * 100.0
    ev     = float(np.mean(pnl))
    total  = float(np.sum(pnl))

    eq    = initial_equity
    curve = [eq]
    for r in pnl:
        risk_usd = min(eq * risk_pct, max_risk_usd)
        eq += r * risk_usd
        curve.append(eq)
    curve = np.array(curve)

    peak   = np.maximum.accumulate(curve)
    dd_pct = (curve - peak) / peak * 100.0
    max_dd = float(dd_pct.min())

    pf = (abs(wins.sum() / losses.sum())
          if len(losses) and losses.sum() != 0 else float("inf"))

    exit_counts = (res["exit_type"].value_counts().to_dict()
                   if "exit_type" in res.columns else {})

    return dict(
        trades        = len(pnl),
        wr            = wr,
        ev            = ev,
        total_r       = total,
        max_dd        = max_dd,
        profit_factor = pf,
        avg_win       = float(wins.mean())   if len(wins)   else 0.0,
        avg_loss      = float(losses.mean()) if len(losses) else 0.0,
        final_equity  = float(curve[-1]),
        curve         = curve,
        pnl           = pnl,
        exit_counts   = exit_counts,
        n_setups      = len(tdf),
        n_unresolved  = int((tdf["result"] == "Unresolved").sum()),
    )
