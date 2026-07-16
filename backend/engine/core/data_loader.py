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
    n_raw = len(df)
    df["time"] = _parse_time(df["time"])
    df = df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    for c in ("O", "H", "L", "C"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["O", "H", "L", "C"]).reset_index(drop=True)
    if df.empty:
        raise ValueError("After cleaning, no usable OHLCV rows remain.")
    # Record how many rows were discarded as invalid (bad time / non-numeric /
    # blank OHLC) so the caller can surface it instead of silently dropping them.
    df.attrs["rows_dropped"] = int(n_raw - len(df))
    return df


def validate_ohlcv(df: pd.DataFrame) -> dict:
    """
    Sanity-check an OHLCV frame. Returns a dict of issues found (empty = healthy).

    Checks performed
    ----------------
    too_few_bars          — fewer than 200 bars
    not_chronological     — rows out of time order after sort
    high_below_low        — H < L (inverted candle)
    oc_outside_hl         — O or C outside the H–L range
    duplicate_timestamps  — same timestamp appears twice
    large_time_gaps       — gaps > 50× the median gap (missing sessions)
    missing_bars_estimate — count of expected-but-absent bars based on median gap
    zero_volume_pct       — % of bars with V == 0 (suspicious if > 30%)
    outlier_wicks         — bars whose H-L range is > 10× the median range
    quality_score         — 0–100 composite score (100 = perfect)
    """
    issues: dict = {}
    n = len(df)

    if n < 200:
        issues["too_few_bars"] = f"Only {n} bars — backtest needs ~200+ for stable stats."

    # Chronological order
    if not df["time"].is_monotonic_increasing:
        n_unordered = int((df["time"].diff().dropna() < pd.Timedelta(0)).sum())
        issues["not_chronological"] = n_unordered

    # Inverted candles
    bad_hl  = int((df["H"] < df["L"]).sum())
    bad_oc  = int(((df["O"] > df["H"]) | (df["O"] < df["L"]) |
                   (df["C"] > df["H"]) | (df["C"] < df["L"])).sum())
    if bad_hl: issues["high_below_low"]  = bad_hl
    if bad_oc: issues["oc_outside_hl"]   = bad_oc

    # Missing / NaN values in any OHLC column. load_csv drops these before they
    # reach the engine, but frames built another way (other loaders, direct
    # construction) may still carry them — flag so callers aren't silently
    # backtesting over gaps.
    nan_rows = int(df[["O", "H", "L", "C"]].isna().any(axis=1).sum())
    if nan_rows:
        issues["nan_rows"] = nan_rows

    # Duplicate timestamps
    dupe = int(df["time"].duplicated().sum())
    if dupe: issues["duplicate_timestamps"] = dupe

    # Time gaps
    gaps = df["time"].diff().dropna()
    if len(gaps) > 5:
        median_gap = gaps.median()
        if median_gap > pd.Timedelta(0):
            big_gaps    = int((gaps > median_gap * 50).sum())
            # Estimate missing bars: total expected minus actual
            span        = df["time"].iloc[-1] - df["time"].iloc[0]
            expected    = max(1, int(span / median_gap))
            missing_est = max(0, expected - n)
            if big_gaps:    issues["large_time_gaps"]      = big_gaps
            if missing_est > n * 0.05:
                issues["missing_bars_estimate"] = missing_est

    # Zero volume
    if "V" in df.columns:
        zero_vol_pct = float((df["V"] == 0).sum()) / n * 100
        if zero_vol_pct > 30:
            issues["zero_volume_pct"] = round(zero_vol_pct, 1)

    # Outlier wicks (H-L range > 10× median)
    hl_range = (df["H"] - df["L"])
    median_range = hl_range.median()
    if median_range > 0:
        outlier_wicks = int((hl_range > median_range * 10).sum())
        if outlier_wicks:
            issues["outlier_wicks"] = outlier_wicks

    # Composite quality score (0–100)
    deductions = 0
    deductions += min(40, bad_hl * 5)
    deductions += min(20, bad_oc * 2)
    deductions += min(20, issues.get("nan_rows", 0))
    deductions += min(10, dupe * 2)
    deductions += min(10, issues.get("large_time_gaps", 0) * 2)
    deductions += min(10, issues.get("outlier_wicks", 0))
    deductions += 5 if "zero_volume_pct" in issues else 0
    deductions += 5 if n < 200 else 0
    issues["quality_score"] = max(0, 100 - deductions)

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


# ─── Dukascopy feed (no API key) — primary VPS data when the MT5 bridge is off ──
# Dukascopy Bank's free historical feed: strong forex + metals + indices + crypto
# coverage, every common timeframe, no signup. Used before yfinance on the VPS so
# intraday backtests work 24/7 regardless of whether the user's PC/bridge is up.
_DUKA_INTERVAL = {
    "M1": "INTERVAL_MIN_1",  "M5": "INTERVAL_MIN_5",  "M15": "INTERVAL_MIN_15",
    "M30": "INTERVAL_MIN_30", "H1": "INTERVAL_HOUR_1", "H4": "INTERVAL_HOUR_4",
    "D1": "INTERVAL_DAY_1",
}
_DUKA_TF_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}

