"""
Edgekit live forward-test executor — runs on the MT5 host (next to the bridge).

For each ACTIVE Grade-3 (live_demo) forward test:
  • on each newly-closed bar, evaluate the strategy
  • if a fresh signal fires and we're flat → open a DEMO market order (via the
    bridge, which captures the real fill / spread / slippage)
  • broker SL/TP closes the position; we detect the closure and log realized PnL
  • every event is pushed to the VPS immutable ledger

Safety:
  • All orders go through the bridge, which HARD-REFUSES non-demo accounts.
  • One open position per test (no pyramiding).
  • Read-only MT5 access here (bars + history); orders only via the guarded bridge.

Run:
  set BRIDGE_TOKEN=...   set VPS_URL=http://165.232.178.128:8765
  python -m bridge.executor
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import httpx

from backend.engine.core.data_loader import load_mt5, infer_pip_from_df
from backend.engine.builder_v2.engine import GraphV2Strategy

BRIDGE_URL  = os.environ.get("BRIDGE_URL_LOCAL", "http://127.0.0.1:8900")
VPS_URL     = os.environ.get("VPS_URL", "http://165.232.178.128:8765").rstrip("/")
TOKEN       = os.environ.get("BRIDGE_TOKEN", "").strip()
POLL_SEC    = int(os.environ.get("EXECUTOR_POLL_SEC", "30"))
EVAL_BARS   = 4000

_H = {"X-Bridge-Token": TOKEN}
_HX = {"X-Executor-Token": TOKEN}

# Per-test memory: last bar time we acted on + the ticket we currently hold.
_state: Dict[int, Dict[str, Any]] = {}


def _bridge_positions() -> list:
    r = httpx.get(f"{BRIDGE_URL}/positions", headers=_H, timeout=15)
    r.raise_for_status()
    return r.json().get("positions", [])


def _bridge_open(symbol: str, side: str, volume: float, sl: float, tp: float, tag: str) -> dict:
    r = httpx.post(f"{BRIDGE_URL}/order/market", headers=_H, timeout=30, json={
        "symbol": symbol, "side": side, "volume": volume,
        "sl": sl, "tp": tp, "comment": tag,
    })
    r.raise_for_status()
    return r.json()


def _vps_active() -> list:
    r = httpx.get(f"{VPS_URL}/forward/live/active", headers=_HX, timeout=30)
    r.raise_for_status()
    return r.json()


def _vps_event(ft_id: int, ev: dict) -> None:
    httpx.post(f"{VPS_URL}/forward/{ft_id}/event", headers=_HX, timeout=30, json=ev).raise_for_status()


def _realized_profit(ticket: int) -> float:
    """Sum the realized PnL (incl. commission/swap) of a closed position."""
    try:
        import MetaTrader5 as mt5
        deals = mt5.history_deals_get(position=ticket) or []
        return float(sum(d.profit + d.commission + d.swap for d in deals))
    except Exception:
        return 0.0


def _evaluate(test: Dict[str, Any]) -> None:
    ft_id = test["id"]
    st = _state.setdefault(ft_id, {"last_bar": None, "ticket": None})

    df  = load_mt5(test["symbol"], test["timeframe"], EVAL_BARS)
    if df is None or len(df) < 50:
        return
    pip = infer_pip_from_df(df, test["symbol"])
    last_bar = str(df["time"].iloc[-1])
    tag = f"ek:{ft_id}"

    # 1) Reconcile against the BROKER (source of truth), so an executor restart
    #    re-adopts an existing position instead of opening a duplicate.
    ours = [p for p in _bridge_positions()
            if p.get("comment", "") == tag or p.get("ticket") == st["ticket"]]
    broker_ticket = ours[0]["ticket"] if ours else None

    if st["ticket"] is not None and broker_ticket is None:
        # We had a position; it's gone → broker closed it (SL/TP). Log realized PnL.
        profit = _realized_profit(st["ticket"])
        _vps_event(ft_id, {"action": "close", "symbol": test["symbol"],
                           "ticket": st["ticket"], "profit": profit, "comment": tag})
        st["ticket"] = None
    elif broker_ticket is not None:
        # Adopt whatever the broker says is open for this test.
        st["ticket"] = broker_ticket

    # 2) Only act once per newly-closed bar.
    if st["last_bar"] == last_bar:
        return
    st["last_bar"] = last_bar

    # 3) Flat + a fresh signal on the latest bar → open a demo order.
    if st["ticket"] is not None:
        return
    try:
        setups = GraphV2Strategy(test["graph"]).detect(df, {"pip": pip})
    except Exception:
        return
    last_idx = len(df) - 1
    fresh = [s for s in setups if int(s.get("signal_idx", -1)) == last_idx]
    if not fresh:
        return
    s = fresh[-1]
    side   = "buy" if s["direction"] == "Bull" else "sell"
    entry  = float(s["entry"]); sl = float(s["sl"]); risk = float(s.get("risk") or abs(entry - sl))
    tgt_r  = float((test.get("mgmt") or {}).get("target_r", 3.0))
    tp     = entry + tgt_r * risk if side == "buy" else entry - tgt_r * risk
    vol    = float((test.get("mgmt") or {}).get("volume", 0.01))

    res = _bridge_open(test["symbol"], side, vol, sl, tp, tag)
    st["ticket"] = res.get("ticket")
    _vps_event(ft_id, {
        "action": "open", "symbol": test["symbol"], "side": side, "volume": vol,
        "requested_price": res.get("requested_price", 0.0), "fill_price": res.get("fill_price", 0.0),
        "slippage": res.get("slippage", 0.0), "spread": res.get("spread", 0.0),
        "sl": sl, "tp": tp, "ticket": res.get("ticket", 0), "comment": tag,
    })


def run_once() -> int:
    """One evaluation pass over all active live tests. Returns count evaluated."""
    tests = _vps_active()
    for t in tests:
        try:
            _evaluate(t)
        except Exception as e:
            print(f"[executor] test {t.get('id')} error: {type(e).__name__}: {e}")
    return len(tests)


def main() -> None:
    if not TOKEN:
        raise SystemExit("BRIDGE_TOKEN not set.")
    print(f"[executor] started · VPS={VPS_URL} · bridge={BRIDGE_URL} · poll={POLL_SEC}s")
    while True:
        try:
            n = run_once()
            print(f"[executor] evaluated {n} live test(s)")
        except Exception as e:
            print(f"[executor] loop error: {type(e).__name__}: {e}")
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
