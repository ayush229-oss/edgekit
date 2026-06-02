"""
Deterministic backtest result cache.

Key  = SHA-256(canonical JSON of request body, excluding user identity).
Store = in-memory dict with TTL.  Survives the request but not a restart —
        that's fine: backtest results are cheap to recompute, and cache-miss
        on restart is safe.

TTL is intentionally short (30 min) so that:
  - MT5 data that refreshes hourly still lands within one TTL window.
  - Template parameter edits always trigger a fresh run.

Usage:
    from backend.api.cache import backtest_cache
    result = backtest_cache.get(req)
    if result:
        return result
    result = run_expensive_backtest(req)
    backtest_cache.set(req, result)
    return result
"""
from __future__ import annotations
import hashlib
import json
import time
from typing import Any, Optional

_DEFAULT_TTL = 60 * 30   # 30 minutes


class BacktestCache:
    def __init__(self, ttl: int = _DEFAULT_TTL, maxsize: int = 256):
        self._store: dict[str, tuple[float, Any]] = {}
        self._ttl   = ttl
        self._max   = maxsize

    def _key(self, obj: Any) -> str:
        """SHA-256 of the canonical JSON of `obj`."""
        raw = json.dumps(obj, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _evict(self) -> None:
        now = time.monotonic()
        # Remove expired
        expired = [k for k, (ts, _) in self._store.items() if now - ts > self._ttl]
        for k in expired:
            del self._store[k]
        # If still over max, remove oldest
        while len(self._store) > self._max:
            oldest = min(self._store, key=lambda k: self._store[k][0])
            del self._store[oldest]

    def get(self, req_body: Any) -> Optional[Any]:
        key = self._key(req_body)
        hit = self._store.get(key)
        if hit and (time.monotonic() - hit[0]) < self._ttl:
            return hit[1]
        return None

    def set(self, req_body: Any, result: Any) -> None:
        self._evict()
        key = self._key(req_body)
        self._store[key] = (time.monotonic(), result)

    def stats(self) -> dict:
        now = time.monotonic()
        live = sum(1 for ts, _ in self._store.values() if now - ts < self._ttl)
        return {"total": len(self._store), "live": live, "ttl_seconds": self._ttl}


# Singleton — imported by routes
backtest_cache = BacktestCache()
