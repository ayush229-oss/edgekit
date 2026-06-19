"""
Smoke test for the v2 graph engine.

Validates:
  - Both templates parse + topo-sort cleanly
  - Donchian breakout fires real setups on live XAUUSD bars
  - EMA cross still works under the new typed-wire model
  - complexity_score returns sensible levels

Run: python -m backend.engine.manual_check_builder_v2
"""
from __future__ import annotations
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from backend.engine.core import load_mt5, simulate, compute_metrics, infer_pip_from_df
from backend.engine.builder_v2 import (
    NODE_LIBRARY, GraphV2Strategy, list_templates, get_template, complexity_score,
)


def main():
    print(f"v2 node library: {len(NODE_LIBRARY)} nodes")
    by_lane = {}
    for nt, s in NODE_LIBRARY.items():
        by_lane.setdefault(s.lane, []).append(nt.split(".")[-1])
    for lane in ["universe", "indicator", "alpha", "filter", "sizing", "risk", "exit", "execution"]:
        names = by_lane.get(lane, [])
        print(f"  {lane:11} ({len(names)}): {', '.join(names)}")
    print()

    df  = load_mt5("XAUUSD", "M15", n_bars=5000)
    pip = infer_pip_from_df(df, "XAUUSD")
    print(f"Loaded {len(df):,} XAUUSD M15 bars, pip={pip}\n")

    print(f"{'template':<32} {'setups':>7} {'trades':>7} {'WR%':>6} {'totR':>8} {'PF':>6} {'cmplx':>6}")
    print("─" * 80)

    for t in list_templates():
        graph = get_template(t["id"])
        cs    = complexity_score(graph)
        strat = GraphV2Strategy(graph)
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
            print(f"{t['name']:<32} {len(setups):>7} {'-':>7} {'-':>6} {'-':>8} {'-':>6} {cs['score']:>6}  (no trades)")
            continue
        pf = m['profit_factor'] if m['profit_factor'] != float('inf') else 99.0
        print(f"{t['name']:<32} {len(setups):>7} {m['trades']:>7} {m['wr']:>6.1f} {m['total_r']:>+8.1f} {pf:>6.2f} {cs['score']:>5}/{cs['level'][:1].upper()}")

    print("\nAll v2 templates executed.")


if __name__ == "__main__":
    main()
