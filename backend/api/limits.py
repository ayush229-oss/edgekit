"""
Tier-based rate / feature limits.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.db import get_db, User, BacktestRun, SavedStrategy, Tier
from backend.api.auth import current_user


# ── Tier-level limits ───────────────────────────────────────────────────────
LIMITS = {
    Tier.FREE:   {"daily_backtests": 3,    "saved_strategies": 1,   "csv_upload": False, "node_builder": False},
    Tier.TRADER: {"daily_backtests": None, "saved_strategies": 10,  "csv_upload": True,  "node_builder": False},
    Tier.PRO:    {"daily_backtests": None, "saved_strategies": 100, "csv_upload": True,  "node_builder": True},
}


def enforce_backtest_quota(user: User = Depends(current_user),
                           db:   Session = Depends(get_db)) -> User:
    cap = LIMITS[user.tier]["daily_backtests"]
    if cap is None:
        return user
    cutoff = datetime.utcnow() - timedelta(days=1)
    used   = db.query(func.count(BacktestRun.id))\
               .filter(BacktestRun.user_id == user.id,
                       BacktestRun.created_at >= cutoff).scalar() or 0
    if used >= cap:
        raise HTTPException(429,
            f"Daily backtest cap reached ({cap}/day on {user.tier.value}). "
            f"Upgrade for unlimited.")
    return user


def enforce_saved_strategy_cap(user: User = Depends(current_user),
                               db:   Session = Depends(get_db)) -> User:
    cap = LIMITS[user.tier]["saved_strategies"]
    if cap is None: return user
    used = db.query(func.count(SavedStrategy.id))\
             .filter(SavedStrategy.user_id == user.id).scalar() or 0
    if used >= cap:
        raise HTTPException(409,
            f"Saved-strategy cap reached ({cap} on {user.tier.value}). "
            "Delete one, or upgrade.")
    return user


def require_csv_upload(user: User = Depends(current_user)) -> User:
    if not LIMITS[user.tier]["csv_upload"]:
        raise HTTPException(403,
            "CSV upload is a Trader+ feature. Free tier uses MT5 live data only.")
    return user


def require_node_builder(user: User = Depends(current_user)) -> User:
    if not LIMITS[user.tier]["node_builder"]:
        raise HTTPException(403,
            "Visual node builder is a Pro feature.")
    return user
