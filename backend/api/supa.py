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


def upsert(table: str, row: dict, *, on_conflict: str, return_row: bool = False) -> Optional[dict]:
    """INSERT … ON CONFLICT DO UPDATE via PostgREST merge-duplicates."""
    if not enabled():
        return None
    pref = f"resolution=merge-duplicates,return={'representation' if return_row else 'minimal'}"
    r = httpx.post(f"{_URL}/rest/v1/{table}",
                   headers=_headers({"Prefer": pref}),
                   params={"on_conflict": on_conflict},
                   json=_clean(row), timeout=_TIMEOUT)
    r.raise_for_status()
    if return_row:
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    return None


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


def upsert_forward_test(*, vps_id: int, user_id, name, symbol, timeframe,
                        graph, mgmt, baseline, started_at, status, latest) -> None:
    """Mirror a forward test into Supabase by vps_id. Swallows all errors."""
    try:
        upsert("forward_tests", {
            "vps_id":     vps_id,
            "user_id":    user_id,
            "name":       name or "",
            "symbol":     symbol or "XAUUSD",
            "timeframe":  timeframe or "M15",
            "graph":      graph or {},
            "mgmt":       mgmt or {},
            "baseline":   baseline or {},
            "started_at": started_at,
            "status":     status or "active",
            "latest":     latest or {},
        }, on_conflict="vps_id")
    except Exception:
        pass


def log_live_trade(*, vps_id: int, ft_vps_id: int, ts, action, symbol, side,
                   volume, requested_price, fill_price, slippage, spread,
                   sl, tp, ticket, profit, comment) -> None:
    """Mirror a live trade event into Supabase. Swallows all errors."""
    try:
        # Resolve the Supabase forward_tests.id from the VPS forward_test id.
        rows = select("forward_tests", {"vps_id": f"eq.{ft_vps_id}", "select": "id"})
        if not rows:
            return  # forward test not mirrored yet; skip
        supa_ft_id = rows[0]["id"]
        insert("live_trades", {
            "forward_test_id": supa_ft_id,
            "vps_id":          vps_id,
            "ft_vps_id":       ft_vps_id,
            "ts":              ts,
            "action":          action or "open",
            "symbol":          symbol or "",
            "side":            side or "",
            "volume":          volume or 0.0,
            "requested_price": requested_price or 0.0,
            "fill_price":      fill_price or 0.0,
            "slippage":        slippage or 0.0,
            "spread":          spread or 0.0,
            "sl":              sl or 0.0,
            "tp":              tp or 0.0,
            "ticket":          ticket or 0,
            "profit":          profit or 0.0,
            "comment":         comment or "",
        })
    except Exception:
        pass
