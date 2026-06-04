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

Supabase is the sole source of truth for forward_tests and live_trades.
SQLite is only used for user auth lookups (users table stays on SQLite).
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.engine.core import (
    load_mt5, simulate, compute_metrics, infer_pip_from_df, data_source_of,
)
from backend.engine.builder_v2.engine import GraphV2Strategy

router = APIRouter(prefix="/forward", tags=["forward"])

FORWARD_NBARS   = 6000
REFRESH_SECONDS = 300


# ─── Core: run the strategy + isolate the forward (post-start) trades ────────
def _parse_dt(s) -> datetime:
    if s is None:
        return datetime.utcnow()
    if isinstance(s, datetime):
        return s.replace(tzinfo=None) if getattr(s, "tzinfo", None) else s
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt.replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()


class _FTProxy:
    """Duck-type of ForwardTest with only the fields _compute_latest needs."""
    __slots__ = ("symbol", "timeframe", "graph", "mgmt", "started_at", "latest")
    def __init__(self, row: dict):
        self.symbol     = row.get("symbol", "XAUUSD")
        self.timeframe  = row.get("timeframe", "M15")
        self.graph      = row.get("graph") or {}
        self.mgmt       = row.get("mgmt") or {}
        self.started_at = _parse_dt(row.get("started_at"))
        self.latest     = row.get("latest") or {}


def _compute_latest(ft) -> Dict[str, Any]:
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

    times     = df["time"]
    n         = len(df)
    started   = ft.started_at
    bars_seen = int((times >= started).sum())

    def _fill_time(fi):
        if fi is None:
            return None
        try:
            i = int(fi)
        except (TypeError, ValueError):
            return None
        return times.iloc[i] if 0 <= i < n else None

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


