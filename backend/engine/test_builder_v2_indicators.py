"""
Correctness tests for the v2 VISUAL BUILDER's own node library
(backend/engine/builder_v2/nodes.py + nodes_extra.py).

Why this file exists: the v2 node library re-implements its indicator/alpha
math from scratch (see the "kept inline for self-containment" comments in
nodes.py) rather than reusing the already-tested backend/engine/core/indicators.py.
That means the code path actually driving the drag-and-drop builder — the one
most users touch — had ZERO correctness coverage before this file existed.
test_engine_correctness.py / test_engine_reference.py only cover the shared
simulator (fills, PnL, R-accounting); test_strategy_signals.py only covers the
OLD v1 hand-coded strategies' indicator module.

Structure (mirrors test_strategy_signals.py):
  1. Indicator primitives — hand-computed values, pinned exactly
  2. Alpha nodes — exact signal placement on constructed bar sequences
  3. Filter nodes — pass/block behavior
  4. Integration — every production template (real node combinations) emits
     well-formed setups and is lookahead-free

Run: python -m pytest backend/engine/test_builder_v2_indicators.py -v
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import pytest

from backend.engine.builder_v2 import NODE_LIBRARY, GraphV2Strategy, RunContext
from backend.engine.builder_v2.nodes import _ema, _atr, _donchian
from backend.engine.builder_v2 import nodes_extra as ext
from backend.engine.builder_v2.templates import list_templates, get_template


# ── helpers (same conventions as test_strategy_signals.py) ─────────────────
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


def synth_series(n=600, seed=3):
    """Trending + oscillating OHLCV — exercises most indicator nodes."""
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


def run_node(node_type, df, params, ctx=None):
    """Run a node's prepare()+eval() across every bar; returns (outputs list, ctx)."""
    spec = NODE_LIBRARY[node_type]
    ctx = ctx or RunContext(pip=0.1)
    full_params = {p["key"]: params.get(p["key"], p["default"]) for p in spec.params}
    if spec.prepare_fn:
        spec.prepare_fn(df, ctx, full_params)
    outs = [spec.eval_fn(df, i, ctx, {}, full_params) for i in range(len(df))]
    return outs, ctx


def eval_alpha(node_type, df, params, inputs_per_bar, ctx=None):
    """Run an alpha/filter node's eval() across every bar with per-bar wired
    inputs; returns list of eval() outputs (dicts or None)."""
    spec = NODE_LIBRARY[node_type]
    ctx = ctx or RunContext(pip=0.1)
    full_params = {p["key"]: params.get(p["key"], p["default"]) for p in spec.params}
    if spec.prepare_fn:
        spec.prepare_fn(df, ctx, full_params)
    ctx.state["__current_node__"] = "t1"
    outs = []
    for i in range(len(df)):
        outs.append(spec.eval_fn(df, i, ctx, inputs_per_bar(i), full_params))
    return outs


# ════════════════════════════════════════════════════════════════════════
# 1. INDICATOR PRIMITIVES — hand-computed, pinned exactly
# ════════════════════════════════════════════════════════════════════════

def test_v2_ema_matches_adjust_false_recursion():
    # nodes.py's _ema is a from-scratch reimplementation of the same
    # convention core.indicators.ema uses (causal, adjust=False, seeded at
    # x[0]). Pin it independently since GraphV2Strategy uses THIS function.
    arr = np.arange(1, 11, dtype=float)
    period = 3
    alpha = 2 / (period + 1)
    ref = [arr[0]]
    for x in arr[1:]:
        ref.append(alpha * x + (1 - alpha) * ref[-1])
    ref = np.array(ref)
    out = _ema(arr, period)
    assert out == pytest.approx(ref, abs=1e-9)


def test_v2_atr_constant_range_converges():
    bars = [(100, 101, 99, 100)] * 60
    df = make_df(bars)
    a = _atr(df, 14)
    assert a[-1] == pytest.approx(2.0, abs=1e-6)


