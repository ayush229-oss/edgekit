"""Scan several MT5 symbol/timeframe/EMA-period combos to find data where the
ema_cross trend_filter condition (Cv[i] vs slow EMA at the cross bar) actually
disagrees with cur_above at least sometimes -- i.e. real whipsaw conditions."""
from backend.engine.core import load_mt5
from backend.engine.core import indicators as ind

CANDIDATES = [
    ("EURUSD", "M1", 3000), ("EURUSD", "M5", 3000),
    ("AUDNZD", "M5", 3000), ("AUDNZD", "M15", 3000),
    ("EURGBP", "M5", 3000), ("EURGBP", "M15", 3000),
    ("USDJPY", "M1", 3000),
    ("XAUUSD", "M1", 3000),
    ("AUS200", "M5", 3000),
]
EMA_PAIRS = [(2, 5), (2, 10), (5, 15)]


def scan(symbol, tf, n_bars, fast_p, slow_p):
    df = load_mt5(symbol, tf, n_bars=n_bars)
    fast = ind.ema(df["C"], fast_p)
    slow = ind.ema(df["C"], slow_p)
    prev_above = fast.shift(1) > slow.shift(1)
    cur_above = fast > slow
    bull_cross = cur_above & ~prev_above
    bear_cross = ~cur_above & prev_above
    Cv = df["C"].values

    bull_idx = [i for i in range(len(df)) if bull_cross.iloc[i]]
    bear_idx = [i for i in range(len(df)) if bear_cross.iloc[i]]
    bull_would_filter = sum(1 for i in bull_idx if Cv[i] <= slow.iloc[i])
    bear_would_filter = sum(1 for i in bear_idx if Cv[i] >= slow.iloc[i])
    total_cross = len(bull_idx) + len(bear_idx)
    total_filtered = bull_would_filter + bear_would_filter
    return total_cross, total_filtered


def main():
    print(f"{'symbol':<8} {'tf':<4} {'fast/slow':<10} {'crosses':>8} {'would_filter':>13} {'pct':>7}")
    print("-" * 60)
    best = None
    for symbol, tf, n_bars in CANDIDATES:
        for fast_p, slow_p in EMA_PAIRS:
            try:
                total_cross, total_filtered = scan(symbol, tf, n_bars, fast_p, slow_p)
            except Exception as e:
                print(f"{symbol:<8} {tf:<4} {fast_p}/{slow_p:<7} ERROR: {e}")
                continue
            pct = (total_filtered / total_cross * 100) if total_cross else 0.0
            print(f"{symbol:<8} {tf:<4} {f'{fast_p}/{slow_p}':<10} {total_cross:>8} {total_filtered:>13} {pct:>6.1f}%")
            if total_filtered > 0 and (best is None or total_filtered > best[1]):
                best = (symbol, tf, n_bars, fast_p, slow_p, total_cross, total_filtered)
    print()
    if best:
        print("BEST candidate (most filter activity):", best)
    else:
        print("NO candidate among real-data scans ever triggered the filter.")


if __name__ == "__main__":
    main()
