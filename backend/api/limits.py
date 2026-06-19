"""
Tier-based rate / feature limits.
"""
from __future__ import annotations
import os
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.db import get_db, User, SavedStrategy, Tier
from backend.api.auth import current_user


# ── Tier-level limits ───────────────────────────────────────────────────────
# Node builder is the CORE feature — available to ALL tiers.
# Differentiation is on depth: saved strategies, backtest history, AI calls.
LIMITS = {
    Tier.FREE:   {"daily_backtests": 10,   "saved_strategies": 3,   "csv_upload": False, "node_builder": True},
    Tier.TRADER: {"daily_backtests": None, "saved_strategies": 20,  "csv_upload": True,  "node_builder": True},
    Tier.PRO:    {"daily_backtests": None, "saved_strategies": 100, "csv_upload": True,  "node_builder": True},
}


def enforce_backtest_quota(user: User = Depends(current_user),
                           db:   Session = Depends(get_db)) -> User:
    cap = LIMITS[user.tier]["daily_backtests"]
    if cap is None:
        return user   # unlimited tier (Trader/Pro)

    from backend.api import supa as _supa
    # The quota can only be enforced when we can authoritatively count today's
    # runs. backtest_runs lives in Supabase, so we need it enabled AND a stable
    # Supabase identity (clerk_id). When neither applies — local dev without
    # Supabase, or a header/anon caller with no clerk_id — there is no quota
    # backend to consult, so the cap is simply not enforced (by design for dev).
    if not (_supa.enabled() and user.clerk_id):
        return user

    cutoff = (datetime.utcnow() - timedelta(days=1)).isoformat()
    try:
        used = _supa.count("backtest_runs", {
            "user_id":    f"eq.{user.clerk_id}",
            "created_at": f"gte.{cutoff}",
        })
    except Exception:
        # Quota backend is configured but erroring. Fail CLOSED — never grant
        # unlimited runs because the counter is unreachable.
        raise HTTPException(503,
            "Couldn't verify your backtest quota right now. Please retry shortly.")

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
    # Node builder is now open to all tiers — kept for backwards compat
    return user


# ── Server-paid AI cost guard ─────────────────────────────────────────────────
# Persisted to disk so quotas survive service restarts.
# File: EDGEKIT_DATA_DIR/ai_usage.json  (same dir as CSV store)

_AI_LOCK  = threading.Lock()
_AI_FILE  = Path(os.environ.get("EDGEKIT_DATA_DIR",
                                str(Path(__file__).parent.parent / "tmp"))) / "ai_usage.json"
SERVER_AI_DAILY_CAP = int(os.environ.get("SERVER_AI_DAILY_CAP", "40"))


def _load_ai_usage() -> dict:
    try:
        if _AI_FILE.exists():
            return json.loads(_AI_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_ai_usage(data: dict) -> None:
    try:
        _AI_FILE.parent.mkdir(parents=True, exist_ok=True)
        _AI_FILE.write_text(json.dumps(data))
    except Exception:
        pass   # disk write failed — graceful degradation


def enforce_ai_quota(identity: str, cap: int = SERVER_AI_DAILY_CAP) -> None:
    """Raise 429 once `identity` has used `cap` server-paid AI calls today.
    Usage is persisted to disk so it survives restarts."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    key   = f"{identity or 'anon'}::{today}"

    with _AI_LOCK:
        usage = _load_ai_usage()

        # Prune keys from previous days to keep file small
        usage = {k: v for k, v in usage.items() if k.endswith(today)}

        used = usage.get(key, 0)
        if used >= cap:
            raise HTTPException(
                429,
                "You've hit today's limit on the free AI assistant. Add your own "
                "API key under Resources → AI Model to keep going, or try again tomorrow.",
            )
        usage[key] = used + 1
        _save_ai_usage(usage)
