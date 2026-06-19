"""QA check for FINDING-1: NaN detection in validate_ohlcv + dropped-row surfacing in load_csv."""
import io
import numpy as np
import pandas as pd

from backend.engine.core import validate_ohlcv, load_csv

results = []


def check(name, cond, detail=""):
    results.append(cond)
    print(("[PASS] " if cond else "[FAIL] ") + name + (f" -- {detail}" if detail else ""))


def frame(n=300):
    t = pd.date_range("2025-01-01", periods=n, freq="15min")
    base = np.linspace(2000, 2100, n)
    return pd.DataFrame({"time": t, "O": base, "H": base + 1, "L": base - 1,
                         "C": base, "V": np.ones(n)})


def main():
    # 1) Clean frame -> no nan_rows flag
    issues = validate_ohlcv(frame())
    check("1 clean frame: no nan_rows", "nan_rows" not in issues, str(issues))

    # 2) NaN-injected frame -> nan_rows counted + quality dinged
    f = frame()
    f.loc[f.index[100:120], "C"] = np.nan
    issues = validate_ohlcv(f)
    check("2 nan frame flagged", issues.get("nan_rows") == 20, str(issues.get("nan_rows")))
    check("2 quality dinged", issues["quality_score"] < 100, f"score={issues['quality_score']}")

    # 3) load_csv records rows_dropped for blank/invalid rows
    rows = ["time,open,high,low,close,volume"]
    base = pd.Timestamp("2025-01-01")
    for i in range(50):
        t = (base + pd.Timedelta(minutes=15 * i)).strftime("%Y-%m-%d %H:%M:%S")
        if i in (10, 20, 30):           # 3 corrupt rows (non-numeric close)
            rows.append(f"{t},2000,2002,1998,NA,100")
        else:
            rows.append(f"{t},2000,2002,1998,2001,100")
    df = load_csv("\n".join(rows).encode())
    check("3 rows_dropped recorded", df.attrs.get("rows_dropped") == 3,
          f"rows_dropped={df.attrs.get('rows_dropped')}, bars={len(df)}")

    ok = all(results)
    print(f"\nDATA-VALIDATION CHECK: {'PASS' if ok else 'FAIL'} ({sum(results)}/{len(results)})")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
