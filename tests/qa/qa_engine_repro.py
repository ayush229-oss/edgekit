"""
QA harness — Workflow #1: Backtest engine correctness & reproducibility.

Runs the REAL product pipeline (strategy.detect -> simulate -> compute_metrics)
on deterministic synthetic OHLCV data (no MT5 dependency, fully reproducible).

Checks:
  R1  Determinism      — identical input run twice -> byte-identical trade log + metrics
  R2  State leakage    — A, B, A again -> the two A runs are identical (no global state)
  R3  Edge cases       — empty / single-bar / flat / NaN-injected frames degrade
                         gracefully (no crash; metrics None when no resolved trades)

Run from repo root:
    python tests/qa/qa_engine_repro.py
Exit code 0 = all green, 1 = at least one failure.
"""
from __future__ import annotations
import sys, traceback
import numpy as np
import pandas as pd

from backend.engine.core import simulate, compute_metrics, infer_pip_from_df
from backend.engine.strategies import REGISTRY, get as get_strategy

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def log(name: str, status: str, detail: str = "") -> None:
    results.append((name, status, detail))
    mark = "[PASS]" if status == PASS else "[FAIL]"
    print(f"{mark} {name}" + (f" — {detail}" if detail else ""))


def make_ohlcv(n: int = 1500, seed: int = 42) -> pd.DataFrame:
    """Deterministic synthetic OHLCV resembling XAUUSD M15."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(0, 1.5, n).cumsum()
    close = 2000.0 + rets
    o = close + rng.normal(0, 0.5, n)
    spread = np.abs(rng.normal(0, 1.0, n)) + 0.2
    h = np.maximum(o, close) + spread
    l = np.minimum(o, close) - spread
    v = rng.integers(100, 5000, n).astype(float)
    t = pd.date_range("2025-01-01", periods=n, freq="15min")
    return pd.DataFrame({"time": t, "O": o, "H": h, "L": l, "C": close, "V": v})


def run_pipeline(strategy_id: str, df: pd.DataFrame) -> tuple[pd.DataFrame, dict | None]:
    """Mirror of backend/api/main.py run_backtest steps 2-4."""
    pip = infer_pip_from_df(df, "XAUUSD")
    strat = get_strategy(strategy_id)()
    params = {**strat.default_params(), "pip": pip}
    setups = strat.detect(df, params)
    tdf = simulate(df, setups, pip=pip, target_r=2.0)
    m = compute_metrics(tdf)
    return tdf, m


def metrics_signature(m: dict | None) -> str:
    if m is None:
        return "None"
    keys = ["trades", "wr", "ev", "total_r", "max_dd", "profit_factor", "final_equity"]
    return "|".join(f"{k}={m.get(k)!r}" for k in keys)


# ─── R1: Determinism per strategy ────────────────────────────────────────────
def test_determinism(df: pd.DataFrame) -> None:
    for sid in REGISTRY.keys():
        try:
            t1, m1 = run_pipeline(sid, df)
            t2, m2 = run_pipeline(sid, df)
            same_log = t1.equals(t2)
            same_metrics = metrics_signature(m1) == metrics_signature(m2)
            if same_log and same_metrics:
                n = 0 if m1 is None else m1.get("trades", 0)
                log(f"R1 determinism [{sid}]", PASS, f"{len(t1)} setups, {n} trades")
            else:
                log(f"R1 determinism [{sid}]", FAIL,
                    f"log_equal={same_log} metrics_equal={same_metrics}")
        except Exception as e:
            log(f"R1 determinism [{sid}]", FAIL, f"EXCEPTION {type(e).__name__}: {e}")


# ─── R2: Cross-strategy state leakage ────────────────────────────────────────
def test_state_leakage(df: pd.DataFrame) -> None:
    sids = list(REGISTRY.keys())
    if len(sids) < 2:
        log("R2 state-leakage", FAIL, "need >=2 strategies")
        return
    a, b = sids[0], sids[1]
    try:
        _, m_a1 = run_pipeline(a, df)
        _, _    = run_pipeline(b, df)
        _, m_a2 = run_pipeline(a, df)
        if metrics_signature(m_a1) == metrics_signature(m_a2):
            log("R2 state-leakage", PASS, f"{a} stable across interleaved {b} run")
        else:
            log("R2 state-leakage", FAIL,
                f"{a} drifted: {metrics_signature(m_a1)} != {metrics_signature(m_a2)}")
    except Exception as e:
        log("R2 state-leakage", FAIL, f"EXCEPTION {type(e).__name__}: {e}")


# ─── R3: Edge cases ──────────────────────────────────────────────────────────
def test_edge_cases() -> None:
    sid = "ema_cross"
    full = make_ohlcv()

    # empty frame
    _edge("R3 empty-frame", sid, full.iloc[0:0].copy())
    # single bar
    _edge("R3 single-bar", sid, full.iloc[0:1].copy())
    # flat market (no volatility -> no signals -> no resolved trades)
    flat = full.copy()
    for c in ("O", "H", "L", "C"):
        flat[c] = 2000.0
    _edge("R3 flat-market", sid, flat)
    # NaN injection in the close column
    nanned = full.copy()
    nanned.loc[nanned.index[100:120], "C"] = np.nan
    _edge("R3 nan-injected", sid, nanned)


def _edge(name: str, sid: str, df: pd.DataFrame) -> None:
    """An edge frame must not crash. Returning None metrics is acceptable."""
    try:
        tdf, m = run_pipeline(sid, df)
        log(name, PASS, f"handled gracefully, metrics={'None' if m is None else m.get('trades')} trades")
    except Exception as e:
        log(name, FAIL, f"EXCEPTION {type(e).__name__}: {e}\n{traceback.format_exc()}")


def main() -> int:
    print(f"Registry: {len(REGISTRY)} strategies -> {', '.join(REGISTRY.keys())}\n")
    df = make_ohlcv()
    print(f"Synthetic data: {len(df)} bars, pip={infer_pip_from_df(df, 'XAUUSD')}\n")
    print("── R1 Determinism ─────────────────────────────────────────────")
    test_determinism(df)
    print("\n── R2 State leakage ───────────────────────────────────────────")
    test_state_leakage(df)
    print("\n── R3 Edge cases ──────────────────────────────────────────────")
    test_edge_cases()

    n_fail = sum(1 for _, s, _ in results if s == FAIL)
    n_pass = sum(1 for _, s, _ in results if s == PASS)
    print(f"\n=========== {n_pass} passed, {n_fail} failed ===========")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
