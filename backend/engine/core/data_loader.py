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


# ─── Data-source caching ────────────────────────────────────────────────────
# Bars are cached briefly per (symbol, timeframe, n_bars) so repeated runs don't
# re-hit the MT5 bridge / Yahoo, and so a momentarily-offline bridge still serves
# the last good data. Each cached frame keeps its data_source label in .attrs.
_BARS_CACHE: dict[tuple, tuple[float, pd.DataFrame]] = {}
_BARS_TTL = float(__import__("os").environ.get("BARS_CACHE_TTL", "120"))


def _set_source(df: pd.DataFrame, provider: str, via: str, symbol: str, label: str) -> pd.DataFrame:
    """Tag a frame with the data source that produced it (read by the API/UI)."""
    df.attrs["data_source"] = {"provider": provider, "via": via, "symbol": symbol, "label": label}
    return df


def data_source_of(df: pd.DataFrame) -> dict:
    """Read the data-source label off a frame (set by the loaders)."""
    src = getattr(df, "attrs", {}).get("data_source")
    return dict(src) if src else {"provider": "unknown", "via": "", "symbol": "", "label": "Unknown"}


def _cache_get(key: tuple) -> Optional[pd.DataFrame]:
    import time
    hit = _BARS_CACHE.get(key)
    if hit and (time.time() - hit[0]) < _BARS_TTL:
        df = hit[1]
        out = df.copy()
        out.attrs = dict(df.attrs)   # .copy() doesn't reliably carry attrs
        return out
    return None


def _cache_put(key: tuple, df: pd.DataFrame) -> None:
    import time
    stored = df.copy()
    stored.attrs = dict(df.attrs)
    _BARS_CACHE[key] = (time.time(), stored)
    if len(_BARS_CACHE) > 64:   # bound memory on the 512 MB box
        oldest = min(_BARS_CACHE.items(), key=lambda kv: kv[1][0])[0]
        _BARS_CACHE.pop(oldest, None)


def load_bridge(symbol: str, timeframe: str, n_bars: int = 5000) -> pd.DataFrame:
    """Fetch bars from the MT5 bridge running on the user's Windows PC.

    Configured via env on the VPS: BRIDGE_URL (tunnel hostname) + BRIDGE_TOKEN.
    Raises if the bridge isn't configured or is unreachable so the caller can
    fall back to yfinance.
    """
    import os
    import httpx
    url   = os.environ.get("BRIDGE_URL", "").strip()
    token = os.environ.get("BRIDGE_TOKEN", "").strip()
    if not url:
        raise RuntimeError("BRIDGE_URL not configured")

    r = httpx.get(
        f"{url.rstrip('/')}/bars",
        params={"symbol": symbol, "timeframe": timeframe, "n_bars": n_bars},
        headers={"X-Bridge-Token": token},
        timeout=httpx.Timeout(30.0),
    )
    r.raise_for_status()
    payload = r.json()
    recs = payload.get("bars") or []
    if not recs:
        raise RuntimeError("bridge returned no bars")

    df = pd.DataFrame(recs)
    df["time"] = pd.to_datetime(df["time"])
    keep = [c for c in ("time", "O", "H", "L", "C", "V") if c in df.columns]
    df = df[keep].reset_index(drop=True)
    return _set_source(df, "mt5", "bridge", symbol, f"MT5 · {symbol}")


def _load_mt5_terminal(symbol: str, timeframe: str, n_bars: int = 5000) -> pd.DataFrame:
    """Fetch bars directly from a connected MT5 terminal (Windows only)."""
    import MetaTrader5 as mt5

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

    # initialize() can return True on a stale connection; copy_rates_from_pos then
    # returns None. Retry once with a full shutdown → reinit to recover silently.
    rates = None
    for attempt in range(2):
        if not mt5.initialize():
            mt5.shutdown()
            if not mt5.initialize():
                raise RuntimeError(
                    f"Cannot connect to MT5 (attempt {attempt+1}): {mt5.last_error()}"
                )
        rates = mt5.copy_rates_from_pos(symbol, tf_map[timeframe], 0, n_bars)
        if rates is not None and len(rates) > 0:
            break
        mt5.shutdown()   # force a clean reconnect before the retry

    if rates is None or len(rates) == 0:
        raise RuntimeError(
            f"No bars returned for {symbol} {timeframe} after reconnect: {mt5.last_error()}"
        )

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.rename(columns={"open": "O", "high": "H", "low": "L", "close": "C",
                            "tick_volume": "V"})
    df = df[["time", "O", "H", "L", "C", "V"]]
    return _set_source(df, "mt5", "terminal", symbol, f"MT5 · {symbol}")


