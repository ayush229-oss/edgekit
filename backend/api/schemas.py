"""
Pydantic request/response schemas for the Edgekit API.
Keep all wire formats in one place so frontend type-gen has a single source.
"""
from __future__ import annotations
from typing import Any, Optional, List, Tuple, Literal
from pydantic import BaseModel, Field


# ─── Strategy listing ────────────────────────────────────────────────────────
class ParamSpecOut(BaseModel):
    key:         str
    label:       str
    type:        str
    default:     Any
    min:         Optional[float] = None
    max:         Optional[float] = None
    step:        Optional[float] = None
    options:     Optional[List[Any]] = None
    description: str = ""
    group:       str = "General"


class StrategySummary(BaseModel):
    id:          str
    name:        str
    description: str
    timeframes:  List[str]
    instruments: List[str]
    params:      List[ParamSpecOut]


# ─── Backtest request ────────────────────────────────────────────────────────
class TPLevel(BaseModel):
    r:   float = Field(..., gt=0,    description="R-multiple, e.g. 2.0 = 2× risk")
    qty: float = Field(..., gt=0, le=1, description="Fraction of position to close, 0–1")


class BacktestRequest(BaseModel):
    strategy_id:     str
    data_source:     Literal["mt5", "csv", "upload"] = "mt5"
    symbol:          str   = "XAUUSD"
    timeframe:       str   = "M15"
    n_bars:          int   = 5000

    csv_data_id:     Optional[str] = None

    params:          dict[str, Any] = Field(default_factory=dict)

    # ── NEW: simple trade-management model ────────────────────────────────
    target_r:        Optional[float] = 3.0
    target_close_pct: float          = 1.0   # 0.0 = ride full position, 1.0 = full exit
    trail_mode:      Literal["none", "candle", "atr", "pips", "swing"] = "none"
    trail_start:     Literal["immediate", "after_target"] = "after_target"
    trail_params:    dict[str, Any] = Field(default_factory=dict)

    # ── LEGACY: TP ladder (kept for backward-compat) ──────────────────────
    tps:             List[TPLevel]  = Field(default_factory=list)
    trail_enabled:   bool           = False
    trail_from_idx:  int            = 2
    trail_buf_pips:  float          = 1.0

    # Order management
    max_concurrent:  int            = 1
    order_expiry:    Optional[int]  = None
    session_hours:   Optional[Tuple[int, int]] = None

    # Sizing
    initial_equity:  float          = 100.0
    risk_pct:        float          = 0.01
    max_risk_usd:    float          = 600.0


# ─── Backtest response ───────────────────────────────────────────────────────
class BacktestMetrics(BaseModel):
    trades:        int
    wr:            float
    ev:            float
    total_r:       float
    profit_factor: float
    max_dd:        float
    avg_win:       float
    avg_loss:      float
    final_equity:  float
    n_setups:      int
    n_unresolved:  int
    exit_counts:   dict[str, int]


class BacktestResponse(BaseModel):
    strategy_id:  str
    data_range:   Tuple[str, str]         # ISO start / end
    bars:         int
    pip:          float
    metrics:      BacktestMetrics
    equity_curve: List[float]
    pnl_series:   List[float]
    issues:       dict[str, Any] = Field(default_factory=dict)


# ─── CSV upload ──────────────────────────────────────────────────────────────
class CSVUploadResponse(BaseModel):
    data_id:    str
    bars:       int
    start:      str
    end:        str
    columns:    List[str]
    issues:     dict[str, Any] = Field(default_factory=dict)
    pip_guess:  float