def test_v2_donchian_excludes_current_bar():
    # upper/lower must be the PRIOR N-bar high/low (shift(1)) — including the
    # current bar would make breakouts impossible (close can never exceed a
    # channel that includes its own bar's high).
    H = [10, 11, 12, 20, 12, 11, 10, 10]
    L = [h - 2 for h in H]
    bars = list(zip([h - 1 for h in H], H, L, H))  # o,h,l,c
    df = make_df(bars)
    upper, lower = _donchian(df, period=3)
    # bar 3 (the spike, value 20) must NOT see its own high — channel covers
    # only the prior 3 bars (10, 11, 12)
    assert upper[3] == pytest.approx(12.0)
    # bar 4's channel covers bars 1,2,3 (11, 12, 20) — NOW it includes the spike
    assert upper[4] == pytest.approx(20.0)


def test_v2_rsi_bounds_and_extremes():
    up = np.arange(1, 40, dtype=float)          # strictly rising
    r = ext._rsi(up, 14)[13:]
    assert (r >= 0).all() and (r <= 100).all()
    assert r[-1] == pytest.approx(100.0)         # no losses -> RSI 100

    down = np.arange(40, 1, -1, dtype=float)     # strictly falling
    rd = ext._rsi(down, 14)[13:]
    assert rd[-1] == pytest.approx(0.0)          # no gains -> RSI 0


def test_v2_rsi_flat_market_is_neutral_not_zero():
    # Standard RSI convention (matching core.indicators.rsi, tested in
    # test_strategy_signals.py::test_rsi_flat_is_neutral_50): a flat market
    # with zero gains AND zero losses is undefined -> convention reports 50
    # (neutral). Pins the fix for a real bug found while writing this suite:
    # the old `np.where(avg_l == 0, 0, ...)` branch reported RSI=0 for BOTH
    # a flat market and a strictly-rising one (see test above) — a quiet
    # market would misread as maximally oversold.
    flat = np.array([100.0] * 40)
    r = ext._rsi(flat, 14)[13:]
    assert r == pytest.approx(50.0)


def test_v2_bollinger_symmetry_and_flat():
    s = np.linspace(100, 120, 60)
    upper, mid, lower = ext._bbands(s, 20, 2.0)
    v_upper, v_mid, v_lower = upper[19:], mid[19:], lower[19:]
    assert np.allclose(v_upper - v_mid, v_mid - v_lower, atol=1e-9)
    flat_u, flat_m, flat_l = ext._bbands(np.array([100.0] * 40), 20, 2.0)
    assert np.allclose(flat_u[19:], flat_m[19:], atol=1e-9)
    assert np.allclose(flat_l[19:], flat_m[19:], atol=1e-9)


def test_v2_macd_definition():
    s = 100 + np.cumsum(np.ones(80))             # steady ramp up
    macd_line, sig_line, hist = ext._macd(s, 12, 26, 9)
    assert np.allclose(hist[34:], (macd_line - sig_line)[34:], atol=1e-9)
    assert macd_line[-1] > 0                      # fast EMA leads slow in uptrend


def test_v2_vwap_constant_typical_price():
    # Every bar has typical price (H+L+C)/3 == 100, varied volume.
    bars = [(100, 101, 99, 100, 500 + 50 * k) for k in range(10)]
    df = make_df(bars)
    vw = ext._vwap(df)
    assert np.allclose(vw, 100.0, atol=1e-9)


def test_v2_stochastic_bounds_and_exact_value():
    up = np.arange(1, 40, dtype=float)
    df = make_df([(x, x + 0.5, x - 0.5, x) for x in up])
    k, d = ext._stoch(df, 14, 3)
    assert (k[13:] >= 0).all() and (k[13:] <= 100.0 + 1e-6).all()
    # hand-computed: 14-bar window at the last bar spans H=[26.5..39.5], L=[25.5..38.5]
    # (each bar's H/L is monotonic +1 from the previous) -> roll max H=39.5, roll min L=25.5
    hi = float(df["H"].iloc[-14:].max())
    lo = float(df["L"].iloc[-14:].min())
    c  = float(df["C"].iloc[-1])
    expected = 100 * (c - lo) / (hi - lo)
    assert k[-1] == pytest.approx(expected, abs=1e-6)