def load_mt5(symbol: str, timeframe: str, n_bars: int = 5000) -> pd.DataFrame:
    """Resolve real bars for a symbol/timeframe, with caching + fallbacks.

    Resolution order:
      • Windows (dev): local MT5 terminal.
      • Linux (VPS):   MT5 bridge (user's PC) → yfinance fallback (clearly labeled).
    The returned frame carries its origin in ``df.attrs['data_source']`` so the
    API and UI can show exactly which data was used (no more silent swaps).
    """
    import sys

    key = (symbol.upper(), timeframe.upper(), int(n_bars))
    cached = _cache_get(key)
    if cached is not None:
        return cached

    df: Optional[pd.DataFrame] = None

    if sys.platform == "win32":
        try:
            df = _load_mt5_terminal(symbol, timeframe, n_bars)
        except ImportError:
            df = None   # MT5 package missing even on Windows — fall through

    if df is None:
        # VPS path (or terminal unavailable): prefer the bridge, then yfinance.
        try:
            df = load_bridge(symbol, timeframe, n_bars)
        except Exception:
            df = _load_yfinance(symbol, timeframe, n_bars)

    _cache_put(key, df)
    return df


# ─── Symbol mapping: Edgekit → Yahoo Finance ticker ─────────────────────────
_YF_SYMBOL_MAP: dict[str, str] = {
    # Forex (via FX=X suffix)
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X", "USDCHF": "USDCHF=X",
    "NZDUSD": "NZDUSD=X", "EURGBP": "EURGBP=X", "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X",
    # Commodities
    "XAUUSD": "GC=F", "GOLD": "GC=F",
    "XAGUSD": "SI=F", "SILVER": "SI=F",
    "USOIL":  "CL=F", "WTI": "CL=F", "BRENT": "BZ=F",
    # Crypto
    "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD",
    "BNBUSD": "BNB-USD", "SOLUSD": "SOL-USD",
    # Indices
    "US500":  "^GSPC", "SPX": "^GSPC",
    "US100":  "^NDX",  "NDX": "^NDX",
    "US30":   "^DJI",  "DJI": "^DJI",
}

_YF_INTERVAL_MAP: dict[str, str] = {
    "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
    "H1": "1h", "H4": "4h", "D1":  "1d",
}

# How many calendar days to fetch per timeframe to get ~n_bars bars
_YF_PERIOD_DAYS: dict[str, float] = {
    "M1": 7, "M5": 60, "M15": 60, "M30": 120,
    "H1": 730, "H4": 730, "D1": 3650,
}


def _load_yfinance(symbol: str, timeframe: str, n_bars: int = 5000) -> pd.DataFrame:
    """Fetch OHLCV from Yahoo Finance. Used as MT5 fallback on Linux/VPS."""
    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError(
            "Neither MetaTrader5 nor yfinance is available. "
            "Install yfinance: pip install yfinance"
        ) from e

    interval = _YF_INTERVAL_MAP.get(timeframe)
    if interval is None:
        raise ValueError(f"Unsupported timeframe for yfinance: {timeframe}")

    ticker = _YF_SYMBOL_MAP.get(symbol.upper(), symbol)
    days   = _YF_PERIOD_DAYS.get(timeframe, 365)

    import datetime
    end   = datetime.datetime.utcnow()
    start = end - datetime.timedelta(days=days)

    raw = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval=interval,
        progress=False,
        auto_adjust=True,
    )

    if raw is None or raw.empty:
        raise RuntimeError(
            f"yfinance returned no data for {symbol} ({ticker}) {timeframe}. "
            "Check the symbol name or try a higher timeframe."
        )

    # yfinance returns a MultiIndex or flat columns depending on version
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    raw = raw.rename(columns={
        "Open": "O", "High": "H", "Low": "L", "Close": "C", "Volume": "V",
    })
    raw.index.name = "time"
    raw = raw.reset_index()
    raw["time"] = pd.to_datetime(raw["time"], utc=True).dt.tz_localize(None)

    keep = [c for c in ("time", "O", "H", "L", "C", "V") if c in raw.columns]
    df = raw[keep].dropna(subset=["O", "H", "L", "C"]).reset_index(drop=True)

    # Return last n_bars rows
    if len(df) > n_bars:
        df = df.iloc[-n_bars:].reset_index(drop=True)

    return _set_source(df, "yahoo", "fallback", symbol, f"Yahoo (fallback) · {ticker}")


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
