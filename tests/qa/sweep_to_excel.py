"""
Generate an Excel workbook with every (coarse-grid) parameter combination for
each of the 10 strategy templates, backtested against real MT5 data.

Grid: 3 points per slider (min / default / max), default value used when a
slider's default isn't exactly min/mid/max. The `pip` field is excluded — it's
an auto-detected constant, not a user-facing slider. Boolean/select controls
use all their discrete options (2, so unaffected by "3-point").

One sheet per template; one row per parameter combination; columns = params +
metrics (trades, wr, ev, total_r, profit_factor, max_dd, final_equity) or an
error message if the combo produced no resolved trades.

Run:
    python tests/qa/sweep_to_excel.py
"""
from __future__ import annotations
import itertools
import time

import pandas as pd

from backend.engine.core import load_mt5, simulate, compute_metrics, infer_pip_from_df
from backend.engine.strategies import REGISTRY

SYMBOL, TIMEFRAME, N_BARS = "XAUUSD", "M15", 5000
OUT_XLSX = r"C:\Users\Ayush\projects\edgekit\tests\qa\EdgeKit_Strategy_Sweep.xlsx"


def grid_values(spec):
    """3 representative values for one slider: min, default, max (deduped, sorted)."""
    if spec.type in ("int", "float"):
        if spec.min is None or spec.max is None:
            return [spec.default]
        vals = {spec.min, spec.default, spec.max}
        vals = sorted(v for v in vals if v is not None)
        if spec.type == "int":
            vals = sorted(set(int(round(v)) for v in vals))
        return vals
    if spec.type == "select":
        return list(spec.options or [spec.default])
    if spec.type == "bool":
        return [True, False]
    return [spec.default]


def build_grid(cls):
    """Return (param_keys, list_of_param_dicts) — full cartesian product,
    excluding the auto-detected `pip` field."""
    schema = [s for s in (cls.param_schema or []) if s.key != "pip"]
    keys = [s.key for s in schema]
    value_lists = [grid_values(s) for s in schema]
    combos = list(itertools.product(*value_lists))
    return keys, [dict(zip(keys, c)) for c in combos]


def run_one(strat_cls, df, pip, params):
    """Run detect -> simulate -> compute_metrics for one parameter combo."""
    full_params = {**strat_cls.default_params(), **params, "pip": pip}
    strat = strat_cls()
    setups = strat.detect(df, full_params)
    tdf = simulate(df, setups, pip=pip)
    m = compute_metrics(tdf)
    return m


def main():
    print(f"Loading {SYMBOL} {TIMEFRAME} ({N_BARS} bars) from MT5...")
    df = load_mt5(SYMBOL, TIMEFRAME, n_bars=N_BARS)
    pip = infer_pip_from_df(df, SYMBOL)
    print(f"Loaded {len(df)} bars, pip={pip}\n")

    writer = pd.ExcelWriter(OUT_XLSX, engine="openpyxl")
    summary_rows = []
    t0 = time.time()

    for sid, cls in REGISTRY.items():
        keys, combos = build_grid(cls)
        print(f"{sid:<16} {len(keys)} sliders -> {len(combos)} combinations")
        rows = []
        t_strat = time.time()
        for params in combos:
            try:
                m = run_one(cls, df, pip, params)
            except Exception as e:
                rows.append({**params, "error": f"{type(e).__name__}: {e}"})
                continue
            if m is None:
                rows.append({**params, "trades": 0, "error": "No resolved trades"})
                continue
            rows.append({
                **params,
                "trades":        m["trades"],
                "win_rate_pct":  round(m["wr"], 2),
                "ev_r":          round(m["ev"], 4),
                "total_r":       round(m["total_r"], 2),
                "profit_factor": (round(m["profit_factor"], 3)
                                  if m["profit_factor"] != float("inf") else "inf"),
                "max_dd_pct":    round(m["max_dd"], 2),
                "final_equity":  round(m["final_equity"], 2),
            })
        sheet_df = pd.DataFrame(rows)
        sheet_df.to_excel(writer, sheet_name=sid[:31], index=False)
        elapsed = time.time() - t_strat
        n_ok = sum(1 for r in rows if "error" not in r)
        summary_rows.append({
            "template": sid, "sliders": len(keys), "combinations": len(combos),
            "with_trades": n_ok, "seconds": round(elapsed, 1),
        })
        print(f"  -> {n_ok}/{len(combos)} produced trades, {elapsed:.1f}s")

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_excel(writer, sheet_name="SUMMARY", index=False)
    writer.close()

    total = time.time() - t0
    print(f"\nDone in {total:.1f}s. Workbook: {OUT_XLSX}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
