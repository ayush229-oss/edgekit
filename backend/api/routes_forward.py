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
        return
    from backend.api import supa as _supa
    _supa.upsert_forward_test(
        vps_id=ft.id, user_id=None, name=ft.name,
        symbol=ft.symbol, timeframe=ft.timeframe, graph=ft.graph,
        mgmt=ft.mgmt, baseline=ft.baseline,
        started_at=ft.started_at.isoformat() if ft.started_at else None,
        status=ft.status, latest=ft.latest,
    )


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
                        if _mode(ft) == "sim":     # live tests are driven by the executor
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
    mode:      str = "sim"     # "sim" = paper recompute | "live_demo" = real demo execution
    mgmt:      Dict[str, Any] = Field(default_factory=dict)
    baseline:  Dict[str, Any] = Field(default_factory=dict)   # backtest metrics for comparison


def _mode(ft: ForwardTest) -> str:
    return (ft.mgmt or {}).get("mode", "sim")


def _live_rollup(ft: ForwardTest, db: Session) -> Dict[str, Any]:
    """Build the live (Grade-3) snapshot from the immutable ledger — real money,
    real costs. Never recomputed from price history; read straight from fills."""
    from backend.db import LiveTrade
    rows = db.query(LiveTrade).filter(LiveTrade.forward_test_id == ft.id).order_by(LiveTrade.ts).all()
    opens  = [r for r in rows if r.action == "open"]
    closes = [r for r in rows if r.action == "close"]
    n      = len(closes)
    wins   = [r for r in closes if r.profit > 0]
    total_profit = float(sum(r.profit for r in closes))
    return {
        "mode": "live_demo",
        "metrics": {
            "trades":        n,
            "wr":            (len(wins) / n * 100.0) if n else 0.0,
            "total_profit":  total_profit,
            "open_positions": max(0, len(opens) - len(closes)),
        },
        "costs": {
            "total_spread":   float(sum(r.spread for r in opens)),
            "total_slippage": float(sum(abs(r.slippage) for r in opens)),
        },
        "trades": [{
            "side": r.side, "fill_price": r.fill_price, "profit": r.profit,
            "spread": r.spread, "slippage": r.slippage,
            "time": r.ts.isoformat() if r.ts else None,
        } for r in closes[-100:]],
        "events":     len(rows),
        "last_run":   rows[-1].ts.isoformat() if rows else None,
    }


def _user_id(db: Session, x_dev_user: Optional[str], authorization: Optional[str]) -> Optional[int]:
    try:
        from backend.api.auth import current_user
        u = current_user(db=db, x_dev_user=x_dev_user, authorization=authorization)
        return u.id if u else None
    except Exception:
        return None


