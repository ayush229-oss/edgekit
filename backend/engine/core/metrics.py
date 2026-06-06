"""
Strategy-agnostic performance metrics for a completed trade log.
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd


def compute_metrics(
    tdf: pd.DataFrame,
    *,
    initial_equity: float = 100.0,
    risk_pct: float = 0.01,
    max_risk_usd: float = 600.0,
    bars_per_year: float = 252.0,   # trading days; used for annualised ratios
) -> Optional[Dict[str, Any]]:
    """
    Compute headline + supporting metrics for a trade log.

    Returns None when the log has no resolved trades.

    Metrics returned
    ----------------
    trades, wr, ev, total_r, max_dd, profit_factor,
    avg_win, avg_loss, avg_rr, final_equity,
    sharpe, sortino, calmar, cagr,
    curve, pnl, exit_counts, n_setups, n_unresolved
    """
    if tdf is None or tdf.empty:
        return None
    res = tdf[tdf["result"] != "Unresolved"].copy()
    if res.empty:
        return None

    pnl    = res["pnl_r"].values
    wins   = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    wr     = len(wins) / len(pnl) * 100.0
    ev     = float(np.mean(pnl))
    total  = float(np.sum(pnl))
    avg_rr = (float(abs(wins.mean()) / abs(losses.mean()))
              if len(wins) and len(losses) and losses.mean() != 0 else float("nan"))

    # ── Equity curve ─────────────────────────────────────────────────────
    eq    = initial_equity
    curve = [eq]
    for r in pnl:
        risk_usd = min(eq * risk_pct, max_risk_usd)
        eq += r * risk_usd
        curve.append(eq)
    curve = np.array(curve)

    peak   = np.maximum.accumulate(curve)
    dd_pct = (curve - peak) / peak * 100.0
    max_dd = float(dd_pct.min())

    pf = (abs(float(wins.sum()) / float(losses.sum()))
          if len(losses) and losses.sum() != 0 else float("inf"))

    # ── Period returns (per-trade equity returns) ─────────────────────────
    rets = np.diff(curve) / curve[:-1]   # per-trade % returns

    # ── Sharpe ratio (annualised, using trade count as frequency proxy) ───
    if len(rets) > 1 and rets.std() > 0:
        trades_per_year = max(len(rets), 1)
        scale = np.sqrt(trades_per_year)   # annualise by trade count
        sharpe = float(rets.mean() / rets.std() * scale)
    else:
        sharpe = float("nan")

    # ── Sortino ratio (downside deviation only) ───────────────────────────
    down = rets[rets < 0]
    if len(down) > 1 and down.std() > 0:
        sortino = float(rets.mean() / down.std() * np.sqrt(max(len(rets), 1)))
    else:
        sortino = float("nan")

    # ── CAGR (use fill/exit timestamps when available, else trade count) ──
    cagr = float("nan")
    try:
        if "fill_idx" in res.columns and "exit_idx" in res.columns:
            first_fill = res["fill_idx"].dropna().min()
            last_exit  = res["exit_idx"].dropna().max()
            if pd.notna(first_fill) and pd.notna(last_exit):
                span_bars = float(last_exit) - float(first_fill)
                if span_bars > 0:
                    years = span_bars / bars_per_year
                    cagr  = float((curve[-1] / curve[0]) ** (1.0 / years) - 1) * 100
    except Exception:
        pass

    # ── Calmar ratio = CAGR / |MaxDD| ────────────────────────────────────
    calmar = float("nan")
    if not np.isnan(cagr) and max_dd < 0:
        calmar = cagr / abs(max_dd)

    exit_counts = (res["exit_type"].value_counts().to_dict()
                   if "exit_type" in res.columns else {})

    return dict(
        trades        = len(pnl),
        wr            = wr,
        ev            = ev,
        total_r       = total,
        max_dd        = max_dd,
        profit_factor = pf,
        avg_win       = float(wins.mean())   if len(wins)   else 0.0,
        avg_loss      = float(losses.mean()) if len(losses) else 0.0,
        avg_rr        = avg_rr,
        sharpe        = sharpe,
        sortino       = sortino,
        calmar        = calmar,
        cagr          = cagr,
        final_equity  = float(curve[-1]),
        curve         = curve,
        pnl           = pnl,
        exit_counts   = exit_counts,
        n_setups      = len(tdf),
        n_unresolved  = int((tdf["result"] == "Unresolved").sum()),
    )


def compute_challenge_result(
    tdf: pd.DataFrame,
    df:  pd.DataFrame,
    challenge: Dict[str, Any],
    *,
    risk_pct:     float = 0.01,
    max_risk_usd: float = 600.0,
) -> Optional[Dict[str, Any]]:
    """
    Replay the trade log against prop firm challenge rules and return a
    pass/fail verdict with a day-by-day breakdown.

    challenge keys:
        account_size          float   e.g. 10000
        daily_loss_limit_pct  float   e.g. 5.0  (5% of account)
        max_drawdown_pct      float   e.g. 10.0 (10% of account)
        profit_target_pct     float   e.g. 10.0 (10% of account)
        min_trading_days      int     e.g. 4
    """
    resolved = tdf[tdf["result"] != "Unresolved"].copy()
    if resolved.empty:
        return None

    account_size  = float(challenge.get("account_size", 10000))
    daily_loss_limit = account_size * float(challenge.get("daily_loss_limit_pct", 5)) / 100
    max_dd_usd    = account_size * float(challenge.get("max_drawdown_pct",  10)) / 100
    profit_target = account_size * float(challenge.get("profit_target_pct", 10)) / 100
    min_days      = int(challenge.get("min_trading_days", 4))

    dates = df["time"].dt.date.values
    n = len(dates)

    def _exit_date(idx):
        if idx is None or (isinstance(idx, float) and np.isnan(idx)):
            return None
        i = int(idx)
        return dates[i] if 0 <= i < n else None

    resolved = resolved.copy()
    resolved["exit_date"] = resolved["exit_idx"].apply(_exit_date)
    resolved = resolved.dropna(subset=["exit_date"])
    if resolved.empty:
        return None

    eq        = account_size
    peak_eq   = account_size
    day_start = account_size

    failure_day   = None
    failure_rule  = None
    profit_hit_day = None
    trading_days  = set()
    daily: List[Dict[str, Any]] = []

    for date, group in resolved.groupby("exit_date", sort=True):
        if failure_day is not None:
            break

        trading_days.add(date)
        day_pnl = 0.0

        for _, trade in group.iterrows():
            risk_usd = min(eq * risk_pct, max_risk_usd)
            pnl_usd  = float(trade["pnl_r"]) * risk_usd
            eq      += pnl_usd
            day_pnl += pnl_usd

        peak_eq = max(peak_eq, eq)
        status  = "ok"

        # Daily loss check (loss from day-start equity)
        if (day_start - eq) >= daily_loss_limit:
            failure_rule = f"Daily loss limit ({challenge.get('daily_loss_limit_pct', 5)}%) breached"
            failure_day  = str(date)
            status       = "fail"

        # Max drawdown from peak
        elif (peak_eq - eq) >= max_dd_usd:
            failure_rule = f"Max drawdown ({challenge.get('max_drawdown_pct', 10)}%) breached"
            failure_day  = str(date)
            status       = "fail"

        # Profit target
        elif profit_hit_day is None and (eq - account_size) >= profit_target:
            profit_hit_day = str(date)
            status         = "target_hit"

        daily.append({"date": str(date), "pnl_usd": round(day_pnl, 2),
                      "equity": round(eq, 2), "status": status})
        day_start = eq

    n_days = len(trading_days)

    if failure_day is not None:
        passed  = False
        verdict = f"Failed — {failure_rule}"
    elif profit_hit_day is not None and n_days >= min_days:
        passed  = True
        verdict = "Passed — profit target reached"
    elif profit_hit_day is not None:
        passed  = False
        verdict = f"Target reached but only {n_days}/{min_days} trading days completed"
    else:
        gain_pct = (eq - account_size) / account_size * 100
        verdict  = (
            f"Incomplete — {gain_pct:.1f}% gained, "
            f"need {challenge.get('profit_target_pct', 10)}%"
        )
        passed = False

    return dict(
        passed         = passed,
        verdict        = verdict,
        failure_rule   = failure_rule,
        failure_day    = failure_day,
        profit_hit_day = profit_hit_day,
        trading_days   = n_days,
        final_equity   = round(eq, 2),
        account_size   = account_size,
        daily          = daily,
    )