# Symbol aliases: map common broker/MT5 names → canonical Dukascopy symbol
_DUKA_ALIAS = {
    "GOLD": "XAUUSD", "SILVER": "XAGUSD", "PLATINUM": "XPTUSD",
    "WTI":  "USOIL",  "BRENT":  "UKOIL",  "OIL":      "USOIL",
    "DJI":  "US30",   "DOW":    "US30",
    "SPX":  "US500",  "SP500":  "US500",
    "NDX":  "NAS100", "NASDAQ": "NAS100",
    "DAX":  "GER40",  "GER30":  "GER40",
    "FTSE": "UK100",
    "N225": "JPN225", "NIK":    "JPN225",
}

# Explicit Dukascopy instrument-constant names for symbols that aren't standard
# 6-char BASE+QUOTE pairs (indices, energies, platinum).
# Found by inspecting `dir(dukascopy_python.instruments)` on the VPS.
_DUKA_EXPLICIT: dict[str, str] = {
    # Indices
    "US30":   "INSTRUMENT_IDX_AMERICA_E_D_J_IND",
    "US500":  "INSTRUMENT_IDX_AMERICA_E_SANDP_500",
    "NAS100": "INSTRUMENT_IDX_AMERICA_E_NQ_100",
    "GER40":  "INSTRUMENT_IDX_EUROPE_E_DAAX",
    "UK100":  "INSTRUMENT_IDX_EUROPE_E_FUTSEE_100",
    "JPN225": "INSTRUMENT_IDX_ASIA_E_N225JAP",
    "AUS200": "INSTRUMENT_IDX_ASIA_E_XJO_ASX",
    "HK50":   "INSTRUMENT_IDX_ASIA_E_H_KONG",
    # Energies
    "USOIL":  "INSTRUMENT_CMD_ENERGY_E_LIGHT",
    "UKOIL":  "INSTRUMENT_CMD_ENERGY_E_BRENT",
    "NGAS":   "INSTRUMENT_CMD_ENERGY_GAS_CMD_USD",
    # Metals with non-standard Dukascopy naming
    "XPTUSD": "INSTRUMENT_CMD_METALS_XPT_CMD_USD",
    "XPDUSD": "INSTRUMENT_CMD_METALS_XPD_CMD_USD",
}

_DUKA_CAT_PRIORITY = ("METALS", "MAJORS", "CROSSES", "EXOTICS", "VCCY")
_duka_symbol_cache: dict = {}


def _duka_resolve_instrument(symbol: str):
    """Map an Edgekit symbol (e.g. XAUUSD, EURUSD, US30) to a Dukascopy
    instrument constant. Returns the constant value, or None if unmapped."""
    from dukascopy_python import instruments as I
    s = "".join(ch for ch in symbol.upper() if ch.isalnum())
    s = _DUKA_ALIAS.get(s, s)
    if s in _duka_symbol_cache:
        return _duka_symbol_cache[s]

    const = None

    # 1. Explicit map (indices, energies, non-standard metals)
    if s in _DUKA_EXPLICIT:
        const_name = _DUKA_EXPLICIT[s]
        const = getattr(I, const_name, None)

    # 2. Generic suffix search for standard 6-char BASE+QUOTE pairs (forex, metals, crypto)
    if const is None and len(s) == 6:
        suffix = f"_{s[:3]}_{s[3:]}"
        names = [n for n in dir(I) if n.startswith("INSTRUMENT_") and n.endswith(suffix)]
        if names:
            def _rank(n: str) -> int:
                for i, cat in enumerate(_DUKA_CAT_PRIORITY):
                    if f"_{cat}_" in n:
                        return i
                return len(_DUKA_CAT_PRIORITY)
            names.sort(key=_rank)
            const = getattr(I, names[0])

    _duka_symbol_cache[s] = const
    return const