def _refresh_supa(row: dict) -> None:
    """Refresh a forward test — compute latest and write back to Supabase only."""
    from backend.api import supa as _supa
    supa_id = row["id"]
    try:
        new_latest = _compute_latest(_FTProxy(row))
        _supa.update("forward_tests", {"id": supa_id}, {
            "latest":     new_latest,
            "updated_at": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        cur = dict(row.get("latest") or {})
        cur["error"]    = f"{type(e).__name__}: {str(e)[:200]}"
        cur["last_run"] = datetime.utcnow().isoformat()
        try:
            _supa.update("forward_tests", {"id": supa_id}, {"latest": cur})
        except Exception:
            pass


# ─── Background scheduler ────────────────────────────────────────────────────
_scheduler_started = False

def start_forward_scheduler() -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    def _loop():
        time.sleep(20)
        while True:
            try:
                from backend.api import supa as _supa
                if _supa.enabled():
                    active = _supa.select("forward_tests", {"status": "eq.active"})
                    for row in active:
                        if (row.get("mgmt") or {}).get("mode", "sim") == "sim":
                            _refresh_supa(row)
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
    mode:      str = "sim"
    mgmt:      Dict[str, Any] = Field(default_factory=dict)
    baseline:  Dict[str, Any] = Field(default_factory=dict)


# ─── Supabase-native summary helpers ─────────────────────────────────────────
def _supa_live_rollup(ft_ext_id: int) -> Dict[str, Any]:
    """Read live-trade ledger from Supabase (keyed by ft_vps_id / external id)."""
    from backend.api import supa as _supa
    rows   = _supa.get_live_trades(ft_ext_id)
    opens  = [r for r in rows if r.get("action") == "open"]
    closes = [r for r in rows if r.get("action") == "close"]
    n      = len(closes)
    wins   = [r for r in closes if (r.get("profit") or 0) > 0]
    total_profit = float(sum(r.get("profit") or 0 for r in closes))
    return {
        "mode": "live_demo",
        "metrics": {
            "trades":         n,
            "wr":             (len(wins) / n * 100.0) if n else 0.0,
            "total_profit":   total_profit,
            "open_positions": max(0, len(opens) - len(closes)),
        },
        "costs": {
            "total_spread":   float(sum(r.get("spread") or 0 for r in opens)),
            "total_slippage": float(sum(abs(r.get("slippage") or 0) for r in opens)),
        },
        "trades": [{
            "side": r.get("side"), "fill_price": r.get("fill_price"),
            "profit": r.get("profit"), "spread": r.get("spread"),
            "slippage": r.get("slippage"), "time": r.get("ts"),
        } for r in closes[-100:]],
        "events":   len(rows),
        "last_run": rows[-1].get("ts") if rows else None,
    }


def _supa_summary(row: dict) -> Dict[str, Any]:
    mgmt       = row.get("mgmt") or {}
    mode       = mgmt.get("mode", "sim")
    ext_id     = row.get("vps_id") or row["id"]   # vps_id for old tests, supa id for new
    if mode == "live_demo":
        try:
            latest: Any = _supa_live_rollup(ext_id)
        except Exception:
            latest = row.get("latest") or {}
    else:
        latest = row.get("latest") or {}
    return {
        "id":         ext_id,
        "name":       row.get("name", ""),
        "symbol":     row.get("symbol", ""),
        "timeframe":  row.get("timeframe", ""),
        "mode":       mode,
        "status":     row.get("status", ""),
        "started_at": row.get("started_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "baseline":   row.get("baseline") or {},
        "latest":     latest,
    }


def _get_row(ft_id: int) -> Optional[dict]:
    """Fetch a forward test from Supabase by external id (vps_id or supa id)."""
    from backend.api import supa as _supa
    return _supa.get_forward_test(ft_id) or _supa.get_forward_test_by_id(ft_id)


def _clerk_id(db: Session, x_dev_user: Optional[str], authorization: Optional[str]) -> Optional[str]:
    try:
        from backend.api.auth import current_user
        u = current_user(db=db, x_dev_user=x_dev_user, authorization=authorization)
        return u.clerk_id if u else None
    except Exception:
        return None


# ─── API endpoints ────────────────────────────────────────────────────────────
@router.post("/start")
def forward_start(
    req: ForwardStartRequest,
    db: Session = Depends(get_db),
    x_dev_user:    Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    if not req.graph or not req.graph.get("nodes"):
        raise HTTPException(400, "A strategy graph with nodes is required.")
    try:
        GraphV2Strategy(req.graph)
    except Exception as e:
        raise HTTPException(422, f"Strategy isn't valid yet: {e}")

    mode     = "live_demo" if req.mode == "live_demo" else "sim"
    mgmt     = {**(req.mgmt or {}), "mode": mode}
    cid      = _clerk_id(db, x_dev_user, authorization)
    now_iso  = datetime.utcnow().isoformat()

    from backend.api import supa as _supa
    row = _supa.insert("forward_tests", {
        "user_id":    cid,
        "name":       (req.name or req.graph.get("name") or "Forward test").strip()[:160],
        "symbol":     req.symbol,
        "timeframe":  req.timeframe,
        "graph":      req.graph,
        "mgmt":       mgmt,
        "baseline":   req.baseline or {},
        "started_at": now_iso,
        "status":     "active",
        "latest":     {},
    }, return_row=True)

    if not row:
        raise HTTPException(500, "Failed to create forward test.")

    if mode == "sim":
        _refresh_supa(row)
        row = _supa.get_forward_test_by_id(row["id"]) or row

    return _supa_summary(row)


@router.get("/list")
def forward_list(
    db: Session = Depends(get_db),
    x_dev_user:    Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> List[Dict[str, Any]]:
    cid = _clerk_id(db, x_dev_user, authorization)
    from backend.api import supa as _supa
    try:
        rows = _supa.select("forward_tests", {
            "user_id": f"eq.{cid}" if cid else "is.null",
            "order":   "created_at.desc",
        })
        return [_supa_summary(r) for r in rows]
    except Exception:
        return []


@router.get("/{ft_id}")
def forward_get(ft_id: int) -> Dict[str, Any]:
    row = _get_row(ft_id)
    if not row:
        raise HTTPException(404, "Forward test not found.")
    return _supa_summary(row)


@router.post("/{ft_id}/refresh")
def forward_refresh(ft_id: int) -> Dict[str, Any]:
    row = _get_row(ft_id)
    if not row:
        raise HTTPException(404, "Forward test not found.")
    if (row.get("mgmt") or {}).get("mode", "sim") == "sim":
        _refresh_supa(row)
        from backend.api import supa as _supa
        row = _supa.get_forward_test_by_id(row["id"]) or row
    return _supa_summary(row)


@router.post("/{ft_id}/stop")
def forward_stop(ft_id: int) -> Dict[str, Any]:
    row = _get_row(ft_id)
    if not row:
        raise HTTPException(404, "Forward test not found.")
    from backend.api import supa as _supa
    _supa.update("forward_tests", {"id": row["id"]}, {"status": "stopped"})
    row = dict(row); row["status"] = "stopped"
    return _supa_summary(row)


# ─── Executor-facing endpoints (host worker ↔ VPS) ──────────────────────────
import os as _os

def _check_executor(token: Optional[str]) -> None:
    expected = _os.environ.get("BRIDGE_TOKEN", "").strip()
    if not expected:
        raise HTTPException(503, "Executor auth not configured on the server.")
    if not token or token != expected:
        raise HTTPException(401, "Invalid executor token.")


class LiveEvent(BaseModel):
    action:          str
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
def live_active(
    x_executor_token: Optional[str] = Header(default=None, alias="X-Executor-Token"),
) -> List[Dict[str, Any]]:
    """Active Grade-3 (live_demo) test configs for the executor."""
    _check_executor(x_executor_token)
    from backend.api import supa as _supa
    try:
        rows = _supa.select("forward_tests", {"status": "eq.active"})
    except Exception:
        rows = []
    out = []
    for row in rows:
        mgmt = row.get("mgmt") or {}
        if mgmt.get("mode", "sim") != "live_demo":
            continue
        out.append({
            "id":         row.get("vps_id") or row["id"],
            "symbol":     row.get("symbol"),
            "timeframe":  row.get("timeframe"),
            "graph":      row.get("graph"),
            "mgmt":       mgmt,
            "started_at": row.get("started_at"),
        })
    return out


@router.post("/{ft_id}/event")
def live_event(
    ft_id: int,
    ev: LiveEvent,
    x_executor_token: Optional[str] = Header(default=None, alias="X-Executor-Token"),
) -> Dict[str, Any]:
    """Append a real fill to the immutable live-trade ledger."""
    _check_executor(x_executor_token)
    supa_ft = _get_row(ft_id)
    if not supa_ft:
        raise HTTPException(404, "Forward test not found.")
    supa_ft_id = supa_ft["id"]
    ft_ext_id  = supa_ft.get("vps_id") or supa_ft_id
    from backend.api import supa as _supa
    result = _supa.insert("live_trades", {
        "forward_test_id": supa_ft_id,
        "ft_vps_id":       ft_ext_id,
        "ts":              datetime.utcnow().isoformat(),
        "action":          ev.action[:8],
        "symbol":          ev.symbol[:32],
        "side":            ev.side[:8],
        "volume":          ev.volume,
        "requested_price": ev.requested_price,
        "fill_price":      ev.fill_price,
        "slippage":        ev.slippage,
        "spread":          ev.spread,
        "sl":              ev.sl,
        "tp":              ev.tp,
        "ticket":          ev.ticket,
        "profit":          ev.profit,
        "comment":         ev.comment[:64],
    }, return_row=True)
    return {"ok": True, "id": (result or {}).get("id")}