def _summary(ft: ForwardTest, db: Optional[Session] = None) -> Dict[str, Any]:
    mode = _mode(ft)
    # Live tests read straight from the immutable ledger; sim tests use the stored snapshot.
    latest = (_live_rollup(ft, db) if (mode == "live_demo" and db is not None) else (ft.latest or {}))
    return {
        "id":         ft.id,
        "name":       ft.name,
        "symbol":     ft.symbol,
        "timeframe":  ft.timeframe,
        "mode":       mode,
        "status":     ft.status,
        "started_at": ft.started_at.isoformat() if ft.started_at else None,
        "created_at": ft.created_at.isoformat() if ft.created_at else None,
        "updated_at": ft.updated_at.isoformat() if ft.updated_at else None,
        "baseline":   ft.baseline or {},
        "latest":     latest,
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

    mode = "live_demo" if req.mode == "live_demo" else "sim"
    mgmt = {**(req.mgmt or {}), "mode": mode}
    ft = ForwardTest(
        user_id    = _user_id(db, x_dev_user, authorization),
        name       = (req.name or req.graph.get("name") or "Forward test").strip()[:160],
        symbol     = req.symbol,
        timeframe  = req.timeframe,
        graph      = req.graph,
        mgmt       = mgmt,
        baseline   = req.baseline or {},
        started_at = datetime.utcnow(),
        status     = "active",
        latest     = {},
    )
    db.add(ft); db.commit(); db.refresh(ft)
    if mode == "sim":
        _refresh(ft, db)      # paper recompute once (Supabase mirror happens inside _refresh)
    else:
        from backend.api import supa as _supa
        _supa.upsert_forward_test(
            vps_id=ft.id, user_id=None, name=ft.name,
            symbol=ft.symbol, timeframe=ft.timeframe, graph=ft.graph,
            mgmt=ft.mgmt, baseline=ft.baseline,
            started_at=ft.started_at.isoformat() if ft.started_at else None,
            status=ft.status, latest=ft.latest,
        )
    return _summary(ft, db)


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
    return [_summary(ft, db) for ft in rows]


@router.get("/{ft_id}")
def forward_get(ft_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ft = db.get(ForwardTest, ft_id)
    if not ft:
        raise HTTPException(404, "Forward test not found.")
    return _summary(ft, db)


@router.post("/{ft_id}/refresh")
def forward_refresh(ft_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ft = db.get(ForwardTest, ft_id)
    if not ft:
        raise HTTPException(404, "Forward test not found.")
    if _mode(ft) == "sim":
        _refresh(ft, db)
    return _summary(ft, db)


@router.post("/{ft_id}/stop")
def forward_stop(ft_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ft = db.get(ForwardTest, ft_id)
    if not ft:
        raise HTTPException(404, "Forward test not found.")
    ft.status = "stopped"
    db.add(ft); db.commit()
    from backend.api import supa as _supa
    _supa.upsert_forward_test(
        vps_id=ft.id, user_id=None, name=ft.name,
        symbol=ft.symbol, timeframe=ft.timeframe, graph=ft.graph,
        mgmt=ft.mgmt, baseline=ft.baseline,
        started_at=ft.started_at.isoformat() if ft.started_at else None,
        status=ft.status, latest=ft.latest,
    )
    return _summary(ft, db)


# ─── Executor-facing endpoints (host worker ↔ VPS) ──────────────────────────
# The live executor runs on the MT5 host. It authenticates with the shared
# bridge secret (both ends already have it).
import os as _os

def _check_executor(token: Optional[str]) -> None:
    expected = _os.environ.get("BRIDGE_TOKEN", "").strip()
    if not expected:
        raise HTTPException(503, "Executor auth not configured on the server.")
    if not token or token != expected:
        raise HTTPException(401, "Invalid executor token.")


class LiveEvent(BaseModel):
    action:          str            # "open" | "close"
    symbol:          str = ""
    side:            str = ""
    volume:          float = 0.0
    requested_price: float = 0.0
    fill_price:      float = 0.0
    slippage:        float = 0.0
    spread:          float = 0.0
    sl:              float = 0.0
    tp:              float = 0.0
    ticket:          int = 0
    profit:          float = 0.0
    comment:         str = ""


@router.get("/live/active")
def live_active(x_executor_token: Optional[str] = Header(default=None, alias="X-Executor-Token"),
                db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Configs the executor needs: active Grade-3 (live_demo) tests."""
    _check_executor(x_executor_token)
    rows = db.query(ForwardTest).filter(ForwardTest.status == "active").all()
    out = []
    for ft in rows:
        if _mode(ft) != "live_demo":
            continue
        out.append({
            "id": ft.id, "symbol": ft.symbol, "timeframe": ft.timeframe,
            "graph": ft.graph, "mgmt": ft.mgmt or {},
            "started_at": ft.started_at.isoformat() if ft.started_at else None,
        })
    return out


@router.post("/{ft_id}/event")
def live_event(ft_id: int, ev: LiveEvent,
               x_executor_token: Optional[str] = Header(default=None, alias="X-Executor-Token"),
               db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Append a real fill to the immutable ledger (open or close)."""
    _check_executor(x_executor_token)
    from backend.db import LiveTrade
    ft = db.get(ForwardTest, ft_id)
    if not ft:
        raise HTTPException(404, "Forward test not found.")
    row = LiveTrade(
        forward_test_id = ft_id,
        ts              = datetime.utcnow(),
        action          = ev.action[:8],
        symbol          = ev.symbol[:32],
        side            = ev.side[:8],
        volume          = ev.volume,
        requested_price = ev.requested_price,
        fill_price      = ev.fill_price,
        slippage        = ev.slippage,
        spread          = ev.spread,
        sl              = ev.sl,
        tp              = ev.tp,
        ticket          = ev.ticket,
        profit          = ev.profit,
        comment         = ev.comment[:64],
    )
    db.add(row); db.commit()
    from backend.api import supa as _supa
    _supa.log_live_trade(
        vps_id=row.id, ft_vps_id=ft_id,
        ts=row.ts.isoformat() if row.ts else None,
        action=row.action, symbol=row.symbol, side=row.side,
        volume=row.volume, requested_price=row.requested_price,
        fill_price=row.fill_price, slippage=row.slippage,
        spread=row.spread, sl=row.sl, tp=row.tp,
        ticket=row.ticket, profit=row.profit, comment=row.comment,
    )
    return {"ok": True, "id": row.id}