def test_v2_adx_flat_market_near_zero():
    bars = [(100, 100.5, 99.5, 100)] * 60          # no directional movement
    df = make_df(bars)
    a = ext._adx(df, 14)
    assert a[-1] < 5.0


def test_v2_swing_high_excludes_current_bar_and_is_causal():
    # A rolling max over the PRIOR N bars (shift(1)) — must not see its own bar.
    highs = np.array([10.0, 11, 12, 20, 12, 11, 10, 10])
    out = ext._swing_rolling(highs, period=3, is_high=True)
    # at i=3 (value 20), the swing-high must reflect bars [0,1,2] only = 12
    assert out[3] == pytest.approx(12.0)
    # at i=4, prior 3 bars [1,2,3] include the 20 -> swing-high becomes 20
    assert out[4] == pytest.approx(20.0)


def test_v2_swing_no_lookahead_prefix_invariance():
    df = synth_series(n=300, seed=7)
    full = ext._swing_rolling(df["H"].values, period=10, is_high=True)
    cut = 200
    truncated = ext._swing_rolling(df["H"].values[:cut], period=10, is_high=True)
    assert np.allclose(full[:cut], truncated, atol=1e-9)


def test_v2_supertrend_direction_tracks_trend():
    up   = [(100 + k, 100 + k + 0.5, 100 + k - 0.5, 100 + k) for k in range(40)]
    down = [(140 - k, 140 - k + 0.5, 140 - k - 0.5, 140 - k) for k in range(40)]
    df = make_df(up + down)
    line, direction = ext._supertrend(df, 10, 3.0)
    assert set(np.unique(direction)).issubset({1.0, -1.0})
    assert direction[39] == 1.0
    assert direction[-1] == -1.0


# ════════════════════════════════════════════════════════════════════════
# 2. ALPHA NODES — exact signal placement
# ════════════════════════════════════════════════════════════════════════

def test_v2_alpha_threshold_cross_up_and_down():
    values = [10, 20, 29, 31, 40, 32, 29, 25]  # crosses 30 up at i=3, down at i=6
    df = make_df([(v, v, v, v) for v in values])
    outs = eval_alpha("alpha.threshold", df,
                       {"long_level": 30, "short_level": 30, "direction": "both"},
                       lambda i: {"value": values[i]})
    fires = [(i, o["insight"].direction) for i, o in enumerate(outs) if o["insight"]]
    assert fires == [(3, "Bull"), (6, "Bear")]


def test_v2_alpha_engulfing_exact_pattern():
    # bar0: bearish body (o=10,c=8). bar1: bullish body engulfing it (o=7.5,c=10.5)
    bars = [(10, 10.2, 7.8, 8), (7.5, 10.6, 7.4, 10.5), (10.5, 10.6, 10.4, 10.5)]
    df = make_df(bars)
    outs = eval_alpha("alpha.engulfing", df, {"direction": "both"}, lambda i: {})
    fires = [(i, o["insight"].direction) for i, o in enumerate(outs) if o["insight"]]
    assert fires == [(1, "Bull")]


def test_v2_alpha_combine_and_or_truth_table():
    from backend.engine.builder_v2.types import Insight
    bull = Insight(direction="Bull", bar_idx=0)
    bear = Insight(direction="Bear", bar_idx=0)
    and_fn = NODE_LIBRARY["alpha.combine_and"].eval_fn
    or_fn  = NODE_LIBRARY["alpha.combine_or"].eval_fn
    ctx = RunContext()

    assert and_fn(None, 0, ctx, {"a": bull, "b": bull}, {})["insight"].direction == "Bull"
    assert and_fn(None, 0, ctx, {"a": bull, "b": bear}, {})["insight"] is None
    assert and_fn(None, 0, ctx, {"a": None, "b": bull}, {})["insight"] is None

    assert or_fn(None, 0, ctx, {"a": bull, "b": None}, {})["insight"].direction == "Bull"
    assert or_fn(None, 0, ctx, {"a": None, "b": bear}, {})["insight"].direction == "Bear"
    assert or_fn(None, 0, ctx, {"a": bull, "b": bear}, {})["insight"].direction == "Bull"  # a wins


