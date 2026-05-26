"""
Universal data loader. Outputs a normalized OHLCV DataFrame with columns:
  time (datetime64), O, H, L, C, V (optional)

Sources supported:
  - CSV upload (any column order, auto-detected — MT5, MT4, TradingView,
                Binance, Yahoo, generic)
  - MT5 live fetch (when MetaTrader5 package available)
  - DataFrame passthrough (already normalized)
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Union
import io
import pandas as pd
import numpy as np


# ─── Column auto-detection ───────────────────────────────────────────────────
# Aliases listed in priority order — first match wins.
_COL_ALIASES = {
    "time": [
        "time", "datetime", "date", "timestamp", "Time", "Date", "Datetime",
        "DateTime", "Timestamp", "Open time", "open_time", "<DATE>", "<TIME>",
    ],
    "O": ["open", "Open", "O", "OPEN", "<OPEN>"],
    "H": ["high", "High", "H", "HIGH", "<HIGH>"],
    "L": ["low",  "Low",  "L", "LOW",  "<LOW>"],
    "C": ["close", "Close", "C", "CLOSE", "<CLOSE>", "adj_close", "Adj Close"],
    "V": ["volume", "Volume", "V", "vol", "tick_volume", "real_volume",
          "<TICKVOL>", "<VOL>", "Quote asset volume"],
}


def _strip_angle_brackets(cols) -> list:
    """MT5 exports columns like <DATE>, <OPEN>. Strip angle brackets for matching."""
    return [c.strip("<>").strip() for c in cols]


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to canonical names (time, O, H, L, C, V).
    Handles common broker exports: MT5, MT4, TradingView, Binance, Yahoo.
    """
    # Handle MT5/MT4 exports that split DATE and TIME into two columns
    cols_clean = {c: c.strip("<>").strip() for c in df.columns}
    df = df.rename(columns=cols_clean)
    if "DATE" in df.columns and "TIME" in df.columns and "time" not in df.columns:
        df["time"] = df["DATE"].astype(str) + " " + df["TIME"].astype(str)
        df = df.drop(columns=["DATE", "TIME"])

    rename_map: dict[str, str] = {}
    used = set()
    for canonical, aliases in _COL_ALIASES.items():
        for a in aliases:
            if a in df.columns and canonical not in used:
                rename_map[a] = canonical
                used.add(canonical)
                break
    df = df.rename(columns=rename_map)

    missing = [c for c in ("time", "O", "H", "L", "C") if c not in df.columns]
    if missing:
        raise ValueError(
            f"CSV missing required columns: {missing}. "
            f"Detected: {list(df.columns)}. "
            "Required: time/date, open, high, low, close (volume optional)."
        )
    return df


def _parse_time(series: pd.Series) -> pd.Series:
    """Parse a time column that might be Unix seconds, Unix ms, or a string."""
    # Numeric → epoch
    if pd.api.types.is_numeric_dtype(series):
        sample = series.dropna().iloc[0] if len(series.dropna()) else 0
        unit = "ms" if sample > 10_000_000_000 else "s"
        return pd.to_datetime(series, unit=unit, errors="coerce")
    # String → flexible parse
    return pd.to_datetime(series, errors="coerce", format="mixed")


def load_csv(source: Union[str, Path, io.IOBase, bytes]) -> pd.DataFrame:
    """Load OHLCV from a CSV path, file-like object, or raw bytes.
    Auto-detects column names from any major broker format.
    """
    if isinstance(source, bytes):
        source = io.BytesIO(source)
    # Try comma first, then tab (MT5 exports are tab-separated)
    try:
        df = pd.read_csv(source)
        if df.shape[1] == 1:
            raise ValueError("single column — likely wrong delimiter")
    except Exception:
        if hasattr(source, "seek"):
            source.seek(0)
        df = pd.read_csv(source, sep="\t")

    df = _normalize_columns(df)
    df["time"] = _parse_time(df["time"])
    df = df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    for c in ("O", "H", "L", "C"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["O", "H", "L", "C"]).reset_index(drop=True)
    if df.empty:
        raise ValueError("After cleaning, no usable OHLCV rows remain.")
    return df


