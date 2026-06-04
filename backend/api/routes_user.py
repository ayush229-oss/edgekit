"""
User-scoped routes: saved strategies, backtest history, waitlist.
"""
from __future__ import annotations
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.db import (
    get_db, User, SavedStrategy, WaitlistEntry, Tier,
)
from backend.api.auth   import current_user
from backend.api.limits import enforce_saved_strategy_cap, LIMITS

router = APIRouter()


# ─── Schemas ─────────────────────────────────────────────────────────────────
class SavedStrategyIn(BaseModel):
    strategy_id: str
    name:        str
    params:      dict
    tps:         list = []
    notes:       str  = ""


class SavedStrategyOut(SavedStrategyIn):
    id:         int
    created_at: str
    updated_at: str

    @classmethod
    def from_orm_row(cls, s: SavedStrategy) -> "SavedStrategyOut":
        return cls(
            id=s.id, strategy_id=s.strategy_id, name=s.name,
            params=s.params or {}, tps=s.tps or [], notes=s.notes or "",
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        )


class WaitlistIn(BaseModel):
    email:    str
    role:     str = ""
    referrer: str = ""


# ─── /me ─────────────────────────────────────────────────────────────────────
@router.get("/me")
def me(user: User = Depends(current_user)):
    return {
        "id":     user.id,
        "email":  user.email,
        "tier":   user.tier.value,
        "limits": LIMITS[user.tier],
    }


# ─── Saved strategies ───────────────────────────────────────────────────────
@router.get("/saved-strategies", response_model=List[SavedStrategyOut])
def list_saved(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.query(SavedStrategy).filter(SavedStrategy.user_id == user.id).all()
    return [SavedStrategyOut.from_orm_row(s) for s in rows]


@router.post("/saved-strategies", response_model=SavedStrategyOut)
def save_strategy(body: SavedStrategyIn,
                  db:   Session = Depends(get_db),
                  user: User    = Depends(enforce_saved_strategy_cap)):
    s = SavedStrategy(
        user_id=user.id, strategy_id=body.strategy_id, name=body.name,
        params=body.params, tps=body.tps, notes=body.notes,
    )
    db.add(s); db.commit(); db.refresh(s)
    return SavedStrategyOut.from_orm_row(s)


@router.delete("/saved-strategies/{sid}")
def delete_saved(sid: int,
                 db:   Session = Depends(get_db),
                 user: User    = Depends(current_user)):
    s = db.query(SavedStrategy).filter(
        SavedStrategy.id == sid, SavedStrategy.user_id == user.id).first()
    if not s: raise HTTPException(404, "Not found")
    db.delete(s); db.commit()
    return {"deleted": sid}


# ─── Backtest history ────────────────────────────────────────────────────────
@router.get("/runs")
def list_runs(limit: int = 50,
              db:   Session = Depends(get_db),
              user: User    = Depends(current_user)):
    from backend.api import supa as _supa
    if not (user.clerk_id and _supa.enabled()):
        return []
    try:
        rows = _supa.select("backtest_runs", {
            "user_id": f"eq.{user.clerk_id}",
            "order":   "created_at.desc",
            "limit":   str(limit),
        })
    except Exception:
        return []
    return [{
        "id":          r["id"],
        "strategy_id": r["strategy_id"],
        "symbol":      r.get("symbol", ""),
        "timeframe":   r.get("timeframe", ""),
        "bars":        r.get("bars", 0),
        "metrics":     r.get("metrics", {}),
        "created_at":  r.get("created_at", ""),
    } for r in rows]


# ─── Waitlist (public — no auth) ─────────────────────────────────────────────
@router.post("/waitlist")
def join_waitlist(body: WaitlistIn, db: Session = Depends(get_db)):
    existing = db.query(WaitlistEntry).filter(WaitlistEntry.email == body.email).first()
    if existing:
        return {"ok": True, "already": True}
    e = WaitlistEntry(email=body.email, role=body.role, referrer=body.referrer)
    db.add(e); db.commit()
    return {"ok": True, "already": False}


@router.get("/waitlist/count")
def waitlist_count(db: Session = Depends(get_db)):
    n = db.query(WaitlistEntry).count()
    return {"count": n}