def test_v2_alpha_fvg_exact_3bar_gap():
    # bar0 high=10. bar1 = filler. bar2 low=10.5 -> gap of 0.5 vs bar0 high (>= min_pips*pip)
    bars = [(9.5, 10.0, 9.4, 9.9), (10.2, 10.3, 10.1, 10.2), (10.6, 10.7, 10.5, 10.6)]
    df = make_df(bars)
    outs = eval_alpha("alpha.fvg", df, {"min_pips": 2.0, "direction": "both"}, lambda i: {},
                       ctx=RunContext(pip=0.1))
    fires = [(i, o["insight"].direction) for i, o in enumerate(outs) if o["insight"]]
    assert fires == [(2, "Bull")]   # 10.5 - 10.0 = 0.5 = 5 pips >= min_pips(2)


def test_v2_alpha_liquidity_sweep_detects_equal_highs_sweep():
    # The node requires i >= lookback + 2 before it evaluates at all (warmup
    # guard), so with lookback=30 the earliest possible signal is i=32 —
    # pad with enough quiet bars for the sweep bar to actually be evaluated.
    quiet = [(100, 105, 99, 100)] * 35
    sweep = (100, 106, 99.5, 104)   # wicks to 106, closes at 104 (< 105 - tol)
    df = make_df(quiet + [sweep])
    sweep_idx = len(quiet)
    outs = eval_alpha("alpha.liquidity_sweep", df,
                       {"lookback": 30, "count": 2, "tolerance_pips": 3, "min_pierce_pips": 1.0, "direction": "both"},
                       lambda i: {}, ctx=RunContext(pip=0.1))
    fires = [(i, o["insight"].direction) for i, o in enumerate(outs) if o["insight"]]
    assert fires == [(sweep_idx, "Bear")]


# ════════════════════════════════════════════════════════════════════════
# 3. FILTER NODES — pass / block behavior
# ════════════════════════════════════════════════════════════════════════

def test_v2_filter_session_blocks_outside_window():
    from backend.engine.builder_v2.types import Insight
    t0 = pd.Timestamp("2024-01-01 05:00:00")
    df = pd.DataFrame({
        "time": [t0, t0 + pd.Timedelta(hours=5), t0 + pd.Timedelta(hours=15)],  # hours 5, 10, 20
        "O": [1, 1, 1], "H": [1, 1, 1], "L": [1, 1, 1], "C": [1, 1, 1],
    })
    ins = Insight(direction="Bull", bar_idx=0)
    outs = eval_alpha("filter.session", df, {"start_hour": 7, "end_hour": 17},
                       lambda i: {"insight": ins})
    passed = [o["insight"] is not None for o in outs]
    assert passed == [False, True, False]   # hour 5 blocked, 10 passes, 20 blocked


def test_v2_filter_threshold_passes_only_in_range():
    from backend.engine.builder_v2.types import Insight
    ins = Insight(direction="Bull", bar_idx=0)
    values = [10, 30, 60, 90]
    df = make_df([(1, 1, 1, 1)] * 4)
    outs = eval_alpha("filter.threshold", df, {"min": 25, "max": 75},
                       lambda i: {"insight": ins, "value": values[i]})
    passed = [o["insight"] is not None for o in outs]
    assert passed == [False, True, True, False]


