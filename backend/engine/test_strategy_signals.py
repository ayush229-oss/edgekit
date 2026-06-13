"""
Correctness tests for the STRATEGY SIGNAL layer (detect()) + the indicator
primitives strategies are built on.

Where test_engine_correctness.py validates the simulator/metrics math, this file
validates that strategies emit the RIGHT setups:

  1. indicator primitives (sma/ema/rsi/atr) vs hand-computed values
  2. exact signal placement on constructed series (Donchian breakout, EMA cross)
  3. registry-wide well-formedness: every strategy emits simulator-valid setups
  4. no-lookahead: early signals must not change when future bars are appended

Run: python -m pytest backend/engine/test_strategy_signals.py -v
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import pytest

from backend.engine.core import indicators as ind
from backend.engine.strategies import REGISTRY, get


# ── helpers ──────────────────────────────────────────────────────────────────
def make_df(bars, start="2024-01-01"):
    """bars = list of (o,h,l,c) or (o,h,l,c,v). 1-hour spacing."""
    t0 = pd.Timestamp(start)
    rows = []
    for k, b in enumerate(bars):
        o, h, l, c = b[0], b[1], b[2], b[3]
        v = b[4] if len(b) > 4 else 1000.0
        rows.append({"time": t0 + pd.Timedelta(hours=k),
                     "O": o, "H": h, "L": l, "C": c, "V": v})
    return pd.DataFrame(rows)


def synth_series(n=500, seed=3):
    """Trending + oscillating OHLCV — exercises most indicator strategies."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    close = 100 + 0.02 * t + 6 * np.sin(t / 17.0) + rng.normal(0, 0.4, n)
    bars = []
    prev = close[0]
    for c in close:
        o = prev
        hi = max(o, c) + abs(rng.normal(0, 0.5))
        lo = min(o, c) - abs(rng.normal(0, 0.5))
        vol = 1000 + abs(rng.normal(0, 200))
        bars.append((o, hi, lo, c, vol))
        prev = c
    return make_df(bars)


# ── 1. INDICATOR PRIMITIVES (hand-computed) ──────────────────────────────────
def test_sma_exact():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = ind.sma(s, 3)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx(2.0)   # (1+2+3)/3
    assert out.iloc[3] == pytest.approx(3.0)
    assert out.iloc[4] == pytest.approx(4.0)


def test_ema_matches_adjust_false_recursion():
    # EMA must be the causal adjust=False EMA (alpha=2/(p+1)), seeded at x[0],
    # with the first (period-1) values masked. Pin that exact convention.
    s = pd.Series(np.arange(1, 11), dtype=float)
    period = 3
    alpha = 2 / (period + 1)
    ref = [float(s.iloc[0])]
    for x in s.iloc[1:]:
        ref.append(alpha * x + (1 - alpha) * ref[-1])
    ref = np.array(ref)
    out = ind.ema(s, period)
    assert out.iloc[:period - 1].isna().all()        # warmup masked
    assert out.iloc[period - 1:].values == pytest.approx(ref[period - 1:], abs=1e-9)


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.arange(1, 40), dtype=float)        # strictly rising
    r = ind.rsi(up, 14).dropna()
    assert (r >= 0).all() and (r <= 100).all()
    assert r.iloc[-1] == pytest.approx(100.0)            # no losses → RSI 100

    down = pd.Series(np.arange(40, 1, -1), dtype=float)  # strictly falling
    rd = ind.rsi(down, 14).dropna()
    assert rd.iloc[-1] == pytest.approx(0.0)             # no gains → RSI 0


def test_rsi_flat_is_neutral_50():
    flat = pd.Series([100.0] * 40)                       # no movement at all
    r = ind.rsi(flat, 14)
    assert r.iloc[14:].eq(50.0).all()                    # neutral, not NaN


def test_rsi_warmup_is_nan():
    r = ind.rsi(pd.Series(np.arange(1, 40), dtype=float), 14)
    assert r.iloc[:13].isna().all()                      # first period-1 masked


def test_atr_constant_range_converges():
    # Every bar has identical 2.0 range and no gaps → ATR converges to 2.0.
    bars = [(100, 101, 99, 100)] * 60
    df = make_df(bars)
    a = ind.atr(df, 14).dropna()
    assert a.iloc[-1] == pytest.approx(2.0, abs=1e-6)


# ── 1b. REMAINING INDICATOR AUDIT (macd/bollinger/vwap/supertrend/pivots) ────
def test_macd_definition():
    s = pd.Series(100 + np.cumsum(np.ones(80)), dtype=float)   # steady ramp up
    m = ind.macd(s, 12, 26, 9)
    valid = m.dropna()
    # histogram is exactly macd - signal, by definition
    assert np.allclose(valid["hist"].values,
                       (valid["macd"] - valid["signal"]).values, atol=1e-9)
    # fast EMA leads slow EMA in an uptrend → macd line positive
    assert valid["macd"].iloc[-1] > 0


