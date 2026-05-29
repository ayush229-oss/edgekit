"""
Edgekit MT5 Bridge — runs on the Windows machine that has the MetaTrader 5
terminal installed and logged in.

Why this exists
---------------
The live backend runs on a Linux VPS, where the `MetaTrader5` Python package
cannot run (it needs a Windows terminal). Without this bridge the VPS silently
falls back to Yahoo Finance — wrong instrument, sparse history. This service
exposes the SAME `load_mt5()` the app already uses, over HTTP, so the VPS can
fetch your real broker bars.

Topology
--------
    [VPS backend]  --HTTPS-->  [Cloudflare tunnel]  -->  [this bridge on your PC]  -->  [MT5 terminal]

The bridge listens on localhost; a Cloudflare tunnel (already configured on this
machine — see tunnel.log / named-tunnel.log) exposes it at a public hostname the
VPS calls. Every request must carry the shared secret in `X-Bridge-Token`.

Run it
------
    set BRIDGE_TOKEN=<a-long-random-secret>          (PowerShell: $env:BRIDGE_TOKEN="...")
    python -m uvicorn bridge.mt5_bridge:app --host 127.0.0.1 --port 8900

Then point a Cloudflare tunnel at http://127.0.0.1:8900 and set the same
BRIDGE_TOKEN + the tunnel URL on the VPS (BRIDGE_URL, BRIDGE_TOKEN env vars).

Security
--------
- Requests without a matching X-Bridge-Token are rejected (401).
- Bind to 127.0.0.1 only; never expose the raw port to the internet — the
  Cloudflare tunnel is the only public entry point.
"""
from __future__ import annotations

import os
import time

from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.engine.core.data_loader import load_mt5, infer_pip_from_df

app = FastAPI(title="Edgekit MT5 Bridge", version="1.1.0")

# Orders are tagged with this magic so we only ever touch our own positions.
EDGEKIT_MAGIC = 770011

# Shared secret — the VPS must send the same value in X-Bridge-Token.
_TOKEN = os.environ.get("BRIDGE_TOKEN", "").strip()

# Allowed timeframes mirror load_mt5's tf_map.
_TIMEFRAMES = {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}


def _check_token(token: str | None) -> None:
    """Reject any request that doesn't present the shared secret."""
    if not _TOKEN:
        # Fail closed: if the operator forgot to set a token, don't serve data.
        raise HTTPException(503, "Bridge token not configured on this machine.")
    if not token or token != _TOKEN:
        raise HTTPException(401, "Invalid or missing X-Bridge-Token.")


@app.get("/health")
def health(x_bridge_token: str | None = Header(default=None, alias="X-Bridge-Token")):
    """Liveness + MT5 reachability check. Token-gated so it can't be probed."""
    _check_token(x_bridge_token)
    mt5_ok = False
    detail = ""
    try:
        # A tiny fetch proves the terminal is connected and logged in.
        df = load_mt5("XAUUSD", "M15", 5)
        mt5_ok = df is not None and len(df) > 0
    except Exception as e:  # noqa: BLE001 — surface any MT5/terminal error
        detail = str(e)
    return {"ok": True, "mt5_connected": mt5_ok, "detail": detail}


@app.get("/bars")
def bars(
    symbol: str = Query(..., min_length=1, max_length=32),
    timeframe: str = Query("M15"),
    n_bars: int = Query(5000, ge=10, le=50000),
    x_bridge_token: str | None = Header(default=None, alias="X-Bridge-Token"),
):
    """Return normalized OHLCV bars straight from the local MT5 terminal.

    Response shape (consumed by the VPS `load_bridge`):
        {
          "source": "mt5",
          "symbol": "XAUUSD", "timeframe": "M15",
          "count": 5000, "pip": 0.10,
          "bars": [{"time": "...ISO...", "O":.., "H":.., "L":.., "C":.., "V":..}, ...]
        }
    """
    _check_token(x_bridge_token)
    tf = timeframe.upper()
    if tf not in _TIMEFRAMES:
        raise HTTPException(400, f"Unsupported timeframe '{timeframe}'. Use {sorted(_TIMEFRAMES)}.")

    t0 = time.time()
    try:
        df = load_mt5(symbol, tf, n_bars)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"MT5 fetch failed for {symbol} {tf}: {e}")
    if df is None or len(df) == 0:
        raise HTTPException(404, f"No bars returned for {symbol} {tf}.")

    has_v = "V" in df.columns
    records = [
        {
            "time": t.isoformat(),
            "O": float(o), "H": float(h), "L": float(l), "C": float(c),
            "V": float(v) if has_v else 0.0,
        }
        for t, o, h, l, c, v in zip(
            df["time"], df["O"], df["H"], df["L"], df["C"],
            (df["V"] if has_v else [0.0] * len(df)),
        )
    ]
    return JSONResponse({
        "source":    "mt5",
        "symbol":    symbol,
        "timeframe": tf,
        "count":     len(records),
        "pip":       infer_pip_from_df(df, symbol),
        "elapsed_ms": int((time.time() - t0) * 1000),
        "bars":      records,
    })


# ═══════════════════════════════════════════════════════════════════════════
# DEMO-ONLY EXECUTION LAYER
# Forward testing places real orders on a DEMO account to measure true spread,
# slippage and commission. A hard guard refuses to ever trade a REAL account.
# ═══════════════════════════════════════════════════════════════════════════

def _mt5():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise HTTPException(502, f"MT5 not reachable: {mt5.last_error()}")
    return mt5