def validate_ohlcv(df: pd.DataFrame) -> dict:
    """Sanity check an OHLCV frame. Returns dict of issues found (empty = healthy)."""
    issues = {}
    n = len(df)
    if n < 200:
        issues["too_few_bars"] = f"Only {n} bars — backtest needs ~200+ for stable stats."
    bad_hl  = (df["H"] < df["L"]).sum()
    bad_oc  = ((df["O"] > df["H"]) | (df["O"] < df["L"]) |
               (df["C"] > df["H"]) | (df["C"] < df["L"])).sum()
    if bad_hl: issues["high_below_low"]      = int(bad_hl)
    if bad_oc: issues["oc_outside_hl"]       = int(bad_oc)
    dupe = df["time"].duplicated().sum()
    if dupe: issues["duplicate_timestamps"]  = int(dupe)
    gaps = df["time"].diff().dropna()
    if len(gaps) > 5:
        median_gap = gaps.median()
        big_gaps   = (gaps > median_gap * 50).sum()
        if big_gaps: issues["large_time_gaps"] = int(big_gaps)
    return issues


def load_mt5(symbol: str, timeframe: str, n_bars: int = 5000) -> pd.DataFrame:
    """Fetch bars from a connected MT5 terminal."""
    try:
        import MetaTrader5 as mt5
    except ImportError as e:
        raise RuntimeError("MetaTrader5 package not installed. `pip install MetaTrader5`.") from e

    tf_map = {
        "M1":  mt5.TIMEFRAME_M1,
        "M5":  mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1":  mt5.TIMEFRAME_H1,
        "H4":  mt5.TIMEFRAME_H4,
        "D1":  mt5.TIMEFRAME_D1,
    }
    if timeframe not in tf_map:
        raise ValueError(f"Unsupported timeframe: {timeframe}. Use one of {list(tf_map)}")

    if not mt5.initialize():
        raise RuntimeError("Cannot connect to MT5. Is the terminal open and logged in?")

    rates = mt5.copy_rates_from_pos(symbol, tf_map[timeframe], 0, n_bars)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No bars returned for {symbol} {timeframe}")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.rename(columns={"open": "O", "high": "H", "low": "L", "close": "C",
                            "tick_volume": "V"})
    return df[["time", "O", "H", "L", "C", "V"]]


def pip_size(symbol: str | None = None, price_sample: float | None = None) -> float:
    """Best-guess pip size from symbol name and/or a sample price.

    Resolution order:
      1. Exact / partial symbol match
      2. Magnitude inference from a sample price
      3. Fallback = 1.0
    """
    if symbol:
        s = symbol.upper()
        if "XAU" in s or "GOLD" in s:            return 0.10
        if "XAG" in s or "SILVER" in s:          return 0.01
        if "JPY" in s:                            return 0.01
        if any(fx in s for fx in ("EUR", "GBP", "AUD", "NZD", "CHF", "CAD")):
            return 0.0001
        if "USD" in s and len(s) == 6:            return 0.0001    # USDXXX or XXXUSD forex
        if any(c in s for c in ("BTC", "ETH", "BNB", "SOL", "XRP")):
            return 1.0
        if any(c in s for c in ("NIFTY", "BANKNIFTY", "SENSEX", "NDX", "SPX", "DJI")):
            return 1.0

    if price_sample is not None and price_sample > 0:
        # Magnitude heuristic — works for unknown instruments
        if price_sample < 5:        return 0.0001     # forex majors
        if price_sample < 50:       return 0.001      # silver, JPY pairs, some crypto
        if price_sample < 500:      return 0.01       # stocks
        if price_sample < 5_000:    return 0.10       # gold
        if price_sample < 100_000:  return 1.0        # indices, ETH
        return 1.0                                    # BTC, large indices

    return 1.0


def infer_pip_from_df(df: pd.DataFrame, symbol: str | None = None) -> float:
    """Convenience: infer pip size from a loaded OHLCV frame."""
    sample = float(df["C"].iloc[-1]) if len(df) else None
    return pip_size(symbol, sample)