def test_bollinger_symmetry_and_flat():
    s = pd.Series(np.linspace(100, 120, 60))
    b = ind.bollinger(s, 20, 2.0)
    v = b.dropna()
    # bands are symmetric around the mid
    assert np.allclose((v["upper"] - v["mid"]).values,
                       (v["mid"] - v["lower"]).values, atol=1e-9)
    # half-width equals stdev * rolling std
    sd = s.rolling(20).std().dropna()
    assert np.allclose((v["upper"] - v["mid"]).values, (2.0 * sd).values, atol=1e-9)
    # constant series → zero width
    flat = ind.bollinger(pd.Series([100.0] * 40), 20, 2.0).dropna()
    assert np.allclose(flat["upper"].values, flat["mid"].values, atol=1e-9)
    assert np.allclose(flat["lower"].values, flat["mid"].values, atol=1e-9)


def test_vwap_constant_typical_price():
    # Every bar has typical price (H+L+C)/3 == 100, varied volume, one session.
    bars = [(100, 101, 99, 100, 500 + 50 * k) for k in range(10)]   # H+L+C=300
    df = make_df(bars)
    vw = ind.vwap(df).dropna()
    assert np.allclose(vw.values, 100.0, atol=1e-9)       # VWAP must equal 100


def test_vwap_requires_volume_column():
    df = make_df([(100, 101, 99, 100)]).drop(columns=["V"])
    with pytest.raises(ValueError):
        ind.vwap(df)


def test_supertrend_direction_tracks_trend():
    up = [(100 + k, 100 + k + 0.5, 100 + k - 0.5, 100 + k) for k in range(40)]
    down = [(140 - k, 140 - k + 0.5, 140 - k - 0.5, 140 - k) for k in range(40)]
    df = make_df(up + down)
    st = ind.supertrend(df, 10, 3.0)
    assert set(st["direction"].unique()).issubset({1, -1})   # only valid states
    assert st["direction"].iloc[39] == 1                     # end of uptrend = up
    assert st["direction"].iloc[-1] == -1                    # end of downtrend = down


def test_swing_pivots_definition_is_noncausal():
    # A swing high at i is the max of [i-len .. i+len]. NOTE: this uses FUTURE
    # bars (center=True) → non-causal. Strategies using it must offset; the
    # prefix-invariance test confirms none leak it into entry timing.
    highs = [10, 11, 12, 20, 12, 11, 10]          # clear peak at index 3
    bars = [(h, h, h - 1, h) for h in highs]
    piv = ind.swing_pivots(make_df(bars), length=2)
    assert bool(piv["swing_high"].iloc[3]) is True
    assert bool(piv["swing_high"].iloc[2]) is False


# ── 2. EXACT SIGNAL PLACEMENT ────────────────────────────────────────────────
def test_donchian_breakout_exact_bar():
    # 11 flat bars (range ~100.0-100.5), then bar 11 closes at 102 → one Bull
    # breakout. channel/atr period = 5 so warmup is short.
    flat = [(100.0, 100.5, 99.6, 100.1) for _ in range(11)]
    breakout = (100.2, 102.2, 100.1, 102.0)   # bar 11: closes above prior 5-bar high
    after = [(101.8, 101.9, 101.0, 101.2) for _ in range(5)]   # no new breakout
    df = make_df(flat + [breakout] + after)

    params = {"channel_period": 5, "atr_period": 5, "sl_atr_mult": 2.0,
              "min_atr_pips": 0.0, "pip": 0.1}
    setups = get("donchian")().detect(df, params)

    bulls = [s for s in setups if s["direction"] == "Bull"]
    assert len(bulls) == 1, f"expected 1 breakout, got {len(bulls)}"
    s = bulls[0]
    assert s["signal_idx"] == 12                       # i=11 detected → trade next bar
    assert s["entry"] == pytest.approx(df["O"].iloc[12])
    assert s["sl"] < s["entry"]                        # long stop below entry
    assert s["risk"] == pytest.approx(s["entry"] - s["sl"], abs=1e-9)
    assert s["risk"] > 0
    # risk must equal ATR(bar 11) * mult
    atr11 = ind.atr(df, 5).iloc[11]
    assert s["risk"] == pytest.approx(atr11 * 2.0, abs=1e-9)


def test_donchian_no_signal_inside_channel():
    # Price never closes beyond the channel → zero setups.
    df = make_df([(100.0, 100.5, 99.6, 100.1) for _ in range(30)])
    setups = get("donchian")().detect(
        df, {"channel_period": 5, "atr_period": 5, "sl_atr_mult": 2.0, "pip": 0.1})
    assert setups == []