def test_v2_filter_cooldown_blocks_then_releases():
    from backend.engine.builder_v2.types import Insight
    ins = Insight(direction="Bull", bar_idx=0)
    df = make_df([(1, 1, 1, 1)] * 15)
    outs = eval_alpha("filter.cooldown", df, {"bars": 10}, lambda i: {"insight": ins})
    passed = [o["insight"] is not None for o in outs]
    assert passed[0] is True             # first one always passes
    assert all(p is False for p in passed[1:10])   # blocked for the next 9 bars
    assert passed[10] is True            # released exactly at bar 10


# ════════════════════════════════════════════════════════════════════════
# 4. INTEGRATION — every production template, every node combination
# ════════════════════════════════════════════════════════════════════════

_TEMPLATE_IDS = [t["id"] for t in list_templates()]


@pytest.mark.parametrize("template_id", _TEMPLATE_IDS)
def test_every_template_emits_well_formed_setups(template_id):
    df = synth_series(n=600, seed=5)
    graph = get_template(template_id)
    strat = GraphV2Strategy(graph)
    setups = strat.detect(df, {"pip": 0.1})
    n = len(df)

    for s in setups:
        assert s["direction"] in ("Bull", "Bear"), f"{template_id}: bad direction"
        assert 0 <= s["signal_idx"] < n, f"{template_id}: signal_idx out of range"
        assert np.isfinite(s["entry"]) and np.isfinite(s["sl"]), f"{template_id}: non-finite price"
        assert s["risk"] > 0, f"{template_id}: non-positive risk"
        assert s["risk"] == pytest.approx(abs(s["entry"] - s["sl"]), rel=1e-6), \
            f"{template_id}: risk != |entry-sl|"
        if s["direction"] == "Bull":
            assert s["sl"] < s["entry"], f"{template_id}: long stop not below entry"
        else:
            assert s["sl"] > s["entry"], f"{template_id}: short stop not above entry"


@pytest.mark.parametrize("template_id", _TEMPLATE_IDS)
def test_every_template_is_deterministic(template_id):
    df = synth_series(n=400, seed=5)
    graph = get_template(template_id)
    s1 = [(s["signal_idx"], s["direction"], round(s["entry"], 6))
          for s in GraphV2Strategy(graph).detect(df.copy(), {"pip": 0.1})]
    s2 = [(s["signal_idx"], s["direction"], round(s["entry"], 6))
          for s in GraphV2Strategy(graph).detect(df.copy(), {"pip": 0.1})]
    assert s1 == s2, f"{template_id}: same input produced different setups"


@pytest.mark.parametrize("template_id", _TEMPLATE_IDS)
def test_every_template_has_no_lookahead(template_id):
    """Signals in the early part of the data must be identical whether or not
    future bars exist — the exact property that makes a backtest's numbers
    trustworthy across different slider/parameter combinations. A node that
    peeks at future bars would give unrealistically good (wrong) results."""
    full = synth_series(n=600, seed=5)
    cut = 380
    margin = 80   # ignore signals near the cut (indicator warmup edge effects)
    graph = get_template(template_id)

    sig_full = {s["signal_idx"]: (s["direction"], round(s["entry"], 6))
                for s in GraphV2Strategy(graph).detect(full.copy(), {"pip": 0.1})
                if s["signal_idx"] < cut - margin}
    sig_cut = {s["signal_idx"]: (s["direction"], round(s["entry"], 6))
               for s in GraphV2Strategy(graph).detect(full.iloc[:cut].copy(), {"pip": 0.1})
               if s["signal_idx"] < cut - margin}

    assert sig_full == sig_cut, (
        f"{template_id}: early signals changed when future bars were removed "
        f"-> lookahead. only_full={set(sig_full)-set(sig_cut)} "
        f"only_cut={set(sig_cut)-set(sig_full)}")


def test_some_templates_actually_fire():
    # Guards against the whole suite silently passing because nothing fired.
    df = synth_series(n=600, seed=5)
    fired = []
    for tid in _TEMPLATE_IDS:
        setups = GraphV2Strategy(get_template(tid)).detect(df.copy(), {"pip": 0.1})
        if setups:
            fired.append(tid)
    assert len(fired) >= 3, f"only {fired} produced setups — series may be unrepresentative"
