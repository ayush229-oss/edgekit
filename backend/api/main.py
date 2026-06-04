"""
Edgekit FastAPI service.

Endpoints:
  GET  /strategies                  → list all strategy templates + their param schemas
  GET  /strategies/{strategy_id}    → one strategy (404 if unknown)
  POST /upload-csv                  → upload an OHLCV CSV, returns a data_id
  POST /backtest                    → run a backtest, returns metrics + curves
  GET  /healthz                     → liveness

Run locally:
  uvicorn backend.api.main:app --reload --port 8000
"""
from __future__ import annotations
from typing import Optional
from pathlib import Path
import dotenv  # type: ignore[import-untyped]

# Load backend/.env before any module reads os.environ
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
import io

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import traceback
from sqlalchemy.orm import Session
import pandas as pd

from backend.engine.core import (
    load_csv, load_mt5, simulate, compute_metrics,
    infer_pip_from_df, validate_ohlcv,
)
from backend.engine.strategies import REGISTRY, get as get_strategy, list_all
from backend.api import store
from backend.api.schemas import (
    StrategySummary, ParamSpecOut,
    BacktestRequest, BacktestResponse, BacktestMetrics,
    CSVUploadResponse,
)
from backend.api.auth    import current_user
from backend.api.limits  import enforce_backtest_quota, require_csv_upload
from backend.api.billing import router as billing_router
from backend.api.routes_user import router as user_router
from backend.api.preview import router as preview_router
from backend.api.routes_graph_v2 import router as graph_v2_router
from backend.api.routes_forward  import router as forward_router, start_forward_scheduler
from backend.db import get_db, init_db, BacktestRun, User

app = FastAPI(
    title="Edgekit API",
    version="0.1.0",
    description="No-code strategy backtesting platform — backend.",
)

# ── Sentry error tracking ────────────────────────────────────────────────────
import os as _os
_SENTRY_DSN = _os.environ.get("SENTRY_DSN", "")
if _SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            traces_sample_rate=0.1,   # 10% of requests traced
            profiles_sample_rate=0.1,
        )
    except ImportError:
        pass   # sentry-sdk not installed — silently skip

# ── VPS deploy webhook (CI calls this instead of SSH) ────────────────────────
# Triggered by GitHub Actions on push to main. Pulls latest code and restarts.
# No secret needed — deploy only does `git clone` from a public repo.
_DEPLOY_SCRIPT = "/opt/edgekit/scripts/vps_deploy.sh"

@app.post("/internal/deploy", include_in_schema=False)
async def trigger_deploy():
    import subprocess
    try:
        # Use systemd-run to launch in its own transient cgroup so it survives
        # the `systemctl restart edgekit-backend` that the script runs.
        proc = subprocess.Popen(
            ["systemd-run", "--no-block", "--description=edgekit-deploy",
             "/bin/bash", _DEPLOY_SCRIPT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"ok": True, "pid": proc.pid, "message": "deploy started via systemd-run"}
    except Exception as e:
        raise HTTPException(500, f"Deploy failed to start: {e}")

# ── CORS — locked to known origins (override via CORS_ORIGINS env var) ───────
_DEFAULT_ORIGINS = "https://edgekit.uk,https://www.edgekit.uk,http://localhost:3000,http://127.0.0.1:3000"
_CORS_ORIGINS = [o.strip() for o in _os.environ.get("CORS_ORIGINS", _DEFAULT_ORIGINS).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Shared-secret API key ─────────────────────────────────────────────────────
# The VPS is publicly reachable on :8765. Require a secret header on every
# request so only our Vercel frontend (which injects it server-side) can call.
#
# FAIL-OPEN: if EDGEKIT_API_KEY is not set, enforcement is disabled. This lets
# us deploy this code with zero behaviour change, then flip protection on by
# setting the env var last (and unset it for an instant rollback).
#
# /healthz stays public so uptime monitors (UptimeRobot) can probe it.
_API_KEY = _os.environ.get("EDGEKIT_API_KEY", "")
_KEY_PUBLIC_PATHS = {"/healthz"}

@app.middleware("http")
async def _require_api_key(request: Request, call_next):
    if (
        _API_KEY
        and request.method != "OPTIONS"                  # never block CORS preflight
        and request.url.path not in _KEY_PUBLIC_PATHS
    ):
        if request.headers.get("x-api-key") != _API_KEY:
            origin = request.headers.get("origin", "*")
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid API key"},
                headers={
                    "Access-Control-Allow-Origin":      origin,
                    "Access-Control-Allow-Credentials": "true",
                },
            )
    return await call_next(request)

# Initialize DB tables + start the forward-test refresh loop on startup
@app.on_event("startup")
def _startup():
    init_db()
    start_forward_scheduler()

# Mount sub-routers
app.include_router(billing_router)
app.include_router(user_router)
app.include_router(preview_router)
app.include_router(graph_v2_router)
app.include_router(forward_router)


# ─── Global exception handler ────────────────────────────────────────────────
# When an unhandled exception escapes a route, FastAPI's default 500 response
# bypasses CORSMiddleware → browser sees no Allow-Origin header and reports a
# misleading "CORS policy" error. Catch every uncaught exception here and
# return JSONResponse so CORS middleware applies and the real error reaches
# the frontend.
@app.exception_handler(Exception)
async def _unhandled_exception(request: Request, exc: Exception):
    traceback.print_exc()
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
        headers={
            "Access-Control-Allow-Origin":      origin,
            "Access-Control-Allow-Credentials": "true",
        },
    )


# ─── Health ──────────────────────────────────────────────────────────────────
@app.get("/healthz")
def healthz():
    from backend.api.cache import backtest_cache
    return {
        "ok":         True,
        "strategies": len(REGISTRY),
        "store":      store.stats(),
        "cache":      backtest_cache.stats(),
    }


