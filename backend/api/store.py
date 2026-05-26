"""
In-memory data store for MVP. Real persistence (Postgres + S3) lands later.
Stores uploaded OHLCV frames keyed by short UUID for the duration of the process.
"""
from __future__ import annotations
from typing import Optional
import secrets
import pandas as pd

_STORE: dict[str, pd.DataFrame] = {}


def put(df: pd.DataFrame) -> str:
    """Save a DataFrame and return a short id."""
    sid = secrets.token_urlsafe(8)
    _STORE[sid] = df
    return sid


def get(data_id: str) -> Optional[pd.DataFrame]:
    return _STORE.get(data_id)


def evict_oldest(max_items: int = 50) -> None:
    while len(_STORE) > max_items:
        _STORE.pop(next(iter(_STORE)))


def stats() -> dict:
    return {"items": len(_STORE)}
