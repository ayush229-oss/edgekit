"""
Edgekit MT5 Connector (simplified) — runs on YOUR Windows PC next to MetaTrader 5.

The VPS evaluates strategies server-side and sends signals here.
This script only needs to: receive signal → place order → report fill.
No Python strategy engine required.

Setup (2 steps)
---------------
1. pip install MetaTrader5 httpx
2. set EDGEKIT_TOKEN=<token-from-Resources-page>
   python connector.py

Or just use the MT5 EA (bridge/EdgekitConnector.mq5) — no Python needed at all.
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List

import httpx

VPS_URL   = os.environ.get("EDGEKIT_VPS",   "http://165.232.178.128:8765").rstrip("/")
TOKEN     = os.environ.get("EDGEKIT_TOKEN", "").strip()
POLL_SEC  = int(os.environ.get("EDGEKIT_POLL_SEC", "30"))
MAGIC     = 770011

_H: Dict[str, str] = {}  # filled after token check

# Per-test: {ft_id: {"last_bar": str, "ticket": int|None}}
_state: Dict[int, Dict[str, Any]] = {}


def _import_mt5():
    try:
        import MetaTrader5 as mt5
        return mt5
    except ImportError:
        sys.exit("[connector] pip install MetaTrader5 httpx  — then re-run")


def _assert_demo(mt5) -> None:
    ai = mt5.account_info()
    if ai is None:
        sys.exit("[connector] Cannot read MT5 account. Is MT5 running and logged in?")
    if int(ai.trade_mode) == 2:
        sys.exit("[connector] REAL account detected — refusing to run. Switch MT5 to a DEMO account.")
    print(f"[connector] MT5 demo #{ai.login} @ {ai.server}  balance={ai.balance:.2f} {ai.currency}")


# ── VPS calls ────────────────────────────────────────────────────────────────
def _get_signals() -> List[Dict[str, Any]]:
    r = httpx.get(f"{VPS_URL}/forward/live/signals", headers=_H, timeout=30)
    r.raise_for_status()
    return r.json()


def _post_event(ft_id: int, ev: Dict[str, Any]) -> None:
    httpx.post(f"{VPS_URL}/forward/{ft_id}/event", headers=_H, timeout=30, json=ev).raise_for_status()


# ── MT5 helpers ──────────────────────────────────────────────────────────────
def _open_order(mt5, symbol: str, side: str, volume: float,
                sl: float, tp: float, tag: str) -> Dict[str, Any]:
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Symbol {symbol} not in terminal")
    tick   = mt5.symbol_info_tick(symbol)
    price  = float(tick.ask if side == "buy" else tick.bid)
    spread = float(tick.ask - tick.bid)
    otype  = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
    base: Dict[str, Any] = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol,
        "volume": volume, "type": otype, "price": price,
        "deviation": 20, "magic": MAGIC, "comment": tag[:31],
        "type_time": mt5.ORDER_TIME_GTC,
    }
    if sl: base["sl"] = sl
    if tp: base["tp"] = tp
    for fmode in (mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
        res = mt5.order_send({**base, "type_filling": fmode})
        if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
            return {"ticket": res.order, "fill_price": float(res.price),
                    "slippage": float(res.price - price), "spread": spread, "volume": volume}
    last = res
    raise RuntimeError(f"Order rejected (retcode={getattr(last,'retcode',None)})")


def _realized_profit(mt5, ticket: int) -> float:
    try:
        deals = mt5.history_deals_get(position=ticket) or []
        return float(sum(d.profit + d.commission + d.swap for d in deals))
    except Exception:
        return 0.0


def _positions(mt5) -> Dict[int, int]:
    """Return {ticket: ticket} for all open Edgekit positions."""
    pos = mt5.positions_get() or []
    return {p.ticket: p.ticket for p in pos if getattr(p, "magic", 0) == MAGIC}


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    if not TOKEN:
        sys.exit(
            "[connector] EDGEKIT_TOKEN not set.\n"
            "Get your token at https://edgekit.uk/resources → Connect your MT5\n"
            "Then: set EDGEKIT_TOKEN=ek-bridge-..."
        )
    _H["X-Bridge-Token"] = TOKEN
    mt5 = _import_mt5()
    if not mt5.initialize():
        sys.exit(f"[connector] MT5 init failed: {mt5.last_error()}")
    _assert_demo(mt5)
    print(f"[connector] started · VPS={VPS_URL} · poll={POLL_SEC}s")

    while True:
        try:
            signals   = _get_signals()
            open_pos  = _positions(mt5)

            # Check for closed positions
            for ft_id, st in list(_state.items()):
                if st["ticket"] is not None and st["ticket"] not in open_pos:
                    profit = _realized_profit(mt5, st["ticket"])
                    _post_event(ft_id, {"action": "close", "ticket": st["ticket"],
                                        "profit": profit, "comment": f"ek:{ft_id}"})
                    print(f"[connector] ft={ft_id} closed ticket={st['ticket']} profit={profit:.2f}")
                    st["ticket"] = None

            # Process signals
            for sig in signals:
                ft_id    = int(sig["ft_id"])
                bar_time = sig.get("bar_time", "")
                st = _state.setdefault(ft_id, {"last_bar": None, "ticket": None})

                if st["last_bar"] == bar_time:
                    continue   # already acted on this bar
                if st["ticket"] is not None:
                    continue   # position still open

                try:
                    fill = _open_order(
                        mt5, sig["symbol"], sig["side"],
                        float(sig.get("volume", 0.01)),
                        float(sig.get("sl", 0)), float(sig.get("tp", 0)),
                        f"ek:{ft_id}",
                    )
                except Exception as e:
                    print(f"[connector] ft={ft_id} order error: {e}")
                    continue

                st["ticket"]   = fill["ticket"]
                st["last_bar"] = bar_time
                _post_event(ft_id, {
                    "action": "open", "symbol": sig["symbol"], "side": sig["side"],
                    "volume": fill["volume"], "fill_price": fill["fill_price"],
                    "slippage": fill["slippage"], "spread": fill["spread"],
                    "sl": float(sig.get("sl", 0)), "tp": float(sig.get("tp", 0)),
                    "ticket": fill["ticket"], "comment": f"ek:{ft_id}",
                })
                print(f"[connector] ft={ft_id} {sig['side'].upper()} {fill['volume']} "
                      f"{sig['symbol']} @ {fill['fill_price']}  ticket={fill['ticket']}")

        except Exception as e:
            print(f"[connector] error: {type(e).__name__}: {e}")

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