# ─── Global stats (landing page counters) ─────────────────────────────────────
@app.get("/stats/global")
def global_stats(db: Session = Depends(get_db)):
    """Total backtests run + total registered users. Cached by ISR on the frontend."""
    from sqlalchemy import func
    total_backtests = db.query(func.count(BacktestRun.id)).scalar() or 0
    total_users     = db.query(func.count(User.id)).scalar() or 0
    return {"total_backtests": int(total_backtests), "total_users": int(total_users)}


# ─── Strategies ──────────────────────────────────────────────────────────────
@app.get("/strategies", response_model=list[StrategySummary])
def list_strategies():
    out: list[StrategySummary] = []
    for sid, cls in REGISTRY.items():
        out.append(StrategySummary(
            id          = sid,
            name        = cls.name,
            description = cls.description,
            timeframes  = list(cls.timeframes),
            instruments = list(cls.instruments),
            params      = [ParamSpecOut(**p.__dict__) for p in cls.param_schema],
        ))
    return out


@app.get("/strategies/{strategy_id}", response_model=StrategySummary)
def get_strategy_detail(strategy_id: str):
    try:
        cls = get_strategy(strategy_id)
    except KeyError:
        raise HTTPException(404, f"Unknown strategy: {strategy_id}")
    return StrategySummary(
        id          = strategy_id,
        name        = cls.name,
        description = cls.description,
        timeframes  = list(cls.timeframes),
        instruments = list(cls.instruments),
        params      = [ParamSpecOut(**p.__dict__) for p in cls.param_schema],
    )


# ─── CSV upload (Trader+ gated in prod; open in dev) ───────────────────────
@app.post("/upload-csv", response_model=CSVUploadResponse)
async def upload_csv(
    file:   UploadFile = File(...),
    symbol: Optional[str] = Form(None),
):
    raw = await file.read()
    try:
        df = load_csv(raw)
    except Exception as e:
        raise HTTPException(400, f"CSV parse failed: {e}")
    issues   = validate_ohlcv(df)
    pip      = infer_pip_from_df(df, symbol)
    data_id  = store.put(df)
    store.evict_oldest()
    return CSVUploadResponse(
        data_id   = data_id,
        bars      = len(df),
        start     = df["time"].iloc[0].isoformat(),
        end       = df["time"].iloc[-1].isoformat(),
        columns   = list(df.columns),
        issues    = issues,
        pip_guess = pip,
    )


# ─── Backtest ────────────────────────────────────────────────────────────────
@app.post("/backtest", response_model=BacktestResponse)
def run_backtest(
    req:  BacktestRequest,
    db:   Session = Depends(get_db),
    # Soft-auth: if a user identifies themselves we enforce quota + log the run.
    # Anonymous requests still work in dev for quick iteration.
    x_dev_user:    Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
):
    # Best-effort identify the caller (don't fail if anonymous)
    user = None
    try:
        from backend.api.auth import current_user as _cu
        user = _cu(db=db, x_dev_user=x_dev_user, authorization=authorization)
        # Now enforce quota
        from backend.api.limits import enforce_backtest_quota as _eq
        _eq(user=user, db=db)
    except HTTPException as e:
        if e.status_code in (401,):
            user = None    # anonymous — allowed in dev
        else:
            raise
    # 1) Resolve data
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

    # 2) Resolve pip + params
    pip = infer_pip_from_df(df, req.symbol)
    try:
        Strat = get_strategy(req.strategy_id)
    except KeyError:
        raise HTTPException(404, f"Unknown strategy: {req.strategy_id}")
    strat = Strat()

    params = {**strat.default_params(), **req.params, "pip": pip}
    tps    = [(t.r, t.qty) for t in req.tps] if req.tps else None
    if tps:
        params["tps"] = tps

    # 3) Detect + simulate
    setups = strat.detect(df, params)
    tdf    = simulate(
        df, setups,
        # ── New simple management model ─────────────────────────────────
        target_r         = req.target_r,
        target_close_pct = req.target_close_pct,
        trail_mode       = req.trail_mode,
        trail_start      = req.trail_start,
        trail_params     = req.trail_params,
        # ── Legacy ladder (still works if caller passes tps) ────────────
        trail_enabled  = req.trail_enabled,
        trail_from_idx = req.trail_from_idx,
        trail_buf_pips = req.trail_buf_pips,
        # ── Order mgmt ──────────────────────────────────────────────────
        max_concurrent = req.max_concurrent,
        order_expiry   = req.order_expiry,
        session_hours  = req.session_hours,
        pip            = pip,
    )
    m = compute_metrics(tdf,
                       initial_equity = req.initial_equity,
                       risk_pct       = req.risk_pct,
                       max_risk_usd   = req.max_risk_usd)
    if m is None:
        raise HTTPException(422, "No resolved trades — loosen the parameters.")

    # Persist the run — always, so global stats count every backtest
    try:
        run_row = BacktestRun(
            user_id         = user.id if user is not None else None,
            strategy_id     = req.strategy_id,
            params_snapshot = {**params, "tps": tps or params.get("tps") or []},
            metrics         = {
                "trades": m["trades"], "wr": m["wr"], "ev": m["ev"],
                "total_r": m["total_r"], "profit_factor":
                    (m["profit_factor"] if m["profit_factor"] != float("inf") else 99.0),
                "max_dd": m["max_dd"], "final_equity": m["final_equity"],
            },
            symbol    = req.symbol,
            timeframe = req.timeframe,
            bars      = len(df),
        )
        db.add(run_row); db.commit()
    except Exception:
        db.rollback()    # don't fail the request just because logging broke

    return BacktestResponse(
        strategy_id  = req.strategy_id,
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
