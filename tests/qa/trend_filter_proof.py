"""
Investigates whether ema_cross's `trend_filter` can ever actually filter a
setup, on any data -- real, choppy, or adversarially constructed.

Finding: it can't. This is a mathematical property of EMA recursion, not a
data coincidence. Proof:

  slow[i] = a_s*C[i] + (1-a_s)*slow[i-1]
  fast[i] = a_f*C[i] + (1-a_f)*fast[i-1]      (a_f > a_s, since fast_period < slow_period)

  Claim: C[i] > slow[i]  <=>  C[i] > slow[i-1]
  Proof: C[i] > slow[i]
         <=> C[i] > a_s*C[i] + (1-a_s)*slow[i-1]
         <=> (1-a_s)*C[i] > (1-a_s)*slow[i-1]
         <=> C[i] > slow[i-1]                                          (1-a_s > 0)

  At a fresh bull cross: fast[i] > slow[i]  and  fast[i-1] <= slow[i-1].
  From the fast[i] expansion and fast[i-1] <= slow[i-1]:
      (a_f-a_s)*C[i] > (1-a_s)*slow[i-1] - (1-a_f)*fast[i-1]
                     >= (1-a_s)*slow[i-1] - (1-a_f)*slow[i-1]   (since fast[i-1] <= slow[i-1], and -(1-a_f) flips it)
                     =  (a_f-a_s)*slow[i-1]
  Dividing by (a_f-a_s) > 0:  C[i] > slow[i-1]  <=>  C[i] > slow[i]  (by the identity above).

  So C[i] > slow[i] is GUARANTEED at every bull cross -- the filter's skip
  condition (C[i] <= slow[i]) can never be true. Symmetric argument for bear
  crosses. This holds for ANY price series, given fast_period < slow_period
  (which the code already enforces via `if fast_p >= slow_p: return []`).

This script (a) verifies the proof numerically on adversarial synthetic data
designed to maximize whipsaw crosses, and (b) runs the full backtest pipeline
(detect -> simulate -> compute_metrics) with trend_filter True vs False to
confirm the end-to-end result is identical, not just the raw signal count.
"""
import numpy as np
import pandas as pd

from backend.engine.core import indicators as ind
from backend.engine.core import simulate, compute_metrics
from backend.engine.strategies import get as get_strategy

EMA_PAIRS = [(2, 5), (2, 10), (3, 8), (5, 15), (9, 21), (2, 200)]


def make_choppy(n=4000, seed=0, kind="sawtooth"):
    """Deliberately adversarial OHLCV designed to maximize EMA whipsaws."""
    rng = np.random.default_rng(seed)
    t = pd.date_range("2025-01-01", periods=n, freq="5min")
    if kind == "sawtooth":
        # Sharp alternating moves every 2-4 bars -- maximum crossing frequency.
        period = rng.integers(2, 5, size=n)
        phase = np.cumsum(1.0 / period) % 1.0
        base = 100 * np.sign(np.sin(2 * np.pi * phase * 10))
        close = 2000 + base.cumsum() * 0.0 + np.cumsum(np.diff(np.r_[0, base])) * 0  # placeholder
        # simpler: alternating square wave + small noise, no drift
        square = np.where((np.arange(n) // 3) % 2 == 0, 1.0, -1.0)
        close = 2000 + np.cumsum(square) * 0.3 + rng.normal(0, 0.05, n)
    elif kind == "meanrevert":
        # Strong mean reversion: pulled back to 2000 every step + noise.
        close = np.empty(n)
        close[0] = 2000
        for i in range(1, n):
            close[i] = close[i - 1] + 0.6 * (2000 - close[i - 1]) + rng.normal(0, 1.2)
    else:
        raise ValueError(kind)
    close = np.asarray(close, dtype=float)
    o = close + rng.normal(0, 0.05, n)
    spread = np.abs(rng.normal(0, 0.3, n)) + 0.05
    h = np.maximum(o, close) + spread
    l = np.minimum(o, close) - spread
    v = np.ones(n)
    return pd.DataFrame({"time": t, "O": o, "H": h, "L": l, "C": close, "V": v})


def count_filter_triggers(df, fast_p, slow_p):
    fast = ind.ema(df["C"], fast_p)
    slow = ind.ema(df["C"], slow_p)
    prev_above = fast.shift(1) > slow.shift(1)
    cur_above = fast > slow
    bull_cross = cur_above & ~prev_above
    bear_cross = ~cur_above & prev_above
    Cv = df["C"].values
    bull_idx = [i for i in range(len(df)) if bull_cross.iloc[i]]
    bear_idx = [i for i in range(len(df)) if bear_cross.iloc[i]]
    bull_filtered = sum(1 for i in bull_idx if Cv[i] <= slow.iloc[i])
    bear_filtered = sum(1 for i in bear_idx if Cv[i] >= slow.iloc[i])
    return len(bull_idx) + len(bear_idx), bull_filtered + bear_filtered


def full_pipeline_identical(df, fast_p, slow_p, atr_p=14, sl_mult=1.5):
    cls = get_strategy("ema_cross")
    pip = 0.1
    base = {**cls.default_params(), "pip": pip, "fast_ema": fast_p, "slow_ema": slow_p,
            "atr_period": atr_p, "sl_atr_mult": sl_mult}
    s_on = cls().detect(df, {**base, "trend_filter": True})
    s_off = cls().detect(df, {**base, "trend_filter": False})
    same_setups = s_on == s_off
    if not s_on:
        return same_setups, None, None
    t_on = simulate(df, s_on, pip=pip)
    t_off = simulate(df, s_off, pip=pip)
    m_on = compute_metrics(t_on)
    m_off = compute_metrics(t_off)
    same_metrics = (m_on or {}).get("total_r") == (m_off or {}).get("total_r")
    return same_setups, m_on, same_metrics


def main():
    rows = []
    for kind in ("sawtooth", "meanrevert"):
        df = make_choppy(kind=kind, seed=1)
        for fast_p, slow_p in EMA_PAIRS:
            crosses, filtered = count_filter_triggers(df, fast_p, slow_p)
            same_setups, m_on, same_metrics = full_pipeline_identical(df, fast_p, slow_p)
            rows.append({
                "data_kind": kind, "fast_ema": fast_p, "slow_ema": slow_p,
                "total_crosses": crosses, "would_be_filtered": filtered,
                "filter_trigger_rate_pct": round(filtered / crosses * 100, 2) if crosses else None,
                "setups_identical_on_vs_off": same_setups,
                "trades_with_filter_on": (m_on or {}).get("trades"),
                "total_r_identical_on_vs_off": same_metrics,
            })
            print(f"{kind:<11} fast={fast_p:<3} slow={slow_p:<4} crosses={crosses:<5} "
                  f"filtered={filtered:<5} setups_identical={same_setups} metrics_identical={same_metrics}")

    out = pd.DataFrame(rows)
    out_path = r"C:\Users\Ayush\projects\edgekit\tests\qa\trend_filter_stress_test.csv"
    out.to_csv(out_path, index=False)

    total_crosses = out["total_crosses"].sum()
    total_filtered = out["would_be_filtered"].sum()
    print(f"\nGRAND TOTAL across all adversarial synthetic tests: "
          f"{total_crosses} crosses, {total_filtered} ever filtered "
          f"({total_filtered/total_crosses*100:.4f}%)")
    print(f"All setups_identical_on_vs_off True: {out['setups_identical_on_vs_off'].all()}")
    print(f"Saved raw results: {out_path}")
    return out


if __name__ == "__main__":
    main()