def test_ema_cross_signals_match_true_crosses():
    # Independently recompute fast/slow EMA crosses and assert detect() fires on
    # exactly those bars, with correct direction / entry / stop wiring.
    df = synth_series(n=400, seed=9)
    params = {"fast_ema": 5, "slow_ema": 20, "atr_period": 14,
              "sl_atr_mult": 1.5, "trend_filter": False, "pip": 0.1}
    setups = get("ema_cross")().detect(df, params)

    fast = ind.ema(df["C"], 5)
    slow = ind.ema(df["C"], 20)
    a = ind.atr(df, 14)
    cur_above = fast > slow
    prev_above = fast.shift(1) > slow.shift(1)
    bull_cross = cur_above & ~prev_above
    bear_cross = ~cur_above & prev_above

    lo = max(20, 14) + 1
    hi = len(df) - 1
    expected = []
    for i in range(lo, hi):
        if pd.isna(a.iloc[i]) or a.iloc[i] <= 0:
            continue
        if bull_cross.iloc[i]:
            expected.append((i + 1, "Bull"))
        elif bear_cross.iloc[i]:
            expected.append((i + 1, "Bear"))

    got = [(s["signal_idx"], s["direction"]) for s in setups]
    assert got == expected, "detected crosses must match independent recomputation"
    assert len(got) > 0, "scenario should produce at least one cross"

    # spot-check wiring on each setup
    for s in setups:
        i = s["signal_idx"] - 1
        sl_dist = a.iloc[i] * 1.5
        assert s["entry"] == pytest.approx(df["O"].iloc[s["signal_idx"]])
        assert s["risk"] == pytest.approx(sl_dist, abs=1e-9)
        if s["direction"] == "Bull":
            assert s["sl"] == pytest.approx(s["entry"] - sl_dist, abs=1e-9)
        else:
            assert s["sl"] == pytest.approx(s["entry"] + sl_dist, abs=1e-9)


def test_ema_cross_invalid_fast_ge_slow_returns_empty():
    df = synth_series(n=120)
    setups = get("ema_cross")().detect(
        df, {"fast_ema": 20, "slow_ema": 20, "pip": 0.1})
    assert setups == []


# ── 3. REGISTRY-WIDE WELL-FORMEDNESS ─────────────────────────────────────────
@pytest.mark.parametrize("sid", list(REGISTRY.keys()))
def test_every_strategy_emits_valid_setups(sid):
    df = synth_series(n=600, seed=5)
    strat = get(sid)()
    params = {**strat.default_params(), "pip": 0.1}
    setups = strat.detect(df, params)
    n = len(df)

    for s in setups:
        # required keys
        for k in ("signal_idx", "direction", "entry", "sl", "risk", "tps"):
            assert k in s, f"{sid}: setup missing '{k}'"
        assert s["direction"] in ("Bull", "Bear"), f"{sid}: bad direction"
        assert 0 <= s["signal_idx"] < n, f"{sid}: signal_idx out of range"
        assert np.isfinite(s["entry"]) and np.isfinite(s["sl"]), f"{sid}: non-finite px"
        assert s["risk"] > 0, f"{sid}: non-positive risk"
        assert s["risk"] == pytest.approx(abs(s["entry"] - s["sl"]), rel=1e-6), \
            f"{sid}: risk != |entry-sl|"
        # stop on the correct side
        if s["direction"] == "Bull":
            assert s["sl"] < s["entry"], f"{sid}: long stop not below entry"
        else:
            assert s["sl"] > s["entry"], f"{sid}: short stop not above entry"
        # TP ladder present and on the correct side of entry
        assert len(s["tps"]) > 0, f"{sid}: empty tps"
        for price, qty in s["tps"]:
            assert qty > 0
            if s["direction"] == "Bull":
                assert price > s["entry"], f"{sid}: long TP not above entry"
            else:
                assert price < s["entry"], f"{sid}: short TP not below entry"


def test_some_strategies_actually_fire():
    # Guards against the suite silently passing because nothing produced setups.
    df = synth_series(n=600, seed=5)
    fired = [sid for sid in REGISTRY
             if get(sid)().detect(df, {**get(sid)().default_params(), "pip": 0.1})]
    assert len(fired) >= 4, f"only {fired} produced setups — series may be unrepresentative"


# ── 4. NO-LOOKAHEAD (prefix invariance) ──────────────────────────────────────
@pytest.mark.parametrize("sid", list(REGISTRY.keys()))
def test_no_lookahead_prefix_invariance(sid):
    """Signals in the early part of the data must be identical whether or not
    future bars exist. A strategy that reads future bars changes its past
    output when the series is truncated — this catches that."""
    full = synth_series(n=600, seed=5)
    cut = 380
    margin = 60                       # ignore signals near the cut (indicator warmup edge)
    strat = get(sid)()
    params = {**strat.default_params(), "pip": 0.1}

    sig_full = {s["signal_idx"]: (s["direction"], round(s["entry"], 6))
                for s in strat.detect(full, params) if s["signal_idx"] < cut - margin}
    sig_cut = {s["signal_idx"]: (s["direction"], round(s["entry"], 6))
               for s in strat.detect(full.iloc[:cut].copy(), params)
               if s["signal_idx"] < cut - margin}

    assert sig_full == sig_cut, (
        f"{sid}: early signals changed when future bars were removed "
        f"→ lookahead. only_full={set(sig_full)-set(sig_cut)} "
        f"only_cut={set(sig_cut)-set(sig_full)}")
