"""
Thin Supabase PostgREST client (service-role) for the tables migrated off the
VPS SQLite: backtest_runs, forward_tests, live_trades.

The service-role key bypasses RLS, so this is backend-only. Every public helper
is BEST-EFFORT: it never raises, so a Supabase outage can never break a user
request. If SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set, all calls are
no-ops (enabled() is False) — that lets us ship the code before wiring the env.
"""
from __future__ import annotations
import os
import json
from typing import Any, Optional

import httpx

_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
_TIMEOUT = 8.0


def enabled() -> bool:
    return bool(_URL and _KEY)


def _headers(extra: Optional[dict] = None) -> dict:
    h = {
        "apikey":        _KEY,
        "Authorization": f"Bearer {_KEY}",
        "Content-Type":  "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _clean(obj: Any) -> Any:
    """Coerce to JSON-safe types (numpy floats, datetimes, etc. → via default=str)."""
    return json.loads(json.dumps(obj, default=str))


# ── Raw CRUD (raise on HTTP error; wrap at call sites) ───────────────────────
def insert(table: str, row: dict, *, return_row: bool = False) -> Optional[dict]:
    if not enabled():
        return None
    pref = "return=representation" if return_row else "return=minimal"
    r = httpx.post(f"{_URL}/rest/v1/{table}", headers=_headers({"Prefer": pref}),
                   json=_clean(row), timeout=_TIMEOUT)
    r.raise_for_status()
    if return_row:
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    return None


def update(table: str, match: dict, changes: dict) -> None:
    if not enabled():
        return
    params = {k: f"eq.{v}" for k, v in match.items()}
    r = httpx.patch(f"{_URL}/rest/v1/{table}", headers=_headers({"Prefer": "return=minimal"}),
                    params=params, json=_clean(changes), timeout=_TIMEOUT)
    r.raise_for_status()


def select(table: str, params: Optional[dict] = None) -> list[dict]:
    if not enabled():
        return []
    r = httpx.get(f"{_URL}/rest/v1/{table}", headers=_headers(),
                  params=params or {}, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def count(table: str, params: Optional[dict] = None) -> int:
    """Exact row count via PostgREST's Content-Range header."""
    if not enabled():
        return 0
    p = dict(params or {})
    p["select"] = "id"
    r = httpx.get(f"{_URL}/rest/v1/{table}",
                  headers=_headers({"Prefer": "count=exact", "Range": "0-0"}),
                  params=p, timeout=_TIMEOUT)
    r.raise_for_status()
    cr = r.headers.get("content-range", "")
    tail = cr.split("/")[-1] if "/" in cr else ""
    return int(tail) if tail.isdigit() else 0


# ── Best-effort helpers used by the routes (never raise) ─────────────────────
def log_backtest_run(*, user_id, strategy_id, params_snapshot, metrics,
                     symbol, timeframe, bars) -> None:
    """Mirror a backtest run into Supabase. Swallows all errors."""
    try:
        insert("backtest_runs", {
            "user_id":         user_id,
            "strategy_id":     strategy_id,
            "params_snapshot": params_snapshot,
            "metrics":         metrics,
            "symbol":          symbol or "",
            "timeframe":       timeframe or "",
            "bars":            bars or 0,
        })
    except Exception:
        pass
