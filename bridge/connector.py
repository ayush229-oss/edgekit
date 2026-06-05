"""
Edgekit MT5 Connector — runs on YOUR Windows PC next to MetaTrader 5.

What it does
------------
1. Polls the Edgekit VPS for your active live-demo forward tests.
2. For each test, grabs fresh bars from your local MT5 terminal, evaluates
   the strategy, and opens a DEMO market order when a signal fires.
3. Reports every fill (entry + exit) back to the VPS so the Forward Tests
   page shows real spread, slippage and commission.

Setup (one-time)
----------------
1. Clone the Edgekit repo and install dependencies:
       git clone https://github.com/<your-fork>/edgekit.git
       cd edgekit
       pip install MetaTrader5 httpx pandas numpy

2. Get your personal token from the Edgekit Resources page:
       https://edgekit.uk/resources  →  "Connect your MT5"  →  "Generate token"

3. Set environment variables:
       Windows CMD:         set EDGEKIT_TOKEN=ek-bridge-...
       Windows PowerShell:  $env:EDGEKIT_TOKEN = "ek-bridge-..."

4. Run:
       python -m bridge.connector

Safety
------
- The connector hard-refuses to trade REAL (live-money) accounts.  MT5 must be
  logged into a DEMO account or the script exits immediately.
- Only trades placed by Edgekit (tagged with magic 770011) are ever touched.
- One open position per forward test (no pyramiding).
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List, Optional

import httpx

# ── Config from env ──────────────────────────────────────────────────────────
VPS_URL    = os.environ.get("EDGEKIT_VPS",   "http://165.232.178.128:8765").rstrip("/")
TOKEN      = os.environ.get("EDGEKIT_TOKEN", "").strip()
POLL_SEC   = int(os.environ.get("EDGEKIT_POLL_SEC", "30"))
EVAL_BARS  = 4000
MAGIC      = 770011

_H: Dict[str, str] = {}   # filled after token check


# ── MT5 + engine imports (available since we're running from the repo root) ──
def _import_engine():
    try:
        from backend.engine.core.data_loader   import load_mt5, infer_pip_from_df
        from backend.engine.builder_v2.engine  import GraphV2Strategy
        return load_mt5, infer_pip_from_df, GraphV2Strategy
    except ImportError as e:
        sys.exit(
            f"[connector] Cannot import Edgekit engine: {e}\n"
            "Run this script from the repo root: python -m bridge.connector"
        )


def _import_mt5():
    try:
        import MetaTrader5 as mt5
        return mt5
    except ImportError:
        sys.exit("[connector] MetaTrader5 package not installed. Run: pip install MetaTrader5")


# ── Connector state: per-test last-acted bar + current ticket ────────────────
_state: Dict[int, Dict[str, Any]] = {}


# ── VPS helpers ──────────────────────────────────────────────────────────────
def _vps_active() -> List[Dict[str, Any]]:
    r = httpx.get(f"{VPS_URL}/forward/live/active", headers=_H, timeout=30)
    r.raise_for_status()
    return r.json()


def _vps_event(ft_id: int, ev: Dict[str, Any]) -> None:
    httpx.post(f"{VPS_URL}/forward/{ft_id}/event", headers=_H, timeout=30, json=ev).raise_for_status()


# ── MT5 helpers ──────────────────────────────────────────────────────────────
def _assert_demo(mt5) -> None:
    """Hard-exit if the terminal is logged into a real account."""
    ai = mt5.account_info()
    if ai is None:
        sys.exit("[connector] Could not read MT5 account info. Is the terminal running and logged in?")
    if int(ai.trade_mode) == 2:
        sys.exit(
            "[connector] REAL account detected — refusing to trade.\n"
            "Switch MT5 to a DEMO account first."
        )
    print(f"[connector] MT5 account: #{ai.login} @ {ai.server}  balance={ai.balance:.2f} {ai.currency}  (demo)")


def _positions(mt5) -> List[Dict[str, Any]]:
    pos = mt5.positions_get() or []
    return [
        {
            "ticket": p.ticket, "symbol": p.symbol,
            "side": "buy" if p.type == 0 else "sell",
            "price_open": float(p.price_open),
            "sl": float(p.sl), "tp": float(p.tp),
            "profit": float(p.profit), "comment": p.comment,
        }
        for p in pos if getattr(p, "magic", 0) == MAGIC
    ]


def _open_order(mt5, symbol: str, side: str, volume: float,
                sl: float, tp: float, tag: str) -> Dict[str, Any]:
    """Place a demo market order and return fill details."""
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Symbol {symbol} not available on this terminal.")
    tick  = mt5.symbol_info_tick(symbol)
    price = float(tick.ask if side == "buy" else tick.bid)
    spread = float(tick.ask - tick.bid)
    otype  = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
    base: Dict[str, Any] = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol,
        "volume": float(volume), "type": otype, "price": price,
        "deviation": 20, "magic": MAGIC, "comment": tag[:31],
        "type_time": mt5.ORDER_TIME_GTC,
    }
    if sl: base["sl"] = float(sl)
    if tp: base["tp"] = float(tp)
    last = None
    for fmode in (mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
        res = mt5.order_send({**base, "type_filling": fmode})
        last = res
        if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
            return {
                "ticket": res.order, "fill_price": float(res.price),
                "slippage": float(res.price - price), "spread": spread,
                "requested_price": price, "volume": float(res.volume),
            }
    rc = getattr(last, "retcode", None)
    raise RuntimeError(f"Order rejected (retcode={rc}): {getattr(last, 'comment', '')}")


def _realized_profit(mt5, ticket: int) -> float:
    try:
        deals = mt5.history_deals_get(position=ticket) or []
        return float(sum(d.profit + d.commission + d.swap for d in deals))
    except Exception:
        return 0.0


# ── Per-test evaluation ──────────────────────────────────────────────────────
def _evaluate(test: Dict[str, Any],
              mt5, load_mt5, infer_pip, GraphV2Strategy,
              all_positions: List[Dict[str, Any]]) -> None:
    ft_id = test["id"]
    st    = _state.setdefault(ft_id, {"last_bar": None, "ticket": None})
    tag   = f"ek:{ft_id}"

    # 1) Fetch fresh bars from local MT5
    df  = load_mt5(test["symbol"], test["timeframe"], EVAL_BARS)
    if df is None or len(df) < 50:
        return
    pip      = infer_pip(df, test["symbol"])
    last_bar = str(df["time"].iloc[-1])

    # 2) Reconcile position against broker (survive executor restart)
    ours = [p for p in all_positions if p.get("comment") == tag or p.get("ticket") == st["ticket"]]
    broker_ticket = ours[0]["ticket"] if ours else None

    if st["ticket"] is not None and broker_ticket is None:
        # Position was closed by broker (SL/TP) → log realized PnL
        profit = _realized_profit(mt5, st["ticket"])
        _vps_event(ft_id, {"action": "close", "symbol": test["symbol"],
                            "ticket": st["ticket"], "profit": profit, "comment": tag})
        print(f"[connector] ft={ft_id} closed ticket={st['ticket']}  profit={profit:.2f}")
        st["ticket"] = None
    elif broker_ticket is not None:
        st["ticket"] = broker_ticket   # re-adopt after restart

    # 3) Only act once per newly-closed bar
    if st["last_bar"] == last_bar:
        return
    st["last_bar"] = last_bar

    # 4) Flat + fresh signal on the latest bar → open order
    if st["ticket"] is not None:
        return
    try:
        setups = GraphV2Strategy(test["graph"]).detect(df, {"pip": pip})
    except Exception as e:
        print(f"[connector] ft={ft_id} strategy detect error: {e}")
        return

    last_idx = len(df) - 1
    fresh = [s for s in setups if int(s.get("signal_idx", -1)) == last_idx]
    if not fresh:
        return

    s      = fresh[-1]
    side   = "buy" if s["direction"] == "Bull" else "sell"
    entry  = float(s["entry"]); sl = float(s["sl"])
    risk   = abs(entry - sl) or pip
    tgt_r  = float((test.get("mgmt") or {}).get("target_r", 3.0))
    tp     = entry + tgt_r * risk if side == "buy" else entry - tgt_r * risk
    vol    = float((test.get("mgmt") or {}).get("volume", 0.01))

    try:
        fill = _open_order(mt5, test["symbol"], side, vol, sl, tp, tag)
    except Exception as e:
        print(f"[connector] ft={ft_id} order error: {e}")
        return

    st["ticket"] = fill["ticket"]
    _vps_event(ft_id, {
        "action": "open", "symbol": test["symbol"], "side": side, "volume": vol,
        "requested_price": fill["requested_price"], "fill_price": fill["fill_price"],
        "slippage": fill["slippage"], "spread": fill["spread"],
        "sl": sl, "tp": tp, "ticket": fill["ticket"], "comment": tag,
    })
    print(f"[connector] ft={ft_id} opened {side.upper()} {vol} {test['symbol']} "
          f"@ {fill['fill_price']}  sl={sl}  tp={tp:.5f}  ticket={fill['ticket']}")


# ── Main loop ────────────────────────────────────────────────────────────────
def main() -> None:
    if not TOKEN:
        sys.exit(
            "[connector] EDGEKIT_TOKEN not set.\n"
            "Get your token at https://edgekit.uk/resources → 'Connect your MT5' → 'Generate token'\n"
            "Then: set EDGEKIT_TOKEN=ek-bridge-..."
        )

    _H["X-Bridge-Token"] = TOKEN

    load_mt5_fn, infer_pip, GraphV2Strategy = _import_engine()
    mt5 = _import_mt5()

    if not mt5.initialize():
        sys.exit(f"[connector] MT5 initialize() failed: {mt5.last_error()}")

    _assert_demo(mt5)
    print(f"[connector] started · VPS={VPS_URL} · poll={POLL_SEC}s")

    while True:
        try:
            tests     = _vps_active()
            positions = _positions(mt5)
            if tests:
                print(f"[connector] {len(tests)} active live-demo test(s)")
            for t in tests:
                try:
                    _evaluate(t, mt5, load_mt5_fn, infer_pip, GraphV2Strategy, positions)
                except Exception as e:
                    print(f"[connector] test {t.get('id')} error: {type(e).__name__}: {e}")
        except Exception as e:
            print(f"[connector] loop error: {type(e).__name__}: {e}")
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
