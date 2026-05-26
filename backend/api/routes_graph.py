"""
Visual-node-builder endpoints.

  GET  /graph/nodes              → full node library for the palette
  GET  /graph/templates          → list starter graphs (id + name + description)
  GET  /graph/templates/{id}     → fetch one full template graph
  POST /graph/backtest           → run a backtest against a custom graph
                                   (reuses the same trade-management model as /backtest)
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple, Literal
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.engine.builder import (
    NODE_LIBRARY, GraphStrategy, list_templates, get_template, validate_graph,
)
from backend.engine.core import (
    load_mt5, simulate, compute_metrics, infer_pip_from_df, validate_ohlcv,
)
from backend.api import store
from backend.api.schemas import BacktestResponse, BacktestMetrics
from backend.db import get_db, BacktestRun


router = APIRouter(prefix="/graph", tags=["graph"])


# ─── Node library ────────────────────────────────────────────────────────────
@router.get("/nodes")
def list_nodes() -> List[Dict[str, Any]]:
    """All nodes available to the builder palette."""
    return [spec.to_dict() for spec in NODE_LIBRARY.values()]


# ─── Templates ───────────────────────────────────────────────────────────────
@router.get("/templates")
def list_starter_templates() -> List[Dict[str, Any]]:
    return list_templates()


@router.get("/templates/{template_id}")
def get_starter_template(template_id: str) -> Dict[str, Any]:
    try:
        return get_template(template_id)
    except KeyError:
        raise HTTPException(404, f"Unknown template: {template_id}")


# ─── Backtest (graph-driven) ─────────────────────────────────────────────────
class GraphBacktestRequest(BaseModel):
    graph:           Dict[str, Any]
    # Data source (same shape as /backtest)
    data_source:     Literal["mt5", "upload"] = "mt5"
    symbol:          str  = "XAUUSD"
    timeframe:       str  = "M15"
    n_bars:          int  = 5000
    csv_data_id:     Optional[str] = None
    # Trade management (matches the panel we just shipped)
    target_r:         Optional[float] = 3.0
    target_close_pct: float           = 1.0
    trail_mode:       Literal["none", "candle", "atr", "pips", "swing"] = "none"
    trail_start:      Literal["immediate", "after_target"] = "after_target"
    trail_params:     Dict[str, Any]  = Field(default_factory=dict)
    # Sizing
    initial_equity:  float = 100.0
    risk_pct:        float = 0.01
    max_risk_usd:    float = 600.0
    # Order management
    max_concurrent:  int   = 1
    order_expiry:    Optional[int] = None
    session_hours:   Optional[Tuple[int, int]] = None


@router.post("/backtest", response_model=BacktestResponse)
def run_graph_backtest(
    req: GraphBacktestRequest,
    db:  Session = Depends(get_db),
    x_dev_user:    Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
):
    # 1) Validate graph early so the user gets a clear error
    try:
        graph = validate_graph(req.graph)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # 2) Soft-auth + quota (same pattern as /backtest)
    user = None
    try:
        from backend.api.auth import current_user as _cu
        user = _cu(db=db, x_dev_user=x_dev_user, authorization=authorization)
        from backend.api.limits import enforce_backtest_quota as _eq
        _eq(user=user, db=db)
    except HTTPException as e:
        if e.status_code == 401:
            user = None
        else:
            raise

    # 3) Resolve data
    if req.data_source == "mt5":
        try:
            df = load_mt5(req.symbol, req.timeframe, req.n_bars)
        except Exception as e:
            raise HTTPException(400, f"MT5 fetch failed: {e}")
    elif req.data_source == "upload":
        if not req.csv_data_id:
            raise HTTPException(400, "csv_data_id required when data_source = 'upload'")
        df = store.get(req.csv_data_id)
        if df is None:
            raise HTTPException(404, f"data_id {req.csv_data_id} not found (may have evicted)")
    else:
        raise HTTPException(400, f"Unsupported data_source: {req.data_source}")

    pip = infer_pip_from_df(df, req.symbol)
    strat  = GraphStrategy(graph)
    setups = strat.detect(df, {"pip": pip})

    tdf = simulate(
        df, setups,
        target_r         = req.target_r,
        target_close_pct = req.target_close_pct,
        trail_mode       = req.trail_mode,
        trail_start      = req.trail_start,
        trail_params     = req.trail_params,
        max_concurrent   = req.max_concurrent,
        order_expiry     = req.order_expiry,
        session_hours    = req.session_hours,
        pip              = pip,
    )
    m = compute_metrics(tdf,
                       initial_equity = req.initial_equity,
                       risk_pct       = req.risk_pct,
                       max_risk_usd   = req.max_risk_usd)
    if m is None:
        raise HTTPException(422, "No resolved trades — loosen the parameters or check the graph wiring.")

    # Persist for logged-in users
    if user is not None:
        try:
            db.add(BacktestRun(
                user_id         = user.id,
                strategy_id     = "graph:" + (graph.get("name") or "custom"),
                params_snapshot = {"graph": graph},
                metrics         = {
                    "trades": m["trades"], "wr": m["wr"], "ev": m["ev"],
                    "total_r": m["total_r"],
                    "profit_factor": (m["profit_factor"] if m["profit_factor"] != float("inf") else 99.0),
                    "max_dd": m["max_dd"], "final_equity": m["final_equity"],
                },
                symbol    = req.symbol,
                timeframe = req.timeframe,
                bars      = len(df),
            ))
            db.commit()
        except Exception:
            db.rollback()

    return BacktestResponse(
        strategy_id  = "graph:custom",
        data_range   = (df["time"].iloc[0].isoformat(), df["time"].iloc[-1].isoformat()),
        bars         = len(df),
        pip          = pip,
        metrics      = BacktestMetrics(
            trades        = m["trades"],
            wr            = m["wr"],
            ev            = m["ev"],
            total_r       = m["total_r"],
            profit_factor = (m["profit_factor"] if m["profit_factor"] != float("inf") else 99.0),
            max_dd        = m["max_dd"],
            avg_win       = m["avg_win"],
            avg_loss      = m["avg_loss"],
            final_equity  = m["final_equity"],
            n_setups      = m["n_setups"],
            n_unresolved  = m["n_unresolved"],
            exit_counts   = {str(k): int(v) for k, v in m["exit_counts"].items()},
        ),
        equity_curve = m["curve"].tolist(),
        pnl_series   = m["pnl"].tolist(),
        issues       = validate_ohlcv(df),
    )