def _assert_demo(mt5) -> dict:
    """Refuse to operate on anything that isn't a demo/contest account.
    ACCOUNT_TRADE_MODE: 0 = DEMO, 1 = CONTEST, 2 = REAL."""
    ai = mt5.account_info()
    if ai is None:
        raise HTTPException(502, "No MT5 account info available.")
    if int(ai.trade_mode) == 2:   # REAL
        raise HTTPException(
            403,
            "Refusing to trade: this MT5 terminal is logged into a REAL (live-money) "
            "account. Forward testing only runs on a DEMO account.",
        )
    return {"login": ai.login, "server": ai.server, "trade_mode": int(ai.trade_mode),
            "currency": ai.currency, "balance": float(ai.balance), "equity": float(ai.equity)}


class MarketOrder(BaseModel):
    symbol:  str
    side:    str            # "buy" | "sell"
    volume:  float = 0.01
    sl:      Optional[float] = None
    tp:      Optional[float] = None
    comment: str = "edgekit-fwd"


@app.get("/account")
def account(x_bridge_token: Optional[str] = Header(default=None, alias="X-Bridge-Token")):
    _check_token(x_bridge_token)
    mt5 = _mt5()
    info = _assert_demo(mt5)   # also blocks reading a real account by mistake
    return info


@app.get("/positions")
def positions(x_bridge_token: Optional[str] = Header(default=None, alias="X-Bridge-Token")):
    """Only our own forward-test positions (filtered by magic)."""
    _check_token(x_bridge_token)
    mt5 = _mt5()
    _assert_demo(mt5)
    pos = mt5.positions_get() or []
    out = []
    for p in pos:
        if getattr(p, "magic", 0) != EDGEKIT_MAGIC:
            continue
        out.append({
            "ticket": p.ticket, "symbol": p.symbol,
            "side": "buy" if p.type == 0 else "sell",
            "volume": float(p.volume), "price_open": float(p.price_open),
            "sl": float(p.sl), "tp": float(p.tp),
            "profit": float(p.profit), "comment": p.comment,
        })
    return {"positions": out}


@app.post("/order/market")
def order_market(req: MarketOrder,
                 x_bridge_token: Optional[str] = Header(default=None, alias="X-Bridge-Token")):
    """Place a market order on the DEMO account; return the ACTUAL fill so the
    caller can record real spread/slippage/commission."""
    _check_token(x_bridge_token)
    mt5 = _mt5()
    _assert_demo(mt5)

    side = req.side.lower().strip()
    if side not in ("buy", "sell"):
        raise HTTPException(400, "side must be 'buy' or 'sell'.")
    if not mt5.symbol_select(req.symbol, True):
        raise HTTPException(400, f"Symbol {req.symbol} not available on this terminal.")

    tick = mt5.symbol_info_tick(req.symbol)
    if tick is None:
        raise HTTPException(502, f"No tick for {req.symbol}.")
    spread = float(tick.ask - tick.bid)
    price  = float(tick.ask if side == "buy" else tick.bid)
    otype  = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL

    base = {
        "action":    mt5.TRADE_ACTION_DEAL,
        "symbol":    req.symbol,
        "volume":    float(req.volume),
        "type":      otype,
        "price":     price,
        "deviation": 20,
        "magic":     EDGEKIT_MAGIC,
        "comment":   req.comment[:31],
        "type_time": mt5.ORDER_TIME_GTC,
    }
    if req.sl: base["sl"] = float(req.sl)
    if req.tp: base["tp"] = float(req.tp)

    # Broker filling mode varies — try the common ones.
    last = None
    for fmode in (mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
        res = mt5.order_send({**base, "type_filling": fmode})
        last = res
        if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
            return {
                "ok": True, "ticket": res.order, "deal": res.deal,
                "requested_price": price, "fill_price": float(res.price),
                "slippage": float(res.price - price),
                "spread": spread, "volume": float(res.volume),
                "side": side, "symbol": req.symbol,
                "comment": res.comment,
            }
    rc = getattr(last, "retcode", None)
    raise HTTPException(502, f"Order rejected (retcode={rc}): {getattr(last, 'comment', '')}")


@app.post("/order/close")
def order_close(ticket: int = Query(...),
                x_bridge_token: Optional[str] = Header(default=None, alias="X-Bridge-Token")):
    """Close one of our positions by ticket; return realized PnL + fill."""
    _check_token(x_bridge_token)
    mt5 = _mt5()
    _assert_demo(mt5)

    pos = mt5.positions_get(ticket=ticket)
    if not pos:
        raise HTTPException(404, f"Position {ticket} not found.")
    p = pos[0]
    if getattr(p, "magic", 0) != EDGEKIT_MAGIC:
        raise HTTPException(403, "Refusing to close a position Edgekit didn't open.")

    close_side = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(p.symbol)
    price = float(tick.bid if p.type == 0 else tick.ask)
    base = {
        "action":   mt5.TRADE_ACTION_DEAL,
        "symbol":   p.symbol,
        "volume":   float(p.volume),
        "type":     close_side,
        "position": p.ticket,
        "price":    price,
        "deviation": 20,
        "magic":    EDGEKIT_MAGIC,
        "comment":  "edgekit-close",
        "type_time": mt5.ORDER_TIME_GTC,
    }
    last = None
    for fmode in (mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
        res = mt5.order_send({**base, "type_filling": fmode})
        last = res
        if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
            return {"ok": True, "ticket": p.ticket, "fill_price": float(res.price),
                    "profit": float(p.profit)}
    rc = getattr(last, "retcode", None)
    raise HTTPException(502, f"Close rejected (retcode={rc}): {getattr(last, 'comment', '')}")
