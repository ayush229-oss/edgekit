"""
Forward (paper) testing.

A forward test pins a strategy to a START time, then re-runs it on fresh bars on
a schedule. Only trades that FILL after the start count — so results accumulate
on data the strategy never saw at design time. This is the trust feature: a
backtest can be overfit; forward performance on unseen bars can't be.

  POST   /forward/start         create + run once
  GET    /forward/list          list mine
  GET    /forward/{id}          detail (full latest snapshot)
  POST   /forward/{id}/refresh  re-run now
  POST   /forward/{id}/stop     stop tracking

A background thread (start_forward_scheduler) refreshes all active tests every
REFRESH_SECONDS so they update without anyone clicking.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db import get_db, SessionLocal, ForwardTest
from backend.engine.core import (
    load_mt5, simulate, compute_metrics, infer_pip_from_df, data_source_of,
)
from backend.engine.builder_v2.engine import GraphV2Strategy

router = APIRouter(prefix="/forward", tags=["forward"])

FORWARD_NBARS   = 6000     # window pulled each refresh (covers ~2 months of M15)
REFRESH_SECONDS = 300      # how often the scheduler re-runs active tests


# ─── Core: run the strategy + isolate the forward (post-start) trades ────────
def _compute_latest(ft: ForwardTest) -> Dict[str, Any]:
    df  = load_mt5(ft.symbol, ft.timeframe, FORWARD_NBARS)
    pip = infer_pip_from_df(df, ft.symbol)
    strat  = GraphV2Strategy(ft.graph)
    setups = strat.detect(df, {"pip": pip})

    m = ft.mgmt or {}
    tdf = simulate(
        df, setups,
        target_r         = m.get("target_r", 3.0),
        target_close_pct = m.get("target_close_pct", 1.0),
        trail_mode       = m.get("trail_mode", "none"),
        trail_start      = m.get("trail_start", "after_target"),
        trail_params     = m.get("trail_params", {}) or {},
        pip              = pip,
    )

    times   = df["time"]
    n       = len(df)
    started = ft.started_at
    bars_seen = int((times >= started).sum())

    def _fill_time(fi):
        if fi is None:
            return None
        try:
            i = int(fi)
        except (TypeError, ValueError):
            return None
        return times.iloc[i] if 0 <= i < n else None

    # Keep only trades that filled on or after the forward start.
    if tdf is not None and len(tdf):
        keep = [(_fill_time(r.get("fill_idx")) is not None and _fill_time(r.get("fill_idx")) >= started)
                for _, r in tdf.iterrows()]
        fwd = tdf[keep]
    else:
        fwd = tdf

    metrics = compute_metrics(
        fwd,
        initial_equity = m.get("initial_equity", 100.0),
        risk_pct       = m.get("risk_pct", 0.01),
        max_risk_usd   = m.get("max_risk_usd", 600.0),
    ) if (fwd is not None and len(fwd)) else None

    trades: List[Dict[str, Any]] = []
    if fwd is not None and len(fwd):
        for _, t in fwd.iterrows():
            ft_time = _fill_time(t.get("fill_idx"))
            trades.append({
                "direction": str(t.get("direction", "Bull")),
                "entry":     float(t.get("entry") or 0.0),
                "sl":        float(t.get("sl") or 0.0),
                "result":    str(t.get("result", "")),
                "exit_type": str(t.get("exit_type", "")),
                "pnl_r":     float(t.get("pnl_r") or 0.0),
                "time":      ft_time.isoformat() if ft_time is not None else None,
            })

    if metrics is not None:
        out_metrics = {
            "trades":        metrics["trades"],
            "wr":            metrics["wr"],
            "ev":            metrics["ev"],
            "total_r":       metrics["total_r"],
            "profit_factor": (metrics["profit_factor"] if metrics["profit_factor"] != float("inf") else 99.0),
            "max_dd":        metrics["max_dd"],
            "final_equity":  metrics["final_equity"],
        }
        equity = metrics["curve"].tolist()
    else:
        out_metrics = {"trades": 0, "wr": 0.0, "ev": 0.0, "total_r": 0.0,
                       "profit_factor": 0.0, "max_dd": 0.0,
                       "final_equity": m.get("initial_equity", 100.0)}
        equity = []

    return {
        "metrics":     out_metrics,
        "trades":      trades[-100:],
        "equity":      equity,
        "bars_seen":   bars_seen,
        "data_source": data_source_of(df),
        "last_run":    datetime.utcnow().isoformat(),
    }


def _refresh(ft: ForwardTest, db: Session) -> None:
    try:
        ft.latest = _compute_latest(ft)
        ft.updated_at = datetime.utcnow()
        db.add(ft); db.commit()
    except Exception as e:           # never let one bad test break the loop
        db.rollback()
        try:
            cur = dict(ft.latest or {})
            cur["error"]    = f"{type(e).__name__}: {str(e)[:200]}"
            cur["last_run"] = datetime.utcnow().isoformat()
            ft.latest = cur
            db.add(ft); db.commit()
        except Exception:
            db.rollback()


# ─── Background scheduler ────────────────────────────────────────────────────
_scheduler_started = False

def start_forward_scheduler() -> None:
    """Spawn a daemon thread that refreshes all active forward tests on a loop."""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    def _loop():
        # small initial delay so startup isn't blocked
        time.sleep(20)
        while True:
            try:
                db = SessionLocal()
                try:
                    active = db.query(ForwardTest).filter(ForwardTest.status == "active").all()
                    for ft in active:
                        _refresh(ft, db)
                finally:
                    db.close()
            except Exception:
                pass
            time.sleep(REFRESH_SECONDS)

    threading.Thread(target=_loop, name="forward-scheduler", daemon=True).start()


# ─── Schemas ─────────────────────────────────────────────────────────────────
class ForwardStartRequest(BaseModel):
    graph:     Dict[str, Any]
    name:      str = ""
    symbol:    str = "XAUUSD"
    timeframe: str = "M15"
    mgmt:      Dict[str, Any] = Field(default_factory=dict)
    baseline:  Dict[str, Any] = Field(default_factory=dict)   # backtest metrics for comparison


def _user_id(db: Session, x_dev_user: Optional[str], authorization: Optional[str]) -> Optional[int]:
    try:
        from backend.api.auth import current_user
        u = current_user(db=db, x_dev_user=x_dev_user, authorization=authorization)
        return u.id if u else None
    except Exception:
        return None


def _summary(ft: ForwardTest) -> Dict[str, Any]:
    return {
        "id":         ft.id,
        "name":       ft.name,
        "symbol":     ft.symbol,
        "timeframe":  ft.timeframe,
        "status":     ft.status,
        "started_at": ft.started_at.isoformat() if ft.started_at else None,
        "created_at": ft.created_at.isoformat() if ft.created_at else None,
        "updated_at": ft.updated_at.isoformat() if ft.updated_at else None,
        "baseline":   ft.baseline or {},
        "latest":     ft.latest or {},
    }


@router.post("/start")
def forward_start(
    req: ForwardStartRequest,
    db: Session = Depends(get_db),
    x_dev_user:    Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    if not req.graph or not req.graph.get("nodes"):
        raise HTTPException(400, "A strategy graph with nodes is required.")
    # Validate the graph upfront so we don't create a test that can never run.
    try:
        GraphV2Strategy(req.graph)
    except Exception as e:
        raise HTTPException(422, f"Strategy isn't valid yet: {e}")

    ft = ForwardTest(
        user_id    = _user_id(db, x_dev_user, authorization),
        name       = (req.name or req.graph.get("name") or "Forward test").strip()[:160],
        symbol     = req.symbol,
        timeframe  = req.timeframe,
        graph      = req.graph,
        mgmt       = req.mgmt or {},
        baseline   = req.baseline or {},
        started_at = datetime.utcnow(),
        status     = "active",
        latest     = {},
    )
    db.add(ft); db.commit(); db.refresh(ft)
    _refresh(ft, db)          # run once immediately (likely 0 forward trades yet)
    return _summary(ft)


@router.get("/list")
def forward_list(
    db: Session = Depends(get_db),
    x_dev_user:    Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> List[Dict[str, Any]]:
    uid = _user_id(db, x_dev_user, authorization)
    q = db.query(ForwardTest)
    q = q.filter(ForwardTest.user_id == uid) if uid is not None else q.filter(ForwardTest.user_id.is_(None))
    rows = q.order_by(ForwardTest.created_at.desc()).all()
    return [_summary(ft) for ft in rows]


@router.get("/{ft_id}")
def forward_get(ft_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ft = db.get(ForwardTest, ft_id)
    if not ft:
        raise HTTPException(404, "Forward test not found.")
    return _summary(ft)


@router.post("/{ft_id}/refresh")
def forward_refresh(ft_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ft = db.get(ForwardTest, ft_id)
    if not ft:
        raise HTTPException(404, "Forward test not found.")
    _refresh(ft, db)
    return _summary(ft)


@router.post("/{ft_id}/stop")
def forward_stop(ft_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ft = db.get(ForwardTest, ft_id)
    if not ft:
        raise HTTPException(404, "Forward test not found.")
    ft.status = "stopped"
    db.add(ft); db.commit()
    return _summary(ft)
