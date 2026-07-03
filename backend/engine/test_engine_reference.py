"""
Independent validation of the backtesting engine.

This file does NOT re-test the engine against numbers I typed by hand (that is
test_engine_correctness.py). Instead it pits the engine against:

  (A) a *clean-room reference simulator* (`ref_simulate`) written only from the
      documented execution model in core/simulator.py — limit-order fill rule,
      gap precedence, R-multiple accounting. It shares no code with the engine,
      so when the two agree trade-for-trade on hundreds of random charts, a
      whole class of systematic logic bugs is ruled out.

  (B) *property / invariant fuzzing*: laws that must hold for ANY input —
      equity reconciliation, cost monotonicity (more cost => less profit),
      determinism, and engine-level no-lookahead (appending future bars never
      changes an already-resolved trade).

Run: python -m pytest backend/engine/test_engine_reference.py -v
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import pytest

from backend.engine.core import simulate, compute_metrics


# ── data + setup generators ──────────────────────────────────────────────────
def make_df_local(bars):
    """bars = list of (open, high, low, close), 1-hour spacing."""
    t0 = pd.Timestamp("2024-01-01")
    return pd.DataFrame([
        {"time": t0 + pd.Timedelta(hours=k), "O": o, "H": h, "L": l, "C": c, "V": 0.0}
        for k, (o, h, l, c) in enumerate(bars)
    ])



def random_ohlc(n: int, seed: int, start: float = 100.0) -> pd.DataFrame:
    """A plausible random-walk OHLC series. 1-hour bars."""
    rng = np.random.default_rng(seed)
    close = start + np.cumsum(rng.normal(0, 1.0, n))
    rows = []
    t0 = pd.Timestamp("2024-01-01")
    for k in range(n):
        c = close[k]
        o = c - rng.normal(0, 0.5)
        hi = max(o, c) + abs(rng.normal(0, 0.6))
        lo = min(o, c) - abs(rng.normal(0, 0.6))
        rows.append({"time": t0 + pd.Timedelta(hours=k),
                     "O": o, "H": hi, "L": lo, "C": c, "V": 0.0})
    return pd.DataFrame(rows)


def random_setups(df: pd.DataFrame, seed: int, k: int):
    """k limit-order setups anchored to bars in df, both directions."""
    rng = np.random.default_rng(seed + 7919)
    n = len(df)
    out = []
    for _ in range(k):
        i = int(rng.integers(0, n - 1))
        ref = float(df["C"].iloc[i])
        direction = "Bull" if rng.random() < 0.5 else "Bear"
        dist = abs(rng.normal(0, 1.5)) + 0.3        # entry offset
        risk = abs(rng.normal(0, 1.5)) + 0.5        # SL distance
        if direction == "Bull":
            entry = round(ref - dist, 4)
            sl = round(entry - risk, 4)
        else:
            entry = round(ref + dist, 4)
            sl = round(entry + risk, 4)
        # risk MUST equal the realized entry->sl distance, or a "2R" TP won't
        # land at exactly 2R (the engine divides by abs(entry-sl)).
        out.append({"signal_idx": i, "direction": direction,
                    "entry": entry, "sl": sl, "risk": abs(entry - sl),
                    # unique liq_level so the engine's dedup never merges setups
                    "liq_level": round(entry + 0.0001 * len(out), 4)})
    return out


# ── (A) CLEAN-ROOM REFERENCE SIMULATOR ───────────────────────────────────────
# Written purely from core/simulator.py's documented model, in a deliberately
# different style. Scope: limit entry, single full-close TP at target_r, fixed
# SL, no trailing, no costs (so R-multiples are exact). max_concurrent honored.
def ref_simulate(df, setups, target_r, max_concurrent=1):
    O = df["O"].values; H = df["H"].values; L = df["L"].values
    n = len(df)
    queue = sorted(setups, key=lambda s: s["signal_idx"])
    q_ptr = 0
    pending, active, trades, seen = [], [], [], set()

    def fill_price_ok(p, i):
        # buy-limit fills only if bar opens at/above entry AND low reaches it.
        if p["direction"] == "Bull":
            return O[i] >= p["entry"] and L[i] <= p["entry"]
        return O[i] <= p["entry"] and H[i] >= p["entry"]

    def resolve(t, i):
        d, entry, sl, risk = t["direction"], t["entry"], t["sl"], t["risk"]
        tp = entry + target_r * risk if d == "Bull" else entry - target_r * risk
        # Stop model: a gap (open beyond the stop) fills at the open — a stop,
        # once triggered, becomes a MARKET order. A take-profit is the
        # opposite: a resting LIMIT order that fills AT the target price,
        # never at a gapped-through "better" price (real limit-order
        # execution doesn't hand you extra profit just because the market
        # moved further before your order was checked).
        if d == "Bull":
            if O[i] < sl:                                   # gap through SL
                return ("Loss", (O[i] - entry) / risk, i)
            if O[i] >= tp or H[i] >= tp:                     # TP hit — capped at tp
                return ("Win", (tp - entry) / risk, i)
            if L[i] <= sl:
                return ("Loss", (sl - entry) / risk, i)     # fill at the stop
        else:
            if O[i] > sl:
                return ("Loss", (entry - O[i]) / risk, i)
            if O[i] <= tp or L[i] <= tp:                     # TP hit — capped at tp
                return ("Win", (entry - tp) / risk, i)
            if H[i] >= sl:
                return ("Loss", (entry - sl) / risk, i)     # fill at the stop
        return None

    for i in range(n):
        while q_ptr < len(queue) and queue[q_ptr]["signal_idx"] <= i:
            s = queue[q_ptr]
            key = (s["direction"], round(s.get("liq_level", s["entry"]), 2))
            if key not in seen:
                seen.add(key)
                pending.append(dict(s))
            q_ptr += 1

        # exits first (a trade filled at bar f is first checked at f+1)
        still = []
        for t in active:
            r = resolve(t, i)
            if r:
                trades.append({"result": r[0], "pnl_r": r[1],
                               "exit_idx": r[2], "fill_idx": t["fill_idx"]})
            else:
                still.append(t)
        active = still

        # then fills
        if len(active) < max_concurrent:
            np2, filled = [], 0
            for p in pending:
                if len(active) + filled >= max_concurrent:
                    np2.append(p); continue
                if fill_price_ok(p, i):
                    active.append({**p, "fill_idx": i}); filled += 1
                else:
                    np2.append(p)
            pending = np2

    return trades


def engine_trades(df, setups, target_r, max_concurrent=1):
    tdf = simulate(df, [dict(s) for s in setups],
                   target_r=target_r, target_close_pct=1.0, trail_mode="none",
                   spread_pips=0.0, commission=0.0, slippage_pips=0.0, pip=0.1,
                   max_concurrent=max_concurrent)
    if tdf.empty:
        return []
    res = tdf[tdf["result"] != "Unresolved"]
    out = []
    for _, row in res.iterrows():
        out.append({"result": row["result"], "pnl_r": float(row["pnl_r"]),
                    "exit_idx": int(row["exit_idx"]), "fill_idx": int(row["fill_idx"])})
    out.sort(key=lambda t: (t["fill_idx"], t["exit_idx"]))
    return out


@pytest.mark.parametrize("seed", range(60))
def test_engine_matches_reference(seed):
    """Engine and clean-room reference must agree trade-for-trade."""
    df = random_ohlc(120, seed)
    setups = random_setups(df, seed, k=8)
    target_r = 2.0

    eng = engine_trades(df, setups, target_r)
    ref = sorted(ref_simulate(df, setups, target_r),
                 key=lambda t: (t["fill_idx"], t["exit_idx"]))

    assert len(eng) == len(ref), (
        f"seed={seed}: engine produced {len(eng)} trades, reference {len(ref)}")
    for e, r in zip(eng, ref):
        assert e["fill_idx"] == r["fill_idx"], f"seed={seed} fill mismatch {e} vs {r}"
        assert e["exit_idx"] == r["exit_idx"], f"seed={seed} exit mismatch {e} vs {r}"
        assert e["result"] == r["result"], f"seed={seed} result mismatch {e} vs {r}"
        assert e["pnl_r"] == pytest.approx(r["pnl_r"], abs=1e-6), \
            f"seed={seed} pnl mismatch {e} vs {r}"


@pytest.mark.parametrize("seed", range(20))
def test_engine_matches_reference_concurrent(seed):
    """Same agreement must hold with multiple simultaneous positions."""
    df = random_ohlc(150, seed + 500)
    setups = random_setups(df, seed + 500, k=14)
    target_r = 1.5
    mc = 3

    eng = engine_trades(df, setups, target_r, max_concurrent=mc)
    ref = sorted(ref_simulate(df, setups, target_r, max_concurrent=mc),
                 key=lambda t: (t["fill_idx"], t["exit_idx"]))

    assert len(eng) == len(ref), f"seed={seed}: {len(eng)} vs {len(ref)} trades"
    for e, r in zip(eng, ref):
        assert (e["fill_idx"], e["exit_idx"], e["result"]) == \
               (r["fill_idx"], r["exit_idx"], r["result"]), f"seed={seed}: {e} vs {r}"
        assert e["pnl_r"] == pytest.approx(r["pnl_r"], abs=1e-6)


# ── (B) PROPERTY / INVARIANT FUZZING ─────────────────────────────────────────
def test_cost_monotonicity_commission():
    """Raising commission can only lower (or hold) total profit — never raise it."""
    for seed in range(15):
        df = random_ohlc(120, seed + 11)
        setups = random_setups(df, seed + 11, k=10)
        totals = []
        for comm in (0.0, 0.5, 1.0, 3.0):
            tdf = simulate(df, [dict(s) for s in setups], target_r=2.0,
                           commission=comm, pip=0.1, max_concurrent=2)
            m = compute_metrics(tdf)
            totals.append(m["total_r"] if m else 0.0)
        for a, b in zip(totals, totals[1:]):
            assert b <= a + 1e-9, f"seed={seed}: commission raised profit {totals}"


def test_spread_cost_model():
    """
    Spread, applied correctly:
      - a clean (non-gap) loss stays EXACTLY -1R at any spread — the stop fills
        at the stop, and eff_risk widens by exactly the spread, so the ratio is
        -1 (this is the bar-low fix in action);
      - a clean win shrinks monotonically as spread widens.

    (Note: total-R across a whole backtest is NOT monotonic in spread — wider
    spread enlarges per-trade risk, shrinking position size, which reduces the
    R-impact of fixed-price *gap* exits. That is correct under fractional-risk
    sizing, so we assert the per-trade cost model here rather than a portfolio
    total.)
    """
    loss = make_df_local([(100, 100.1, 99.9, 100.0), (100, 100.3, 98.5, 99.0)])
    win = make_df_local([(100, 100.1, 99.8, 100.0), (100, 101.9, 99.9, 101.8)])
    prev_win = float("inf")
    for sp in (0.0, 2.0, 5.0, 10.0):
        lr = simulate(loss, [{"signal_idx": 0, "direction": "Bull", "entry": 100.0,
                              "sl": 99.0, "risk": 1.0}], target_r=9.0,
                      spread_pips=sp, pip=0.1)
        wr = simulate(win, [{"signal_idx": 0, "direction": "Bull", "entry": 99.8,
                             "sl": 98.8, "risk": 1.0}], target_r=2.0,
                      spread_pips=sp, pip=0.1)
        lv = float(lr[lr["result"] != "Unresolved"].iloc[0]["pnl_r"])
        wv = float(wr[wr["result"] != "Unresolved"].iloc[0]["pnl_r"])
        assert lv == pytest.approx(-1.0, abs=1e-9), f"spread={sp}: loss {lv} != -1R"
        assert wv <= prev_win + 1e-9, f"spread={sp}: win {wv} not <= {prev_win}"
        prev_win = wv


def test_intrabar_stop_fills_at_stop_not_bar_low():
    """
    A non-gap stop (bar opens on the right side of the stop, then trades through
    it) must fill AT THE STOP, not at the bar low. Regression guard for the
    bar-low fix.
    """
    df = make_df_local([
        (100.0, 100.2, 99.9, 100.1),   # bar 0: fills the long at 100
        (100.0, 100.3, 97.0, 98.0),    # bar 1: opens at 100 (no gap), wicks to 97
    ])
    setups = [{"signal_idx": 0, "direction": "Bull", "entry": 100.0,
               "sl": 99.0, "risk": 1.0}]
    tdf = simulate(df, setups, target_r=5.0, pip=0.1)   # TP far away, only SL can hit
    res = tdf[tdf["result"] != "Unresolved"]
    assert len(res) == 1
    assert res.iloc[0]["exit_type"] == "SL"
    # Stop at 99, entry 100 => clean -1R. The 97 low is irrelevant (price was
    # already stopped out at 99 on the way down).
    assert float(res.iloc[0]["pnl_r"]) == pytest.approx(-1.0, abs=1e-6)


def test_gap_down_stop_still_fills_at_open():
    """The gap path is UNCHANGED: open below the stop fills at the open, not the stop."""
    df = make_df_local([
        (100.0, 100.2, 99.9, 100.1),   # bar 0: fills the long at 100
        (97.0, 97.5, 96.0, 96.5),      # bar 1: GAPS open to 97 (below stop 99)
    ])
    setups = [{"signal_idx": 0, "direction": "Bull", "entry": 100.0,
               "sl": 99.0, "risk": 1.0}]
    tdf = simulate(df, setups, target_r=5.0, pip=0.1)
    res = tdf[tdf["result"] != "Unresolved"]
    assert len(res) == 1
    assert res.iloc[0]["exit_type"] == "SL_gap"
    assert float(res.iloc[0]["pnl_r"]) == pytest.approx(-3.0, abs=1e-6)   # filled at open 97


def test_determinism():
    """Identical inputs => byte-identical trade logs."""
    for seed in range(10):
        df = random_ohlc(140, seed + 71)
        setups = random_setups(df, seed + 71, k=12)
        a = engine_trades(df, setups, 2.0, max_concurrent=3)
        b = engine_trades(df, setups, 2.0, max_concurrent=3)
        assert a == b


def test_no_lookahead_future_bars():
    """
    Appending future bars must NOT change any trade that already resolved on the
    original window. This is the engine-level guard against future-data leakage.
    """
    for seed in range(15):
        df = random_ohlc(100, seed + 91)
        setups = random_setups(df, seed + 91, k=8)
        short = engine_trades(df, setups, 2.0, max_concurrent=2)

        extra = random_ohlc(60, seed + 9100)
        extra["time"] = df["time"].iloc[-1] + pd.to_timedelta(
            np.arange(1, len(extra) + 1), unit="h")
        long_df = pd.concat([df, extra], ignore_index=True)
        long_trades = engine_trades(long_df, setups, 2.0, max_concurrent=2)

        last_orig = len(df) - 1
        for t in short:
            twin = [u for u in long_trades
                    if u["fill_idx"] == t["fill_idx"] and u["exit_idx"] <= last_orig]
            assert any(u["pnl_r"] == pytest.approx(t["pnl_r"], abs=1e-9)
                       and u["result"] == t["result"] for u in twin), \
                f"seed={seed}: resolved trade {t} changed when future bars added"


def test_equity_reconciles():
    """final_equity must equal initial + compounded Σ(pnl_r·risk_usd)."""
    for seed in range(15):
        df = random_ohlc(130, seed + 131)
        setups = random_setups(df, seed + 131, k=12)
        tdf = simulate(df, [dict(s) for s in setups], target_r=2.0,
                       commission=0.3, spread_pips=1.0, pip=0.1, max_concurrent=2)
        m = compute_metrics(tdf, initial_equity=100.0, risk_pct=0.01,
                            max_risk_usd=600.0)
        if not m:
            continue
        eq = 100.0
        for r in m["pnl"]:
            eq += r * min(eq * 0.01, 600.0)
        assert m["final_equity"] == pytest.approx(eq, rel=1e-9)
        assert m["max_dd"] <= 1e-9                      # drawdown is never positive
        assert m["total_r"] == pytest.approx(float(np.sum(m["pnl"])), abs=1e-9)


# ── degenerate sanity ────────────────────────────────────────────────────────
def test_flat_market_no_pnl():
    """A market that never moves can fill nothing that risks anything."""
    df = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=40, freq="h"),
        "O": 100.0, "H": 100.0, "L": 100.0, "C": 100.0, "V": 0.0,
    })
    setups = [{"signal_idx": 0, "direction": "Bull", "entry": 99.0,
               "sl": 98.0, "risk": 1.0}]
    tdf = simulate(df, setups, target_r=2.0, pip=0.1)
    # entry at 99 never touched (price pinned at 100) => no resolved trade
    if not tdf.empty:
        assert (tdf["result"] == "Unresolved").all()


def test_guaranteed_winner_is_win():
    """A long that fills and whose TP is hit intrabar must book exactly +target_r."""
    # bar0 dips to 99.8 (fills entry), bar1 opens below TP then spikes through it.
    bars = [(100.0, 100.1, 99.8, 100.0),    # fills long @ 99.8
            (100.0, 101.9, 99.9, 101.8)]    # TP @ 99.8+2*1=101.8 hit intrabar (O<TP<=H)
    bars += [(101.8, 101.9, 101.7, 101.8)] * 5
    df = make_df_local(bars)
    setups = [{"signal_idx": 0, "direction": "Bull", "entry": 99.8,
               "sl": 98.8, "risk": 1.0}]
    tdf = simulate(df, setups, target_r=2.0, pip=0.1)
    res = tdf[tdf["result"] != "Unresolved"]
    assert len(res) == 1
    assert res.iloc[0]["result"] == "Win"
    assert float(res.iloc[0]["pnl_r"]) == pytest.approx(2.0, abs=1e-6)