def _load_dukascopy(symbol: str, timeframe: str, n_bars: int = 5000) -> pd.DataFrame:
    """Fetch OHLCV from Dukascopy's free historical feed (no API key)."""
    import logging
    logging.getLogger("DUKASCRIPT").setLevel(logging.WARNING)   # silence per-fetch info logs
    import dukascopy_python
    from datetime import datetime, timedelta, timezone

    iv_name = _DUKA_INTERVAL.get(timeframe.upper())
    if iv_name is None:
        raise ValueError(f"Unsupported timeframe for Dukascopy: {timeframe}")
    instrument = _duka_resolve_instrument(symbol)
    if instrument is None:
        raise RuntimeError(f"Dukascopy has no instrument for {symbol}")

    # Enough calendar span to yield n_bars (markets ~5/7 days) + buffer, capped.
    tf_min    = _DUKA_TF_MINUTES[timeframe.upper()]
    span_days = (tf_min * n_bars) / (60 * 24) * (7 / 5) * 1.3 + 3
    span_days = min(max(span_days, 3), 2000)
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=span_days)

    df = dukascopy_python.fetch(
        instrument, getattr(dukascopy_python, iv_name),
        dukascopy_python.OFFER_SIDE_BID, start, end,
    )
    if df is None or len(df) == 0:
        raise RuntimeError(f"Dukascopy returned no data for {symbol} {timeframe}")

    df = df.rename(columns={"open": "O", "high": "H", "low": "L", "close": "C", "volume": "V"})
    df.index.name = "time"
    df = df.reset_index()
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_localize(None)
    keep = [c for c in ("time", "O", "H", "L", "C", "V") if c in df.columns]
    df = df[keep].dropna(subset=["O", "H", "L", "C"]).reset_index(drop=True)
    if len(df) > n_bars:
        df = df.iloc[-n_bars:].reset_index(drop=True)
    return _set_source(df, "dukascopy", "feed", symbol, f"Dukascopy · {symbol}")


# ─── Sharekhan (Indian equities/indices) — official exchange data, no key cost ──
# Access token is short-lived (~10-11h) with no refresh flow; re-issued by
# manually running backend/scripts/sharekhan_refresh.py. If the saved session
# is missing/expired, _load_sharekhan raises immediately so callers fall back
# to yfinance — this must never hard-fail a request.
_SHAREKHAN_ROOT = "https://api.sharekhan.com"
_SHAREKHAN_INTERVAL = {
    "M1": "1minute", "M5": "5minute", "M15": "15minute", "H1": "60minute", "D1": "daily",
}
# Bare index names — exchange varies by index (NSE vs BSE), can't assume one
# default the way *.NS/*.BO suffixes let us for individual stocks.
_SHAREKHAN_INDEX_ALIAS: dict[str, tuple[str, str]] = {
    "NIFTY":     ("NC", "NIFTY"),
    "NIFTY50":   ("NC", "NIFTY"),
    "BANKNIFTY": ("NC", "NiftyBank"),
    "SENSEX":    ("BC", "SENSEX"),
}
_sharekhan_master_cache: dict[str, list[dict]] = {}


def _sharekhan_session() -> dict:
    import json, time
    path = Path(__file__).resolve().parent.parent.parent / ".sharekhan_session.json"
    if not path.exists():
        raise RuntimeError("No Sharekhan session — run backend/scripts/sharekhan_refresh.py")
    session = json.loads(path.read_text())
    if session["expires_at"] <= time.time() + 60:
        raise RuntimeError("Sharekhan session expired — run backend/scripts/sharekhan_refresh.py")
    return session


def _sharekhan_headers(session: dict) -> dict:
    import os
    return {
        "api-key":      os.environ.get("SHAREKHAN_API_KEY", ""),
        "access-token": session["access_token"],
        "Content-type": "application/json",
    }


def _sharekhan_master(exchange: str, headers: dict) -> list[dict]:
    import httpx
    if exchange in _sharekhan_master_cache:
        return _sharekhan_master_cache[exchange]
    r = httpx.get(f"{_SHAREKHAN_ROOT}/skapi/services/master/{exchange}",
                  headers=headers, timeout=30.0)
    r.raise_for_status()
    rows = r.json().get("data") or []
    _sharekhan_master_cache[exchange] = rows
    return rows


def _sharekhan_resolve(symbol: str, headers: dict) -> tuple[str, int]:
    """Map an Edgekit symbol to a (exchange, scripCode) pair via the cached
    scrip master. Raises if not found — caller falls back to yfinance."""
    s = symbol.upper().strip()
    if s in _SHAREKHAN_INDEX_ALIAS:
        exchange, target = _SHAREKHAN_INDEX_ALIAS[s]
        target = target.upper()
    elif s.endswith(".BO"):
        exchange, target = "BC", s[:-3]
    elif s.endswith(".NS"):
        exchange, target = "NC", s[:-3]
    else:
        exchange, target = "NC", s   # bare tickers default to NSE Cash

    for row in _sharekhan_master(exchange, headers):
        if (row.get("tradingSymbol") or "").upper() == target:
            return exchange, row["scripCode"]
    raise RuntimeError(f"Sharekhan master has no scrip for {symbol!r} on {exchange}")


