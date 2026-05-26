"""
Common technical indicators — used by strategy templates.
All functions take a pandas DataFrame with columns O/H/L/C and return a Series
(or DataFrame for multi-line indicators). Implementations are vectorized.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


# ─── Moving averages ─────────────────────────────────────────────────────────
def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


# ─── Oscillators ─────────────────────────────────────────────────────────────
def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    macd_line   = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    hist        = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": hist})


# ─── Volatility ──────────────────────────────────────────────────────────────
def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr1 = df["H"] - df["L"]
    tr2 = (df["H"] - df["C"].shift()).abs()
    tr3 = (df["L"] - df["C"].shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def bollinger(series: pd.Series, period: int = 20, stdev: float = 2.0) -> pd.DataFrame:
    mid = sma(series, period)
    sd  = series.rolling(window=period, min_periods=period).std()
    return pd.DataFrame({"upper": mid + stdev * sd, "mid": mid, "lower": mid - stdev * sd})


# ─── Volume-aware ────────────────────────────────────────────────────────────
def vwap(df: pd.DataFrame, session_reset: str = "D") -> pd.Series:
    """Session-anchored VWAP. session_reset: 'D' (daily) or 'W' (weekly)."""
    if "V" not in df.columns:
        raise ValueError("VWAP requires a 'V' (volume) column.")
    typical = (df["H"] + df["L"] + df["C"]) / 3.0
    pv  = typical * df["V"]
    grp = df["time"].dt.to_period(session_reset)
    return pv.groupby(grp).cumsum() / df["V"].groupby(grp).cumsum()


# ─── Trend ───────────────────────────────────────────────────────────────────
def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """Returns columns: supertrend (price), direction (1 = up, -1 = down)."""
    a = atr(df, period)
    hl2 = (df["H"] + df["L"]) / 2.0
    upper_band = hl2 + multiplier * a
    lower_band = hl2 - multiplier * a
    st   = pd.Series(index=df.index, dtype=float)
    dirn = pd.Series(index=df.index, dtype=int)

    for i in range(len(df)):
        if i == 0 or pd.isna(a.iloc[i]):
            st.iloc[i]   = np.nan
            dirn.iloc[i] = 1
            continue
        prev_st  = st.iloc[i - 1] if not pd.isna(st.iloc[i - 1]) else lower_band.iloc[i]
        prev_dir = dirn.iloc[i - 1]
        if prev_dir == 1:
            cur = max(lower_band.iloc[i], prev_st)
            if df["C"].iloc[i] < cur:
                dirn.iloc[i] = -1
                st.iloc[i]   = upper_band.iloc[i]
            else:
                dirn.iloc[i] = 1
                st.iloc[i]   = cur
        else:
            cur = min(upper_band.iloc[i], prev_st)
            if df["C"].iloc[i] > cur:
                dirn.iloc[i] = 1
                st.iloc[i]   = lower_band.iloc[i]
            else:
                dirn.iloc[i] = -1
                st.iloc[i]   = cur
    return pd.DataFrame({"supertrend": st, "direction": dirn})


# ─── Structural helpers (SMC) ────────────────────────────────────────────────
def swing_pivots(df: pd.DataFrame, length: int = 3) -> pd.DataFrame:
    """Detect swing highs/lows using the standard pivot definition.
    A swing high at index i is the highest of [i-length .. i+length].
    Returns booleans: swing_high, swing_low."""
    H, L = df["H"], df["L"]
    sh = (H == H.rolling(2 * length + 1, center=True).max())
    sl = (L == L.rolling(2 * length + 1, center=True).min())
    return pd.DataFrame({"swing_high": sh.fillna(False), "swing_low": sl.fillna(False)})
