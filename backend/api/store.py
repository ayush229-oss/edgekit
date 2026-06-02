"""
Persistent data store for uploaded OHLCV CSVs.

Strategy:
  1. Write to disk on put() so data survives service restarts/crashes.
  2. Keep an in-memory cache for fast repeated lookups.
  3. Evict oldest disk files when the folder grows beyond MAX_DISK_FILES.

Storage path: EDGEKIT_DATA_DIR env var (default /tmp/edgekit_data on Linux,
%TEMP%/edgekit_data on Windows).
"""
from __future__ import annotations
import os
import json
import secrets
import tempfile
from pathlib import Path
from typing import Optional

import pandas as pd

# ── Storage directory ────────────────────────────────────────────────────────
_DEFAULT_DIR = Path(tempfile.gettempdir()) / "edgekit_data"
DATA_DIR = Path(os.environ.get("EDGEKIT_DATA_DIR", str(_DEFAULT_DIR)))
DATA_DIR.mkdir(parents=True, exist_ok=True)

MAX_DISK_FILES = 100   # max CSVs kept on disk

# ── In-memory cache (hot path) ───────────────────────────────────────────────
_MEM: dict[str, pd.DataFrame] = {}


def put(df: pd.DataFrame) -> str:
    """Save a DataFrame to disk (and memory cache). Returns a stable data_id."""
    sid = secrets.token_urlsafe(8)
    _persist(sid, df)
    _MEM[sid] = df
    evict_oldest()
    return sid


def get(data_id: str) -> Optional[pd.DataFrame]:
    """Return the DataFrame for data_id. Checks memory first, then disk."""
    if data_id in _MEM:
        return _MEM[data_id]
    # Try loading from disk (service was restarted)
    df = _load(data_id)
    if df is not None:
        _MEM[data_id] = df   # warm the cache
    return df


def evict_oldest(max_items: int = MAX_DISK_FILES) -> None:
    """Remove oldest files from disk when over the limit."""
    files = sorted(DATA_DIR.glob("*.parquet"), key=lambda f: f.stat().st_mtime)
    while len(files) > max_items:
        files.pop(0).unlink(missing_ok=True)


def stats() -> dict:
    return {
        "mem_items":  len(_MEM),
        "disk_items": len(list(DATA_DIR.glob("*.parquet"))),
        "data_dir":   str(DATA_DIR),
    }


# ── Internal helpers ─────────────────────────────────────────────────────────

def _path(sid: str) -> Path:
    return DATA_DIR / f"{sid}.parquet"


def _persist(sid: str, df: pd.DataFrame) -> None:
    """Write DataFrame to Parquet (fast, compact, type-preserving)."""
    try:
        df.to_parquet(_path(sid), index=False)
    except Exception:
        # Parquet needs pyarrow/fastparquet — fall back to CSV
        try:
            df.to_csv(_path(sid).with_suffix(".csv"), index=False)
        except Exception:
            pass   # disk write failed — memory-only for this session


def _load(sid: str) -> Optional[pd.DataFrame]:
    """Load from disk. Returns None if not found."""
    p = _path(sid)
    if p.exists():
        try:
            return pd.read_parquet(p)
        except Exception:
            pass
    p_csv = p.with_suffix(".csv")
    if p_csv.exists():
        try:
            return pd.read_csv(p_csv, parse_dates=["time"])
        except Exception:
            pass
    return None