def _load_sharekhan(symbol: str, timeframe: str, n_bars: int = 5000) -> pd.DataFrame:
    import httpx

    interval = _SHAREKHAN_INTERVAL.get(timeframe.upper())
    if interval is None:
        raise ValueError(f"Unsupported timeframe for Sharekhan: {timeframe}")

    session = _sharekhan_session()
    headers = _sharekhan_headers(session)
    exchange, scrip_code = _sharekhan_resolve(symbol, headers)

    r = httpx.get(
        f"{_SHAREKHAN_ROOT}/skapi/services/historical/{exchange}/{scrip_code}/{interval}",
        headers=headers, timeout=30.0,
    )
    r.raise_for_status()
    body = r.json()
    if body.get("status") != 200:
        raise RuntimeError(f"Sharekhan historical data error: {body}")

    rows = body.get("data") or []
    if not rows:
        raise RuntimeError(f"Sharekhan returned no bars for {symbol} {timeframe}")

    df = pd.DataFrame(rows)
    # tradeDate is D/M/YYYY (not zero-padded) — dayfirst parse, combined with time.
    df["time"] = pd.to_datetime(df["tradeDate"] + " " + df["tradeTime"], dayfirst=True)
    df = df.rename(columns={"open": "O", "high": "H", "low": "L", "close": "C", "qty": "V"})
    keep = [c for c in ("time", "O", "H", "L", "C", "V") if c in df.columns]
    df = df[keep].sort_values("time").reset_index(drop=True)
    if len(df) > n_bars:
        df = df.iloc[-n_bars:].reset_index(drop=True)
    return _set_source(df, "sharekhan", "api", symbol, f"Sharekhan · {symbol}")


def _is_indian_symbol(symbol: str) -> bool:
    s = symbol.upper().strip()
    return s in _SHAREKHAN_INDEX_ALIAS or s.endswith(".NS") or s.endswith(".BO")


def load_mt5(symbol: str, timeframe: str, n_bars: int = 5000) -> pd.DataFrame:
    """Resolve real bars for a symbol/timeframe, with caching + fallbacks.

    Resolution order:
      • Windows (dev): local MT5 terminal.
      • Linux (VPS):   MT5 bridge (user's PC) → Dukascopy (free, no key) → yfinance.
      • Indian symbols (NIFTY/BANKNIFTY/SENSEX, *.NS, *.BO): Sharekhan (official
        exchange data, daily/weekly go back to 2000; intraday capped to a small
        fixed recent window) is tried ahead of Dukascopy/yfinance whenever a
        valid session is saved — falls straight through if not.
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
        except Exception:
            # MT5 package missing, terminal not connected, or (most commonly for
            # non-forex symbols like NIFTY/RELIANCE.NS) the broker just doesn't
            # list this symbol — fall through to Dukascopy/yfinance either way.
            df = None

    if df is None and _is_indian_symbol(symbol):
        try:
            df = _load_sharekhan(symbol, timeframe, n_bars)
        except Exception:
            df = None   # no/expired session, unsupported timeframe, or unknown scrip

    if df is None:
        # VPS path (or terminal unavailable): prefer the user's MT5 bridge, then
        # Dukascopy's free feed (real forex/metals intraday, no key), then
        # yfinance as a last resort.
        try:
            df = load_bridge(symbol, timeframe, n_bars)
        except Exception:
            try:
                df = _load_dukascopy(symbol, timeframe, n_bars)
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
    # Indian indices
    "NIFTY": "^NSEI", "NIFTY50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
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
        if "XPT" in s or "XPD" in s:             return 0.10    # Platinum / Palladium
        if "JPY" in s:                            return 0.01
        if any(fx in s for fx in ("EUR", "GBP", "AUD", "NZD", "CHF", "CAD")):
            return 0.0001
        if "USD" in s and len(s) == 6:            return 0.0001    # USDXXX or XXXUSD forex
        if any(c in s for c in ("BTC", "ETH", "BNB", "SOL", "XRP")):
            return 1.0
        # Indices — integer pip
        if any(c in s for c in ("US30", "DJI", "DOW")):          return 1.0
        if any(c in s for c in ("NAS100", "NDX", "NASDAQ")):      return 1.0
        if any(c in s for c in ("US500", "SPX", "SP500")):        return 0.1
        if any(c in s for c in ("GER40", "GER30", "DAX")):        return 1.0
        if any(c in s for c in ("UK100", "FTSE")):                return 0.5
        if any(c in s for c in ("JPN225", "N225", "NIK")):        return 1.0
        if any(c in s for c in ("AUS200", "ASX")):                return 0.5
        if any(c in s for c in ("NIFTY", "BANKNIFTY", "SENSEX")): return 1.0
        # NSE/BSE individual stocks (Yahoo suffix) — exchange-wide tick size
        if s.endswith(".NS") or s.endswith(".BO"):                return 0.05
        # Energies
        if any(c in s for c in ("OIL", "BRENT", "WTI", "USOIL", "UKOIL")):
            return 0.01
        if "NGAS" in s or "GAS" in s:             return 0.001

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
