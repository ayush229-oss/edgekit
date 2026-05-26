"""
Universal strategy simulator. Strategy-agnostic — works with any setup list.

TRADE EXECUTION MODEL (matches user mental model):
    1. Pending limit order is placed at `entry`
    2. When price touches entry, order fills
    3. If price hits `sl` first → -1R loss, move on
    4. If price goes in profit → reach `target_r` × risk = take profit
    5. If trailing is enabled, instead of (or after) the fixed target,
       the SL trails behind price using one of several modes:
         - 'candle'    : behind each new bar's low/high + buffer pips
         - 'atr'       : behind close by atr_mult × current ATR
         - 'pips'      : behind close by a fixed pip distance
         - 'swing'     : behind the most recent swing low/high

A setup dict must contain:
    signal_idx:  int            bar at which setup becomes available
    direction:   'Bull' | 'Bear'
    entry:       float          limit order price
    sl:          float          initial stop loss
    risk:        float          |entry - sl|, pre-computed
    tps:         list[(price, qty_fraction)]   (LEGACY) take-profit ladder
    liq_level:   float          (optional) for dedup
    meta:        dict           (optional) anything else for display

Trade management params can ALSO be passed via the simpler `target_r` / `trail_*`
kwargs — they take precedence over per-setup `tps` when provided.

Outputs a DataFrame of completed trades.
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple, Literal
import pandas as pd
import numpy as np


TrailMode = Literal["none", "candle", "atr", "pips", "swing"]


def _atr_series(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    """Compute ATR inline (kept here so simulator stays self-contained)."""
    H, L, C = df["H"].values, df["L"].values, df["C"].values
    prev_c  = np.concatenate(([C[0]], C[:-1]))
    tr      = np.maximum.reduce([H - L, np.abs(H - prev_c), np.abs(L - prev_c)])
    out     = np.zeros(len(df))
    alpha   = 1.0 / period
    out[0]  = tr[0]
    for i in range(1, len(tr)):
        out[i] = alpha * tr[i] + (1 - alpha) * out[i - 1]
    return out


def _swing_lows(df: pd.DataFrame, length: int) -> np.ndarray:
    """For each bar, the most recent swing low at or before bar i (NaN if none)."""
    L = df["L"].values
    n = len(L)
    result = np.full(n, np.nan)
    for i in range(length, n - length):
        # rolling check costs nothing at this scale
        if L[i] == L[max(0, i-length):i+length+1].min():
            result[i] = L[i]
    # forward-fill
    last = np.nan
    for i in range(n):
        if not np.isnan(result[i]): last = result[i]
        result[i] = last
    return result


def _swing_highs(df: pd.DataFrame, length: int) -> np.ndarray:
    H = df["H"].values
    n = len(H)
    result = np.full(n, np.nan)
    for i in range(length, n - length):
        if H[i] == H[max(0, i-length):i+length+1].max():
            result[i] = H[i]
    last = np.nan
    for i in range(n):
        if not np.isnan(result[i]): last = result[i]
        result[i] = last
    return result


def simulate(
    df: pd.DataFrame,
    setups: List[Dict[str, Any]],
    *,
    # ── New simpler trade-management model ─────────────────────────────────
    target_r:        Optional[float] = None,   # single TP at this R-multiple
    target_close_pct: float          = 1.0,    # 0.0 = ride full position, 1.0 = full exit
    trail_mode:      TrailMode       = "none",
    trail_start:     Literal["immediate", "after_target"] = "after_target",
    trail_params:    Optional[Dict[str, Any]] = None,
    # ── Legacy ladder mode (still supported) ───────────────────────────────
    trail_enabled:   bool  = False,
    trail_from_idx:  int   = 2,
    trail_buf_pips:  float = 1.0,
    # ── Order management ───────────────────────────────────────────────────
    max_concurrent:  int   = 1,
    order_expiry:    Optional[int] = None,
    session_hours:   Optional[Tuple[int, int]] = None,
    pip:             float = 0.10,
    dedup_key_fn = None,
) -> pd.DataFrame:
    """
    Run a backtest given pre-detected setups.

    Parameters
    ----------
    df              OHLCV DataFrame (must include time, O, H, L, C)
    setups          list of setup dicts (see module docstring)
    max_concurrent  max open trades at any moment
    order_expiry    cancel pending limit orders after N bars (None = never)
    session_hours   (start_hour, end_hour) — only fill in this window (None = always)
    trail_enabled   whether to trail SL after a chosen TP fires
    trail_from_idx  start trailing AFTER this TP index is hit (0-based)
    trail_buf_pips  pips behind each new candle wick when trailing
    pip             pip size for the instrument (default 0.10 for XAUUSD)
    dedup_key_fn    callable(setup) -> hashable. Default dedups by (direction, liq_level rounded).
    """
    trail_buf = trail_buf_pips * pip
    H, L = df["H"].values, df["L"].values
    hours = df["time"].dt.hour.values
    n = len(df)

    if dedup_key_fn is None:
        def dedup_key_fn(s):
            return (s["direction"], round(s.get("liq_level", s["entry"]), 2))

    # ── New trade-management model: override per-setup tps with target_r ──
    tp_params  = trail_params or {}
    use_new    = target_r is not None or trail_mode != "none"
    atr_arr        = None
    swing_lo_arr   = None
    swing_hi_arr   = None
    if use_new:
        # Force trailing flag on when caller chose a real mode
        if trail_mode != "none":
            trail_enabled = True
            trail_from_idx = 0 if trail_start == "immediate" else 0  # always start at 0; logic below decides
        if trail_mode == "atr":
            atr_arr = _atr_series(df, int(tp_params.get("atr_period", 14)))
        elif trail_mode == "swing":
            sl_len = int(tp_params.get("swing_len", 3))
            swing_lo_arr = _swing_lows(df,  sl_len)
            swing_hi_arr = _swing_highs(df, sl_len)

    def _build_tps(setup):
        """Apply new-model TPs to a setup if target_r is provided."""
        if not use_new:
            return setup.get("tps", [])
        if target_r is None:
            # Pure-trail with no fixed exit — empty TP list, trail handles everything
            return []
        entry = setup["entry"]; risk = setup["risk"]
        price = entry + target_r * risk if setup["direction"] == "Bull" else entry - target_r * risk
        # If no trail, force full close at target (close_pct ignored).
        # If trail enabled, use the user's chosen close_pct (0.0 = ride full, 1.0 = full exit).
        qty = 1.0 if trail_mode == "none" else max(0.0, min(1.0, target_close_pct))
        return [(price, qty)]

    def _trail_candidate(direction, i, current_sl, fill_idx):
        """Return the new trail SL candidate for this bar, given the mode."""
        if trail_mode == "candle":
            buf = float(tp_params.get("buf_pips", trail_buf_pips)) * pip
            return (L[i] - buf) if direction == "Bull" else (H[i] + buf)
        if trail_mode == "atr":
            mult = float(tp_params.get("atr_mult", 1.5))
            d    = atr_arr[i] * mult
            return (df["C"].values[i] - d) if direction == "Bull" else (df["C"].values[i] + d)
        if trail_mode == "pips":
            d = float(tp_params.get("trail_pips", 20)) * pip
            return (df["C"].values[i] - d) if direction == "Bull" else (df["C"].values[i] + d)
        if trail_mode == "swing":
            buf = float(tp_params.get("buf_pips", 1)) * pip
            if direction == "Bull":
                lv = swing_lo_arr[i]
                return (lv - buf) if not np.isnan(lv) else None
            else:
                lv = swing_hi_arr[i]
                return (lv + buf) if not np.isnan(lv) else None
        # legacy 'candle' (no explicit mode)
        return (L[i] - trail_buf) if direction == "Bull" else (H[i] + trail_buf)

    queue   = sorted(setups, key=lambda x: x["signal_idx"])
    q_ptr   = 0
    pending = []
    active  = []
    trades  = []
    seen    = set()

    for i in range(n):
        # Release newly-available setups into the pending queue
        while q_ptr < len(queue) and queue[q_ptr]["signal_idx"] <= i:
            s   = queue[q_ptr]
            key = dedup_key_fn(s)
            if key not in seen:
                seen.add(key)
                s_copy = {**s}
                if use_new:
                    s_copy["tps"] = _build_tps(s_copy)
                pending.append(s_copy)
            q_ptr += 1

        if session_hours and not (session_hours[0] <= hours[i] < session_hours[1]):
            continue

        # ── Walk active trades forward ─────────────────────────────────────
        still_active = []
        for t in active:
            entry     = t["entry"]
            risk      = t["risk"]
            direction = t["direction"]
            tps       = t["tps"]
            next_idx  = t["next_tp_idx"]
            remaining = t["remaining"]
            realized  = t["realized_r"]
            trailing  = t["trailing"]
            closed    = False

            # 1) Walk through any TPs hit on this bar
            while not closed and next_idx < len(tps) and remaining > 1e-9:
                tp_price, tp_qty = tps[next_idx]
                if direction == "Bull":
                    hit = H[i] >= tp_price
                    r_at_tp = (tp_price - entry) / risk
                else:
                    hit = L[i] <= tp_price
                    r_at_tp = (entry - tp_price) / risk
                if not hit:
                    break
                qty_close = min(tp_qty, remaining)
                realized += qty_close * r_at_tp
                remaining -= qty_close
                t["last_tp_hit"] = next_idx + 1
                next_idx += 1

                if trail_enabled and not trailing and next_idx > trail_from_idx:
                    trailing = True
                    cand = _trail_candidate(direction, i, t.get("trail_sl"), t.get("fill_idx", i)) \
                           if use_new else \
                           ((L[i] - trail_buf) if direction == "Bull" else (H[i] + trail_buf))
                    if cand is not None:
                        t["trail_sl"] = cand

                if remaining <= 1e-9:
                    trades.append({**t, "result": "Win",
                                   "pnl_r": realized,
                                   "exit_type": f"TP{next_idx}",
                                   "exit_idx": i})
                    closed = True

            # 2) Trailing-stop exit
            if not closed and trailing and remaining > 1e-9:
                # Compute new trail candidate
                cand = _trail_candidate(direction, i, t["trail_sl"], t.get("fill_idx", i)) \
                       if use_new else \
                       ((L[i] - trail_buf) if direction == "Bull" else (H[i] + trail_buf))

                if direction == "Bull":
                    if cand is not None and cand > t["trail_sl"]:
                        t["trail_sl"] = cand
                    if L[i] <= t["trail_sl"]:
                        r_exit = (t["trail_sl"] - entry) / risk
                        realized += remaining * r_exit
                        trades.append({**t, "result": "Win" if realized > 0 else "Loss",
                                       "pnl_r": realized, "exit_type": "Trail",
                                       "exit_idx": i})
                        closed = True
                else:
                    if cand is not None and cand < t["trail_sl"]:
                        t["trail_sl"] = cand
                    if H[i] >= t["trail_sl"]:
                        r_exit = (entry - t["trail_sl"]) / risk
                        realized += remaining * r_exit
                        trades.append({**t, "result": "Win" if realized > 0 else "Loss",
                                       "pnl_r": realized, "exit_type": "Trail",
                                       "exit_idx": i})
                        closed = True

            # 2.5) Break-even promotion — move SL to entry once MFE reaches be_at_r
            if not closed and remaining > 1e-9:
                be_at_r = (t.get("meta") or {}).get("be_at_r")
                if be_at_r and not t.get("be_promoted"):
                    if direction == "Bull":
                        mfe_r = (H[i] - entry) / risk
                    else:
                        mfe_r = (entry - L[i]) / risk
                    if mfe_r >= float(be_at_r):
                        t["sl"] = entry              # SL → break-even
                        t["be_promoted"] = True

            # 3) Stop-loss / break-even exit
            if not closed and remaining > 1e-9:
                if direction == "Bull" and L[i] <= t["sl"] and not trailing and next_idx == 0:
                    realized += remaining * -1.0
                    trades.append({**t, "result": "Loss", "pnl_r": realized,
                                   "exit_type": "SL", "exit_idx": i})
                    closed = True
                elif direction == "Bear" and H[i] >= t["sl"] and not trailing and next_idx == 0:
                    realized += remaining * -1.0
                    trades.append({**t, "result": "Loss", "pnl_r": realized,
                                   "exit_type": "SL", "exit_idx": i})
                    closed = True
                elif not trailing and next_idx > 0:
                    be_hit = (direction == "Bull" and L[i] <= entry) or \
                             (direction == "Bear" and H[i] >= entry)
                    if be_hit:
                        trades.append({**t, "result": "Win" if realized > 0 else "Loss",
                                       "pnl_r": realized, "exit_type": "BE",
                                       "exit_idx": i})
                        closed = True

            # 4) Time exit — force close after N bars in trade
            if not closed and remaining > 1e-9:
                t_bars = (t.get("meta") or {}).get("time_exit_bars")
                if t_bars and t.get("fill_idx") is not None:
                    if (i - t["fill_idx"]) >= int(t_bars):
                        # Close at current bar's close
                        from_px = float(df["C"].values[i])
                        r_exit  = ((from_px - entry) / risk) if direction == "Bull" else ((entry - from_px) / risk)
                        realized += remaining * r_exit
                        trades.append({**t, "result": "Win" if realized > 0 else "Loss",
                                       "pnl_r": realized, "exit_type": "TimeExit",
                                       "exit_idx": i})
                        closed = True

            if not closed:
                t["next_tp_idx"] = next_idx
                t["remaining"]   = remaining
                t["realized_r"]  = realized
                t["trailing"]    = trailing
                still_active.append(t)
        active = still_active

        # ── Expire stale pending orders ────────────────────────────────────
        if order_expiry is not None:
            pending = [p for p in pending if i - p["signal_idx"] <= order_expiry]

        # ── Try to fill pending orders ─────────────────────────────────────
        if len(active) < max_concurrent:
            new_pending = []
            filled_this_bar = 0
            for p in pending:
                if len(active) + filled_this_bar >= max_concurrent:
                    new_pending.append(p); continue
                entry = p["entry"]
                if L[i] <= entry <= H[i]:
                    # If new model + immediate trail, start trailing right at fill
                    start_trailing = (use_new and trail_mode != "none"
                                      and trail_start == "immediate")
                    init_trail_sl = p["sl"]
                    if start_trailing:
                        c0 = _trail_candidate(p["direction"], i, p["sl"], i)
                        if c0 is not None:
                            init_trail_sl = (max(p["sl"], c0)
                                             if p["direction"] == "Bull"
                                             else min(p["sl"], c0))
                    active.append({**p,
                        "next_tp_idx": 0,
                        "remaining":   1.0,
                        "realized_r":  0.0,
                        "trailing":    start_trailing,
                        "trail_sl":    init_trail_sl,
                        "last_tp_hit": 0,
                        "fill_idx":    i,
                    })
                    filled_this_bar += 1
                else:
                    new_pending.append(p)
            pending = new_pending

    for p in pending:
        trades.append({**p, "result": "Unresolved", "pnl_r": 0.0,
                       "exit_type": "Unresolved", "last_tp_hit": -1,
                       "fill_idx": None, "exit_idx": None})

    return pd.DataFrame(trades) if trades else pd.DataFrame()
