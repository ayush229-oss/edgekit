"""
Correctness tests for the backtesting engine.

Unlike the smoke/trail tests (which check "does it run" / "do configs differ"),
these assert the engine produces the EXACT, hand-computed result for scenarios
small enough to verify by hand — plus structural invariants on multi-trade runs
(no lookahead, R accounting, determinism).

Run: python -m pytest backend/engine/test_engine_correctness.py -v
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import pytest

from backend.engine.core import simulate, compute_metrics


# ── helpers ──────────────────────────────────────────────────────────────────
def make_df(bars: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """bars = list of (open, high, low, close). 1-hour spacing."""
    t0 = pd.Timestamp("2024-01-01 00:00:00")
    rows = []
    for k, (o, h, l, c) in enumerate(bars):
        rows.append({
            "time": t0 + pd.Timedelta(hours=k),
            "O": o, "H": h, "L": l, "C": c, "V": 0.0,
        })
    return pd.DataFrame(rows)


def one_setup(direction, entry, sl, signal_idx=0):
    return [{
        "signal_idx": signal_idx, "direction": direction,
        "entry": entry, "sl": sl, "risk": abs(entry - sl), "tps": [],
    }]


# Zero-cost simulate so R-multiples are exact.
CLEAN = dict(spread_pips=0.0, commission=0.0, slippage_pips=0.0, pip=0.1,
             trail_mode="none", max_concurrent=1)


# ── 1. METRICS MATH (exact, hand-computed) ───────────────────────────────────
def test_metrics_known_log():
    # pnl_r = [+2, -1, +2, -1, -1] → 2 wins, 3 losses
    tdf = pd.DataFrame({
        "result":    ["Win", "Loss", "Win", "Loss", "Loss"],
        "pnl_r":     [2.0, -1.0, 2.0, -1.0, -1.0],
        "exit_type": ["TP1", "SL", "TP1", "SL", "SL"],
        "fill_idx":  [0, 2, 4, 6, 8],
        "exit_idx":  [1, 3, 5, 7, 9],
    })
    m = compute_metrics(tdf)
    assert m["trades"] == 5
    assert m["wr"] == pytest.approx(40.0)            # 2/5
    assert m["ev"] == pytest.approx(0.2)             # (2-1+2-1-1)/5
    assert m["total_r"] == pytest.approx(1.0)        # sum
    assert m["avg_win"] == pytest.approx(2.0)
    assert m["avg_loss"] == pytest.approx(-1.0)
    assert m["avg_rr"] == pytest.approx(2.0)
    assert m["profit_factor"] == pytest.approx(4.0 / 3.0)   # |sum(win)/sum(loss)|
    assert m["n_unresolved"] == 0


def test_metrics_empty_returns_none():
    assert compute_metrics(pd.DataFrame()) is None
    only_unres = pd.DataFrame({"result": ["Unresolved"], "pnl_r": [0.0]})
    assert compute_metrics(only_unres) is None


def test_metrics_all_wins_profit_factor_inf():
    tdf = pd.DataFrame({"result": ["Win", "Win"], "pnl_r": [1.0, 2.0],
                        "exit_type": ["TP1", "TP1"]})
    m = compute_metrics(tdf)
    assert m["wr"] == pytest.approx(100.0)
    assert np.isinf(m["profit_factor"])
    assert m["max_dd"] == pytest.approx(0.0)         # monotonic up → no drawdown


# ── 2. TRADE MECHANICS (exact R, hand-verified) ──────────────────────────────
def test_long_clean_2R_win():
    # entry 100, sl 99 (risk 1), target 2R → TP 102
    df = make_df([
        (98,  98.5, 97.5, 98),     # 0: signal, no touch
        (100, 100.2, 99.5, 100),   # 1: fills at 100 (O>=100, L<=100)
        (100.5, 102, 100.3, 101.8) # 2: H hits 102 → TP
    ])
    tdf = simulate(df, one_setup("Bull", 100, 99), target_r=2.0, **CLEAN)
    assert len(tdf) == 1
    r = tdf.iloc[0]
    assert r["result"] == "Win"
    assert str(r["exit_type"]).startswith("TP")
    assert r["pnl_r"] == pytest.approx(2.0, abs=1e-9)
    assert r["fill_idx"] == 1 and r["exit_idx"] == 2     # no lookahead


def test_long_clean_minus1R_loss():
    df = make_df([
        (98, 98.5, 97.5, 98),
        (100, 100.2, 99.5, 100),   # fill at 100
        (99.8, 99.9, 99.0, 99.2),  # low touches sl=99 exactly → -1R
    ])
    tdf = simulate(df, one_setup("Bull", 100, 99), target_r=2.0, **CLEAN)
    r = tdf.iloc[0]
    assert r["result"] == "Loss"
    assert r["exit_type"] == "SL"
    assert r["pnl_r"] == pytest.approx(-1.0, abs=1e-9)


def test_long_gap_through_stop_is_worse_than_1R():
    # Bar opens below SL → fill at the gap-open, not the stop price.
    df = make_df([
        (98, 98.5, 97.5, 98),
        (100, 100.2, 99.5, 100),   # fill at 100
        (98.0, 98.2, 97.5, 97.8),  # opens at 98 < sl 99 → gap fill
    ])
    tdf = simulate(df, one_setup("Bull", 100, 99), target_r=2.0, **CLEAN)
    r = tdf.iloc[0]
    assert r["result"] == "Loss"
    assert r["exit_type"] == "SL_gap"
    assert r["pnl_r"] == pytest.approx(-2.0, abs=1e-9)   # (98-100)/1
    assert r["pnl_r"] < -1.0


def test_long_gap_through_target_caps_at_target_not_the_gap_price():
    # A take-profit is a resting LIMIT order: it fills AT the target price,
    # never at a more "favorable" gapped-through price — the opposite of a
    # stop, which becomes a market order once triggered and DOES slip on a
    # gap (see test_long_gap_through_stop_is_worse_than_1R above). A strategy
    # with a 2R target must never book 9R just because one bar opened far
    # past the target — that's not how a real broker fills a limit order.
    df = make_df([
        (98, 98.5, 97.5, 98),
        (100, 100.2, 99.5, 100),   # fill at 100 (entry=100, sl=99, risk=1, target=2R -> tp=102)
        (109.0, 110.0, 108.5, 109.5),  # opens at 109 — 9R past entry, way past the 102 target
    ])
    tdf = simulate(df, one_setup("Bull", 100, 99), target_r=2.0, **CLEAN)
    r = tdf.iloc[0]
    assert r["result"] == "Win"
    assert r["exit_type"] == "TP1"
    assert r["pnl_r"] == pytest.approx(2.0, abs=1e-9)   # capped at the 2R target, not 9R


def test_short_clean_2R_win():
    # entry 100, sl 101 (risk 1), target 2R → TP 98
    df = make_df([
        (102, 102.5, 101.5, 102),
        (100, 100.5, 99.5, 100),   # fill at 100 (O<=100, H>=100)
        (99.5, 99.7, 98.0, 98.2),  # low hits 98 → TP
    ])
    tdf = simulate(df, one_setup("Bear", 100, 101), target_r=2.0, **CLEAN)
    r = tdf.iloc[0]
    assert r["result"] == "Win"
    assert r["pnl_r"] == pytest.approx(2.0, abs=1e-9)


def test_never_filled_is_unresolved():
    # Price never reaches entry 100 → order never fills.
    df = make_df([(98, 98.5, 97.5, 98)] * 5)
    tdf = simulate(df, one_setup("Bull", 100, 99), target_r=2.0, **CLEAN)
    assert len(tdf) == 1
    r = tdf.iloc[0]
    assert r["result"] == "Unresolved"
    assert r["fill_idx"] is None


def test_no_fill_before_signal_bar():
    # Setup signals at bar 3; an entry-touching bar at index 1 must NOT fill it.
    df = make_df([
        (100, 100.2, 99.5, 100),   # 0: would touch entry, but signal not active
        (100, 100.2, 99.5, 100),   # 1
        (98, 98.5, 97.5, 98),      # 2
        (100, 100.2, 99.5, 100),   # 3: signal active here, fills
        (100.5, 102, 100.3, 101.8) # 4: TP
    ])
    tdf = simulate(df, one_setup("Bull", 100, 99, signal_idx=3), target_r=2.0, **CLEAN)
    r = tdf.iloc[0]
    assert r["fill_idx"] >= 3          # never filled on the earlier touches
    assert r["result"] == "Win"


# ── 3. ENGINE INVARIANTS on a multi-trade synthetic run ──────────────────────
def _random_walk(n=600, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    bars = []
    for c_prev, c in zip(np.concatenate(([100.0], close[:-1])), close):
        o = c_prev
        hi = max(o, c) + abs(rng.normal(0, 0.2))
        lo = min(o, c) - abs(rng.normal(0, 0.2))
        bars.append((o, hi, lo, c))
    return make_df(bars)


def _many_setups(df):
    # A long setup every 12 bars: entry just below close, stop 1.0 under it.
    setups = []
    C = df["C"].values
    for i in range(0, len(df) - 30, 12):
        entry = C[i] - 0.1
        sl = entry - 1.0
        setups.append({"signal_idx": i, "direction": "Bull",
                       "entry": entry, "sl": sl, "risk": 1.0, "tps": []})
    return setups


def test_invariants_no_lookahead_and_r_accounting():
    df = _random_walk()
    tdf = simulate(df, _many_setups(df), target_r=2.0, max_concurrent=1,
                   spread_pips=0.0, commission=0.0, slippage_pips=0.0, pip=0.1)
    assert not tdf.empty
    closed = tdf[tdf["result"] != "Unresolved"]

    # no lookahead: a trade never fills before its signal, never exits before fill
    for _, t in closed.iterrows():
        assert t["fill_idx"] is not None
        assert t["fill_idx"] >= t["signal_idx"], "fill before signal = lookahead"
        assert t["exit_idx"] >= t["fill_idx"], "exit before fill"

    # R accounting: reported total_r equals the sum of per-trade R
    m = compute_metrics(tdf)
    assert m["total_r"] == pytest.approx(float(closed["pnl_r"].sum()), abs=1e-9)

    # win rate matches the actual win count
    wins = int((closed["pnl_r"] > 0).sum())
    assert m["wr"] == pytest.approx(wins / len(closed) * 100.0)

    # no NaN / inf leaking into trade P&L
    assert np.isfinite(closed["pnl_r"].values).all()


def test_determinism_same_input_same_output():
    df = _random_walk()
    setups = _many_setups(df)
    a = simulate(df, [dict(s) for s in setups], target_r=2.0, **CLEAN)
    b = simulate(df, [dict(s) for s in setups], target_r=2.0, **CLEAN)
    assert len(a) == len(b)
    assert a["pnl_r"].sum() == pytest.approx(b["pnl_r"].sum(), abs=1e-12)
    assert list(a["result"]) == list(b["result"])


def test_winners_above_entry_losers_at_or_below():
    # Sanity: every Win has positive R, every Loss non-positive R.
    df = _random_walk(seed=11)
    tdf = simulate(df, _many_setups(df), target_r=2.0, **CLEAN)
    closed = tdf[tdf["result"] != "Unresolved"]
    for _, t in closed.iterrows():
        if t["result"] == "Win":
            assert t["pnl_r"] > 0
        else:
            assert t["pnl_r"] <= 1e-9
