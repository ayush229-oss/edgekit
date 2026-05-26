"""
Smoke test for the visual-node-builder engine.

  - Loads each starter template
  - Runs it through validate → GraphStrategy.detect → simulate → metrics
  - Prints a one-liner per template

Run: python -m backend.engine.test_builder
"""
from __future__ import annotations
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from backend.engine.core import load_mt5, simulate, compute_metrics, infer_pip_from_df
from backend.engine.builder import (
    NODE_LIBRARY, GraphStrategy, list_templates, get_template,
)


def main():
    print(f"Node library: {len(NODE_LIBRARY)} nodes")
    for cat in ["signal", "filter", "entry", "risk"]:
        names = [t for t, s in NODE_LIBRARY.items() if s.category == cat]
        print(f"  {cat:7} ({len(names)}): {', '.join(n.split('.')[-1] for n in names)}")
    print()

    df  = load_mt5("XAUUSD", "M15", n_bars=5000)
    pip = infer_pip_from_df(df, "XAUUSD")
    print(f"Loaded {len(df):,} XAUUSD M15 bars, pip={pip}\n")

    print(f"{'template':<30} {'setups':>7} {'trades':>7} {'WR%':>6} {'totR':>8} {'PF':>6}")
    print("─" * 70)

    for t in list_templates():
        if t["id"] == "blank":
            continue
        graph  = get_template(t["id"])
        strat  = GraphStrategy(graph)
        setups = strat.detect(df, {"pip": pip})
        tdf = simulate(
            df, setups,
            pip              = pip,
            target_r         = 3.0,
            target_close_pct = 0.5,
            trail_mode       = "candle",
            trail_start      = "after_target",
            trail_params     = {"buf_pips": 1},
            max_concurrent   = 1,
        )
        m = compute_metrics(tdf)
        if m is None:
            print(f"{t['name']:<30} {len(setups):>7} {'-':>7} {'-':>6} {'-':>8} {'-':>6}  (no resolved trades)")
            continue
        pf = m['profit_factor'] if m['profit_factor'] != float('inf') else 99.0
        print(f"{t['name']:<30} {len(setups):>7} {m['trades']:>7} {m['wr']:>6.1f} {m['total_r']:>+8.1f} {pf:>6.2f}")

    print("\nAll templates executed.")


if __name__ == "__main__":
    main()
