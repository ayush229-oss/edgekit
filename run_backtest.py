import requests, json

graph = {
  "name": "SMC Gold 1m — Sweep+OB 1:4 RR",
  "nodes": [
    {"id": "u1",  "type": "universe.single_asset",  "params": {"ticker": "XAUUSD", "timeframe": "M1"}},
    {"id": "atr", "type": "indicator.atr",           "params": {"period": 14}},
    {"id": "obL", "type": "indicator.order_block",   "params": {"direction": "long",  "scan_min": 2, "scan_max": 6, "entry_ratio": 0.5}},
    {"id": "alL", "type": "alpha.liquidity_sweep",   "params": {"lookback": 15, "count": 2, "tolerance_pips": 2, "min_pierce_pips": 0.5, "direction": "long"}},
    {"id": "fsL", "type": "filter.session",          "params": {"start_hour": 7, "end_hour": 17}},
    {"id": "faL", "type": "filter.threshold",        "params": {"min": 0.25, "max": 100}},
    {"id": "szL", "type": "sizing.fixed_pct",        "params": {"risk_pct": 1.0}},
    {"id": "rkL", "type": "risk.structure_stop",     "params": {"buf_pips": 2}},
    {"id": "e1L", "type": "exit.target_and_trail",   "params": {"target_r": 4.0, "close_pct": 0.75, "trail_mode": "candle", "trail_buf": 2.0}},
    {"id": "e2L", "type": "exit.breakeven_at_r",     "params": {"be_at_r": 1.5}},
    {"id": "e3L", "type": "exit.time_exit",          "params": {"bars": 60}},
    {"id": "xcL", "type": "execution.limit_at",      "params": {"expiry_bars": 5}},
    {"id": "obS", "type": "indicator.order_block",   "params": {"direction": "short", "scan_min": 2, "scan_max": 6, "entry_ratio": 0.5}},
    {"id": "alS", "type": "alpha.liquidity_sweep",   "params": {"lookback": 15, "count": 2, "tolerance_pips": 2, "min_pierce_pips": 0.5, "direction": "short"}},
    {"id": "fsS", "type": "filter.session",          "params": {"start_hour": 7, "end_hour": 17}},
    {"id": "faS", "type": "filter.threshold",        "params": {"min": 0.25, "max": 100}},
    {"id": "szS", "type": "sizing.fixed_pct",        "params": {"risk_pct": 1.0}},
    {"id": "rkS", "type": "risk.structure_stop",     "params": {"buf_pips": 2}},
    {"id": "e1S", "type": "exit.target_and_trail",   "params": {"target_r": 4.0, "close_pct": 0.75, "trail_mode": "candle", "trail_buf": 2.0}},
    {"id": "e2S", "type": "exit.breakeven_at_r",     "params": {"be_at_r": 1.5}},
    {"id": "e3S", "type": "exit.time_exit",          "params": {"bars": 60}},
    {"id": "xcS", "type": "execution.limit_at",      "params": {"expiry_bars": 5}},
  ],
  "edges": [
    {"from": "alL", "from_port": "insight",  "to": "fsL", "to_port": "insight"},
    {"from": "fsL", "from_port": "insight",  "to": "faL", "to_port": "insight"},
    {"from": "atr", "from_port": "value",    "to": "faL", "to_port": "value"},
    {"from": "faL", "from_port": "insight",  "to": "szL", "to_port": "insight"},
    {"from": "szL", "from_port": "target",   "to": "rkL", "to_port": "target"},
    {"from": "obL", "from_port": "low",      "to": "rkL", "to_port": "swing"},
    {"from": "rkL", "from_port": "adjusted", "to": "e1L", "to_port": "adjusted"},
    {"from": "e1L", "from_port": "adjusted", "to": "e2L", "to_port": "adjusted"},
    {"from": "e2L", "from_port": "adjusted", "to": "e3L", "to_port": "adjusted"},
    {"from": "e3L", "from_port": "adjusted", "to": "xcL", "to_port": "adjusted"},
    {"from": "obL", "from_port": "entry",    "to": "xcL", "to_port": "price"},
    {"from": "alS", "from_port": "insight",  "to": "fsS", "to_port": "insight"},
    {"from": "fsS", "from_port": "insight",  "to": "faS", "to_port": "insight"},
    {"from": "atr", "from_port": "value",    "to": "faS", "to_port": "value"},
    {"from": "faS", "from_port": "insight",  "to": "szS", "to_port": "insight"},
    {"from": "szS", "from_port": "target",   "to": "rkS", "to_port": "target"},
    {"from": "obS", "from_port": "high",     "to": "rkS", "to_port": "swing"},
    {"from": "rkS", "from_port": "adjusted", "to": "e1S", "to_port": "adjusted"},
    {"from": "e1S", "from_port": "adjusted", "to": "e2S", "to_port": "adjusted"},
    {"from": "e2S", "from_port": "adjusted", "to": "e3S", "to_port": "adjusted"},
    {"from": "e3S", "from_port": "adjusted", "to": "xcS", "to_port": "adjusted"},
    {"from": "obS", "from_port": "entry",    "to": "xcS", "to_port": "price"},
  ]
}

payload = {
  "graph": graph,
  "symbol": "XAUUSD",
  "timeframe": "M1",
  "n_bars": 10000,
  "target_r": 4.0,
  "target_close_pct": 0.75,
  "trail_mode": "candle",
  "trail_start": "after_target",
  "trail_params": {"buf_pips": 2},
  "risk_pct": 0.01,
  "initial_equity": 100.0,
  "max_concurrent": 1
}

print("Sending backtest request...")
r = requests.post("http://127.0.0.1:8765/graph/v2/backtest", json=payload, timeout=120)
print("Status:", r.status_code)
if r.status_code == 200:
    d = r.json()
    m = d.get("metrics", {})
    print("=== RESULTS ===")
    print("Trades:", m.get("trades"))
    print("Win Rate:", m.get("wr"), "%")
    print("Total R:", m.get("total_r"))
    print("Avg Win R:", m.get("avg_win_r"))
    print("Avg Loss R:", m.get("avg_loss_r"))
    print("Profit Factor:", m.get("profit_factor"))
    print("Max DD:", m.get("max_dd"), "%")
    print("Sharpe:", m.get("sharpe"))
    print("Sortino:", m.get("sortino"))
    print("Expectancy R:", m.get("expectancy_r"))
    print()
    print("All metric keys:", sorted(m.keys()))
else:
    print("Error:", r.text[:1000])
