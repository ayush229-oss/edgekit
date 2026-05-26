"""
Trade preview generator — returns one winning + one losing trade
from a quick backtest, suitable for animating a thumbnail clip on the
strategy gallery card.

Cached in memory for 1 hour per strategy_id to avoid hammering MT5.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional
import math

import pandas as pd
from fastapi import APIRouter, HTTPException

from backend.engine.core import load_mt5, simulate, infer_pip_from_df
from backend.engine.strategies import get as get_strategy

router = APIRouter(prefix="/strategies", tags=["preview"])

# ─── Cache ────────────────────────────────────────────────────────────────────
_CACHE: dict[str, tuple[datetime, dict]] = {}
_TTL = timedelta(hours=1)

# Bars to include in a clip
PRE_ENTRY_BARS = 8
POST_EXIT_BARS = 3


def _bar_to_dict(row, idx):
    return {
        "i":    int(idx),
        "t":    row["time"].isoformat(),
        "o":    float(row["O"]),
        "h":    float(row["H"]),
        "l":    float(row["L"]),
        "c":    float(row["C"]),
    }


def _trade_clip(df: pd.DataFrame, trade: dict) -> dict:
    """Slice ~25 bars around a trade and return clip-ready data."""
    fill = int(trade.get("fill_idx") or trade.get("signal_idx"))
    exit_ = int(trade.get("exit_idx") or fill + 1)
    start = max(0, fill - PRE_ENTRY_BARS)
    end   = min(len(df) - 1, exit_ + POST_EXIT_BARS)

    bars = [_bar_to_dict(df.iloc[i], i) for i in range(start, end + 1)]
    tps = trade.get("tps", [])
    return {
        "direction":   trade["direction"],
        "result":      trade["result"],
        "exit_type":   trade.get("exit_type", ""),
        "pnl_r":       float(trade.get("pnl_r", 0.0)),
        "entry":       float(trade["entry"]),
        "sl":          float(trade["sl"]),
        "tps":         [{"price": float(p), "qty": float(q)} for p, q in tps],
        "fill_idx":    fill,
        "exit_idx":    exit_,
        "bars":        bars,
    }


def _pick_best_winner(tdf: pd.DataFrame) -> Optional[dict]:
    wins = tdf[(tdf["result"] == "Win") & (tdf["exit_type"] != "BE")]
    if wins.empty:
        return None
    # Prefer a Trail or TP3+ exit — most dramatic to show
    juicy = wins[wins["exit_type"].isin(["Trail", "TP3", "TP4", "TP5"])]
    pool  = juicy if not juicy.empty else wins
    return pool.sort_values("pnl_r", ascending=False).iloc[0].to_dict()


def _pick_clean_loser(tdf: pd.DataFrame) -> Optional[dict]:
    losses = tdf[tdf["result"] == "Loss"]
    if losses.empty:
        return None
    # Want a textbook -1R full SL hit, not a partial BE
    full_sl = losses[losses["exit_type"] == "SL"]
    pool    = full_sl if not full_sl.empty else losses
    return pool.iloc[len(pool) // 2].to_dict()       # middle-of-the-pack loser


def _compute(strategy_id: str) -> dict:
    Strat = get_strategy(strategy_id)
    strat = Strat()
    df = load_mt5("XAUUSD", "M15", n_bars=4000)
    pip = infer_pip_from_df(df, "XAUUSD")
    params = {**strat.default_params(), "pip": pip}
    setups = strat.detect(df, params)
    if not setups:
        raise RuntimeError("no setups detected")
    tdf = simulate(
        df, setups, pip=pip,
        trail_enabled=True, trail_from_idx=2,
        max_concurrent=1,
    )
    if tdf.empty:
        raise RuntimeError("no trades produced")

    winner = _pick_best_winner(tdf)
    loser  = _pick_clean_loser(tdf)
    return {
        "strategy_id": strategy_id,
        "symbol":      "XAUUSD",
        "timeframe":   "M15",
        "pip":         pip,
        "winner":      _trade_clip(df, winner) if winner else None,
        "loser":       _trade_clip(df, loser)  if loser  else None,
    }


@router.get("/{strategy_id}/preview-trades")
def get_preview(strategy_id: str):
    now = datetime.utcnow()
    if strategy_id in _CACHE:
        ts, data = _CACHE[strategy_id]
        if now - ts < _TTL:
            return data
    try:
        data = _compute(strategy_id)
    except KeyError:
        raise HTTPException(404, f"unknown strategy: {strategy_id}")
    except Exception as e:
        raise HTTPException(503, f"preview unavailable: {e}")
    _CACHE[strategy_id] = (now, data)
    return data
