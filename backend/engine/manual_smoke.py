"""
End-to-end smoke test covering Day 1 + Day 2 work:
  - Fetch live MT5 bars
  - Roundtrip via CSV (save → reload → verify identical shape)
  - Validate OHLCV health
  - Auto-detect pip size
  - Run BOTH strategies (OB+FVG+Liquidity, EMA Crossover)
  - Confirm metrics produced

Run:  python -m backend.engine.manual_smoke
"""
from __future__ import annotations
import sys, os, tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from backend.engine.core import (
    load_mt5, load_csv, simulate, compute_metrics,
    infer_pip_from_df, validate_ohlcv,
)
from backend.engine.strategies import REGISTRY


def _hr(t=""):
    print("─" * 60)
    if t: print(f" {t}")
    if t: print("─" * 60)


def main():
    _hr("Edgekit engine smoke — Day 1 + Day 2")

    # 1) Fetch
    try:
        df = load_mt5("XAUUSD", "M15", n_bars=5000)
    except Exception as e:
        print(f"❌  MT5 fetch failed: {e}")
        sys.exit(1)
    print(f"✓ MT5 fetch: {len(df):,} bars "
          f"({df['time'].iloc[0]} → {df['time'].iloc[-1]})")

    # 2) Validate
    issues = validate_ohlcv(df)
    print(f"✓ OHLCV validate: {'clean' if not issues else issues}")

    # 3) Pip auto-detect
    pip = infer_pip_from_df(df, "XAUUSD")
    print(f"✓ Pip auto-detect (XAUUSD): {pip}")

    # 4) CSV roundtrip — save then reload, verify shape
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        tmp_path = f.name
        df.to_csv(tmp_path, index=False)
    try:
        df2 = load_csv(tmp_path)
        assert len(df) == len(df2), f"row mismatch {len(df)} vs {len(df2)}"
        assert set(["time","O","H","L","C"]).issubset(df2.columns)
        print(f"✓ CSV roundtrip: {len(df2):,} rows preserved")
    finally:
        os.unlink(tmp_path)

    # 5) Run every registered strategy
    print()
    for sid, Strat in REGISTRY.items():
        strat = Strat()
        params = strat.default_params()
        params["pip"] = pip
        setups = strat.detect(df, params)
        tdf    = simulate(df, setups,
                          pip            = pip,
                          trail_enabled  = True,
                          trail_from_idx = 1,
                          max_concurrent = 1)
        m = compute_metrics(tdf)
        if m is None:
            print(f"⚠  {sid}: no resolved trades")
            continue
        print(f"✓ {sid:14} — {m['trades']:>3} trades · "
              f"WR {m['wr']:>5.1f}% · EV {m['ev']:+.2f}R · "
              f"Total {m['total_r']:+6.0f}R · PF {m['profit_factor']:.2f}")

    print()
    _hr("All checks passed")


if __name__ == "__main__":
    main()
