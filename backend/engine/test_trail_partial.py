"""
Verify the partial-close-at-target + trail behavior.
Specifically: when trail_mode != 'none' with after_target start,
varying target_close_pct should produce DIFFERENT exit distributions
(not the identical metrics bug we had before).

Run: python -m backend.engine.test_trail_partial
"""
from __future__ import annotations
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from backend.engine.core import load_mt5, simulate, compute_metrics, infer_pip_from_df
from backend.engine.strategies import get as get_strategy


def run(close_pct: float, trail_mode: str, trail_start: str, df, pip, setups):
    tdf = simulate(
        df, setups,
        pip              = pip,
        target_r         = 3.0,
        target_close_pct = close_pct,
        trail_mode       = trail_mode,
        trail_start      = trail_start,
        trail_params     = {"buf_pips": 1},
        max_concurrent   = 1,
    )
    m = compute_metrics(tdf)
    if m is None:
        return None
    exits = m["exit_counts"]
    return {
        "trades":  m["trades"],
        "wr":      m["wr"],
        "total_r": m["total_r"],
        "TP1":     int(exits.get("TP1", 0)),
        "SL":      int(exits.get("SL", 0)),
        "Trail":   int(exits.get("Trail", 0)),
        "BE":      int(exits.get("BE", 0)),
    }


def main():
    df = load_mt5("XAUUSD", "M15", n_bars=5000)
    pip = infer_pip_from_df(df, "XAUUSD")
    Strat = get_strategy("ob_fvg_liq")
    strat = Strat()
    params = {**strat.default_params(), "pip": pip}
    setups = strat.detect(df, params)
    print(f"Loaded {len(df):,} bars, {len(setups)} setups, pip={pip}\n")

    print(f"{'config':<32} {'trades':>6} {'WR%':>6} {'totR':>7} {'TP1':>5} {'SL':>4} {'Trail':>6} {'BE':>4}")
    print("─" * 78)

    # Baseline: no trail (full exit at target)
    r = run(1.0, "none", "after_target", df, pip, setups)
    print(f"{'no trail':<32} {r['trades']:>6} {r['wr']:>6.1f} {r['total_r']:>+7.1f} {r['TP1']:>5} {r['SL']:>4} {r['Trail']:>6} {r['BE']:>4}")

    # Trail with various close_pct values
    for pct in [1.0, 0.75, 0.5, 0.25, 0.0]:
        r = run(pct, "candle", "after_target", df, pip, setups)
        lbl = f"candle/after, close={int(pct*100)}%"
        print(f"{lbl:<32} {r['trades']:>6} {r['wr']:>6.1f} {r['total_r']:>+7.1f} {r['TP1']:>5} {r['SL']:>4} {r['Trail']:>6} {r['BE']:>4}")

    # Sanity: immediate trail (close_pct ignored — trail starts at fill)
    r = run(0.5, "candle", "immediate", df, pip, setups)
    print(f"{'candle/immediate':<32} {r['trades']:>6} {r['wr']:>6.1f} {r['total_r']:>+7.1f} {r['TP1']:>5} {r['SL']:>4} {r['Trail']:>6} {r['BE']:>4}")


if __name__ == "__main__":
    main()
