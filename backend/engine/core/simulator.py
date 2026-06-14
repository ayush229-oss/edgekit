"""
Universal strategy simulator. Strategy-agnostic — works with any setup list.

TRADE EXECUTION MODEL:
    1. Pending limit order placed at `entry` (spread-adjusted on fill)
    2. When price touches entry → fill at entry + spread/2 (buy) or - spread/2 (sell)
    3. Gap risk: if open gaps past SL/TP, fill at gap-open, not the level price
    4. Commission deducted on both open and close
    5. Slippage applied to market exits (SL, trail, time-exit, break-even)
    6. Overnight swap deducted each calendar day the trade spans
    7. Partial fills on limit orders based on liquidity_factor

A setup dict must contain:
    signal_idx:  int            bar at which setup becomes available
    direction:   'Bull' | 'Bear'
    entry:       float          limit order price
    sl:          float          initial stop loss
    risk:        float          |entry - sl|, pre-computed
    tps:         list[(price, qty_fraction)]
    liq_level:   float          (optional) for dedup
    meta:        dict           (optional)
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple, Literal
import pandas as pd
import numpy as np


TrailMode = Literal["none", "candle", "atr", "pips", "swing"]


def _atr_series(df: pd.DataFrame, period: int = 14) -> np.ndarray:
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
    L = df["L"].values
    n = len(L)
    result = np.full(n, np.nan)
    for i in range(length, n - length):
        if L[i] == L[max(0, i-length):i+length+1].min():
            result[i] = L[i]
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


def _bar_date(df: pd.DataFrame, i: int):
    """Return the date of bar i (used for overnight swap counting)."""
    try:
        return df["time"].iloc[i].date()
    except Exception:
        return None


def simulate(
    df: pd.DataFrame,
    setups: List[Dict[str, Any]],
    *,
    # ── Trade management ───────────────────────────────────────────────────
    target_r:          Optional[float] = None,
    target_close_pct:  float           = 1.0,
    trail_mode:        TrailMode       = "none",
    trail_start:       Literal["immediate", "after_target"] = "after_target",
    trail_params:      Optional[Dict[str, Any]] = None,
    trail_enabled:     bool  = False,
    trail_from_idx:    int   = 2,
    trail_buf_pips:    float = 1.0,
    # ── Execution costs (NEW) ──────────────────────────────────────────────
    spread_pips:       float = 0.0,    # bid/ask spread in pips (half each side)
    commission:        float = 0.0,    # fixed USD cost per trade (round-trip ÷ 2 each leg)
    slippage_pips:     float = 0.0,    # worst-case slippage on market exits (pips)
    swap_long_pips:    float = 0.0,    # overnight swap per day for long positions (pips, can be negative)
    swap_short_pips:   float = 0.0,    # overnight swap per day for short positions
    # ── Order management ───────────────────────────────────────────────────
    max_concurrent:    int   = 1,
    order_expiry:      Optional[int] = None,
    session_hours:     Optional[Tuple[int, int]] = None,
    pip:               float = 0.10,
    dedup_key_fn = None,
    risk_pct:          float = 0.01,   # needed to convert commission USD → R
    initial_equity:    float = 100.0,
    max_risk_usd:      float = 600.0,
) -> pd.DataFrame:
    """
    Run a backtest given pre-detected setups.

    Cost model
    ----------
    spread_pips   Half the spread is added to the fill price on entry (widens
                  effective SL distance and TP distance by spread/2).
    commission    Round-trip commission in USD. Converted to R at fill time and
                  subtracted from pnl_r as a constant drag.
    slippage_pips Market exits (SL, trail, break-even, time-exit) suffer this
                  many pips of additional adverse slippage.
    swap_long/short_pips  Overnight carry cost per calendar day. Summed across
                  the holding period and subtracted from pnl_r at close.
    """
    trail_buf  = trail_buf_pips * pip
    spread_h   = spread_pips * pip / 2.0      # half spread per side
    slip       = slippage_pips * pip           # market-exit slippage
    H, L, O_arr = df["H"].values, df["L"].values, df["O"].values
    C_arr      = df["C"].values
    hours      = df["time"].dt.hour.values
    n          = len(df)

    if dedup_key_fn is None:
        def dedup_key_fn(s):
            return (s["direction"], round(s.get("liq_level", s["entry"]), 2))

    tp_params  = trail_params or {}
    use_new    = target_r is not None or trail_mode != "none"
    atr_arr        = None
    swing_lo_arr   = None
    swing_hi_arr   = None
    if use_new:
        if trail_mode != "none":
            trail_enabled = True
            trail_from_idx = 0
        if trail_mode == "atr":
            atr_arr = _atr_series(df, int(tp_params.get("atr_period", 14)))
        elif trail_mode == "swing":
            sl_len = int(tp_params.get("swing_len", 3))
            swing_lo_arr = _swing_lows(df, sl_len)
            swing_hi_arr = _swing_highs(df, sl_len)

    def _build_tps(setup):
        if not use_new:
            return setup.get("tps", [])
        if target_r is None:
            return []
        entry = setup["entry"]; risk = setup["risk"]
        price = entry + target_r * risk if setup["direction"] == "Bull" else entry - target_r * risk
        qty = 1.0 if trail_mode == "none" else max(0.0, min(1.0, target_close_pct))
        return [(price, qty)]

    def _trail_candidate(direction, i, current_sl, fill_idx):
        if trail_mode == "candle":
            buf = float(tp_params.get("buf_pips", trail_buf_pips)) * pip
            return (L[i] - buf) if direction == "Bull" else (H[i] + buf)
        if trail_mode == "atr":
            mult = float(tp_params.get("atr_mult", 1.5))
            d    = atr_arr[i] * mult
            return (C_arr[i] - d) if direction == "Bull" else (C_arr[i] + d)
        if trail_mode == "pips":
            d = float(tp_params.get("trail_pips", 20)) * pip
            return (C_arr[i] - d) if direction == "Bull" else (C_arr[i] + d)
        if trail_mode == "swing":
            buf = float(tp_params.get("buf_pips", 1)) * pip
            if direction == "Bull":
                lv = swing_lo_arr[i]
                return (lv - buf) if not np.isnan(lv) else None
            else:
                lv = swing_hi_arr[i]
                return (lv + buf) if not np.isnan(lv) else None
        return (L[i] - trail_buf) if direction == "Bull" else (H[i] + trail_buf)

    # ── Commission in R units ─────────────────────────────────────────────
    # We compute this once per fill because risk_usd is ~constant for small equity moves.
    def _commission_r(risk_amount: float) -> float:
        """Full round-trip commission expressed as a fraction of risk."""
        if commission <= 0 or risk_amount <= 0:
            return 0.0
        return commission / risk_amount   # both open + close legs

    queue   = sorted(setups, key=lambda x: x["signal_idx"])
    q_ptr   = 0
    pending = []
    active  = []
    trades  = []
    seen    = set()

    # Track running equity for risk_usd calculation
    equity = initial_equity

    for i in range(n):
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
            fill_entry = t["fill_entry"]     # spread-adjusted fill price
            entry      = t["entry"]          # nominal entry
            risk       = t["risk"]
            direction  = t["direction"]
            tps        = t["tps"]
            next_idx   = t["next_tp_idx"]
            remaining  = t["remaining"]
            realized   = t["realized_r"]
            trailing   = t["trailing"]
            closed     = False

            # ── Overnight swap ─────────────────────────────────────────────
            fill_date  = t.get("fill_date")
            bar_date   = _bar_date(df, i)
            prev_date  = t.get("last_date")
            if fill_date and bar_date and prev_date and bar_date > prev_date:
                # New calendar day — apply swap
                swap = swap_long_pips if direction == "Bull" else swap_short_pips
                if swap != 0 and risk > 0:
                    realized -= (swap * pip) / risk   # subtract (negative swap = cost)
            t["last_date"] = bar_date

            # ── Gap risk check ─────────────────────────────────────────────
            # If bar opens past the SL, fill at open (not SL) — realistic gap slippage
            sl_now = t.get("trail_sl", t["sl"]) if trailing else t["sl"]
            if direction == "Bull" and O_arr[i] < sl_now and not trailing and next_idx == 0:
                gap_r = (O_arr[i] - slip - fill_entry) / risk
                realized += remaining * gap_r
                risk_usd = min(equity * risk_pct, max_risk_usd)
                realized -= _commission_r(risk_usd)
                equity += realized * risk_usd
                trades.append({**t, "result": "Loss", "pnl_r": realized,
                               "exit_type": "SL_gap", "exit_idx": i})
                closed = True
            elif direction == "Bear" and O_arr[i] > sl_now and not trailing and next_idx == 0:
                gap_r = (fill_entry - O_arr[i] - slip) / risk
                realized += remaining * gap_r
                risk_usd = min(equity * risk_pct, max_risk_usd)
                realized -= _commission_r(risk_usd)
                equity += realized * risk_usd
                trades.append({**t, "result": "Loss", "pnl_r": realized,
                               "exit_type": "SL_gap", "exit_idx": i})
                closed = True

            if closed:
                # already appended to trades above — skip rest of logic
                pass

            # 1) TPs
            while not closed and next_idx < len(tps) and remaining > 1e-9:
                tp_price, tp_qty = tps[next_idx]
                # Gap-through TP: bar opens past TP — fill at open (favorable gap)
                if direction == "Bull":
                    if O_arr[i] >= tp_price:
                        tp_fill = O_arr[i]   # filled at gap-open
                        hit = True
                    else:
                        tp_fill = tp_price
                        hit = H[i] >= tp_price
                    r_at_tp = (tp_fill - fill_entry) / risk
                else:
                    if O_arr[i] <= tp_price:
                        tp_fill = O_arr[i]
                        hit = True
                    else:
                        tp_fill = tp_price
                        hit = L[i] <= tp_price
                    r_at_tp = (fill_entry - tp_fill) / risk
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
                    # Deduct commission on close leg
                    risk_usd = min(equity * risk_pct, max_risk_usd)
                    realized -= _commission_r(risk_usd)
                    equity += realized * risk_usd
                    trades.append({**t, "result": "Win",
                                   "pnl_r": realized,
                                   "exit_type": f"TP{next_idx}",
                                   "exit_idx": i})
                    closed = True

            # 2) Trailing stop
            if not closed and trailing and remaining > 1e-9:
                cand = _trail_candidate(direction, i, t["trail_sl"], t.get("fill_idx", i)) \
                       if use_new else \
                       ((L[i] - trail_buf) if direction == "Bull" else (H[i] + trail_buf))

                if direction == "Bull":
                    if cand is not None and cand > t["trail_sl"]:
                        t["trail_sl"] = cand
                    if L[i] <= t["trail_sl"]:
                        # Fill at the trail stop (minus slippage). On a gap down
                        # (open below the stop) fill at the open instead -- never
                        # the bar low. No separate gap branch exists for trails.
                        exit_px = min(t["trail_sl"], O_arr[i]) - slip
                        r_exit  = (exit_px - fill_entry) / risk
                        realized += remaining * r_exit
                        risk_usd = min(equity * risk_pct, max_risk_usd)
                        realized -= _commission_r(risk_usd)
                        equity += realized * risk_usd
                        trades.append({**t, "result": "Win" if realized > 0 else "Loss",
                                       "pnl_r": realized, "exit_type": "Trail",
                                       "exit_idx": i})
                        closed = True
                else:
                    if cand is not None and cand < t["trail_sl"]:
                        t["trail_sl"] = cand
                    if H[i] >= t["trail_sl"]:
                        # Fill at the trail stop (plus slippage), or the open on a
                        # gap up. Never the bar high.
                        exit_px = max(t["trail_sl"], O_arr[i]) + slip
                        r_exit  = (fill_entry - exit_px) / risk
                        realized += remaining * r_exit
                        risk_usd = min(equity * risk_pct, max_risk_usd)
                        realized -= _commission_r(risk_usd)
                        equity += realized * risk_usd
                        trades.append({**t, "result": "Win" if realized > 0 else "Loss",
                                       "pnl_r": realized, "exit_type": "Trail",
                                       "exit_idx": i})
                        closed = True

            # 2.5) Break-even promotion
            if not closed and remaining > 1e-9:
                be_at_r = (t.get("meta") or {}).get("be_at_r")
                if be_at_r and not t.get("be_promoted"):
                    mfe_r = (H[i] - fill_entry) / risk if direction == "Bull" else (fill_entry - L[i]) / risk
                    if mfe_r >= float(be_at_r):
                        t["sl"] = entry
                        t["be_promoted"] = True

            # 3) Stop-loss (with gap-adjusted fill and slippage)
            if not closed and remaining > 1e-9:
                sl_price = t["sl"]
                if direction == "Bull" and L[i] <= sl_price and not trailing and next_idx == 0:
                    # Stop fires as price trades through it -> fill at the stop
                    # price (minus slippage), NOT the bar low. A gap down
                    # (open < sl) is handled by the SL_gap branch above, which
                    # fills at the open. This matches real stop-order execution.
                    exit_px  = sl_price - slip
                    r_exit   = (exit_px - fill_entry) / risk
                    realized += remaining * r_exit
                    risk_usd = min(equity * risk_pct, max_risk_usd)
                    realized -= _commission_r(risk_usd)
                    equity += realized * risk_usd
                    trades.append({**t, "result": "Loss", "pnl_r": realized,
                                   "exit_type": "SL", "exit_idx": i})
                    closed = True
                elif direction == "Bear" and H[i] >= sl_price and not trailing and next_idx == 0:
                    # Mirror of the long: fill at the stop (plus slippage), not the
                    # bar high. Gap ups (open > sl) handled by SL_gap branch above.
                    exit_px  = sl_price + slip
                    r_exit   = (fill_entry - exit_px) / risk
                    realized += remaining * r_exit
                    risk_usd = min(equity * risk_pct, max_risk_usd)
                    realized -= _commission_r(risk_usd)
                    equity += realized * risk_usd
                    trades.append({**t, "result": "Loss", "pnl_r": realized,
                                   "exit_type": "SL", "exit_idx": i})
                    closed = True
                elif not trailing and next_idx > 0:
                    be_hit = (direction == "Bull" and L[i] <= entry) or \
                             (direction == "Bear" and H[i] >= entry)
                    if be_hit:
                        risk_usd = min(equity * risk_pct, max_risk_usd)
                        realized -= _commission_r(risk_usd)
                        equity += realized * risk_usd
                        trades.append({**t, "result": "Win" if realized > 0 else "Loss",
                                       "pnl_r": realized, "exit_type": "BE",
                                       "exit_idx": i})
                        closed = True

            # 4) Time exit
            if not closed and remaining > 1e-9:
                t_bars = (t.get("meta") or {}).get("time_exit_bars")
                if t_bars and t.get("fill_idx") is not None:
                    if (i - t["fill_idx"]) >= int(t_bars):
                        exit_px = C_arr[i]
                        # Apply directional slippage on market close
                        if direction == "Bull":
                            exit_px -= slip
                            r_exit = (exit_px - fill_entry) / risk
                        else:
                            exit_px += slip
                            r_exit = (fill_entry - exit_px) / risk
                        realized += remaining * r_exit
                        risk_usd = min(equity * risk_pct, max_risk_usd)
                        realized -= _commission_r(risk_usd)
                        equity += realized * risk_usd
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
                entry     = p["entry"]
                direction = p["direction"]
                if direction == "Bull":
                    _filled = O_arr[i] >= entry and L[i] <= entry
                else:
                    _filled = O_arr[i] <= entry and H[i] >= entry

                if _filled:
                    # Spread-adjusted fill price (widens effective risk)
                    if direction == "Bull":
                        fill_entry = entry + spread_h   # paid more for the buy
                    else:
                        fill_entry = entry - spread_h   # sold for less

                    # Effective risk after spread (SL distance shrinks slightly)
                    sl = p["sl"]
                    eff_risk = abs(fill_entry - sl)
                    if eff_risk < 1e-9:
                        eff_risk = p["risk"]   # fallback

                    start_trailing = (use_new and trail_mode != "none"
                                      and trail_start == "immediate")
                    init_trail_sl = sl
                    if start_trailing:
                        c0 = _trail_candidate(direction, i, sl, i)
                        if c0 is not None:
                            init_trail_sl = (max(sl, c0) if direction == "Bull" else min(sl, c0))

                    # Deduct commission on open leg
                    risk_usd  = min(equity * risk_pct, max_risk_usd)
                    open_comm = _commission_r(risk_usd) / 2   # open leg = half round-trip

                    active.append({**p,
                        "fill_entry":  fill_entry,
                        "risk":        eff_risk,
                        "next_tp_idx": 0,
                        "remaining":   1.0,
                        "realized_r":  -open_comm,   # open-leg commission drag
                        "trailing":    start_trailing,
                        "trail_sl":    init_trail_sl,
                        "last_tp_hit": 0,
                        "fill_idx":    i,
                        "fill_date":   _bar_date(df, i),
                        "last_date":   _bar_date(df, i),
                    })
                    filled_this_bar += 1
                else:
                    new_pending.append(p)
            pending = new_pending

    for p in pending:
        trades.append({**p, "result": "Unresolved", "pnl_r": 0.0,
                       "exit_type": "Unresolved", "last_tp_hit": -1,
                       "fill_idx": None, "exit_idx": None,
                       "fill_entry": p["entry"]})

    return pd.DataFrame(trades) if trades else pd.DataFrame()
