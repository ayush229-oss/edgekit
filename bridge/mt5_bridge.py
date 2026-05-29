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

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from backend.engine.core.data_loader import load_mt5, infer_pip_from_df

app = FastAPI(title="Edgekit MT5 Bridge", version="1.0.0")

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
