"""
Test SMC strategy on M15 timeframe - market execution + ATR stop
"""
import requests

BASE_URL = "http://127.0.0.1:8765"
TF = "M15"

def run(graph, target_r=4.0):
    payload = {
        "graph": graph,
        "symbol": "XAUUSD",
        "timeframe": TF,
        "n_bars": 10000,
        "target_r": target_r,
        "target_close_pct": 0.75,
        "trail_mode": "candle",
        "trail_start": "after_target",
        "trail_params": {"buf_pips": 2},
        "risk_pct": 0.01,
        "initial_equity": 100.0,
        "max_concurrent": 1
    }
    r = requests.post(f"{BASE_URL}/graph/v2/backtest", json=payload, timeout=90)
    if r.status_code != 200:
        return None, r.text[:200]
    d = r.json()
    m = d.get("metrics", {})
    return m, None


def make_market_atr(lookback, count, min_pierce, tol, atr_mult, atr_filter, session_end=17):
    return {
        "name": f"M15_MktATR_L{lookback}_P{min_pierce}_M{atr_mult}",
        "nodes": [
            {"id": "u1",  "type": "universe.single_asset",  "params": {"ticker": "XAUUSD", "timeframe": TF}},
            {"id": "atr", "type": "indicator.atr",           "params": {"period": 14}},
            {"id": "alL", "type": "alpha.liquidity_sweep",   "params": {"lookback": lookback, "count": count, "tolerance_pips": tol, "min_pierce_pips": min_pierce, "direction": "long"}},
            {"id": "fsL", "type": "filter.session",          "params": {"start_hour": 7, "end_hour": session_end}},
            {"id": "faL", "type": "filter.threshold",        "params": {"min": atr_filter, "max": 100}},
            {"id": "szL", "type": "sizing.fixed_pct",        "params": {"risk_pct": 1.0}},
            {"id": "rkL", "type": "risk.atr_stop",           "params": {"mult": atr_mult}},
            {"id": "e1L", "type": "exit.target_and_trail",   "params": {"target_r": 4.0, "close_pct": 0.75, "trail_mode": "candle", "trail_buf": 2.0}},
            {"id": "e2L", "type": "exit.breakeven_at_r",     "params": {"be_at_r": 1.5}},
            {"id": "e3L", "type": "exit.time_exit",          "params": {"bars": 30}},
            {"id": "xcL", "type": "execution.market",        "params": {"expiry_bars": 3}},
            {"id": "alS", "type": "alpha.liquidity_sweep",   "params": {"lookback": lookback, "count": count, "tolerance_pips": tol, "min_pierce_pips": min_pierce, "direction": "short"}},
            {"id": "fsS", "type": "filter.session",          "params": {"start_hour": 7, "end_hour": session_end}},
            {"id": "faS", "type": "filter.threshold",        "params": {"min": atr_filter, "max": 100}},
            {"id": "szS", "type": "sizing.fixed_pct",        "params": {"risk_pct": 1.0}},
            {"id": "rkS", "type": "risk.atr_stop",           "params": {"mult": atr_mult}},
            {"id": "e1S", "type": "exit.target_and_trail",   "params": {"target_r": 4.0, "close_pct": 0.75, "trail_mode": "candle", "trail_buf": 2.0}},
            {"id": "e2S", "type": "exit.breakeven_at_r",     "params": {"be_at_r": 1.5}},
            {"id": "e3S", "type": "exit.time_exit",          "params": {"bars": 30}},
            {"id": "xcS", "type": "execution.market",        "params": {"expiry_bars": 3}},
        ],
        "edges": [
            {"from": "alL", "from_port": "insight",  "to": "fsL", "to_port": "insight"},
            {"from": "fsL", "from_port": "insight",  "to": "faL", "to_port": "insight"},
            {"from": "atr", "from_port": "value",    "to": "faL", "to_port": "value"},
            {"from": "faL", "from_port": "insight",  "to": "szL", "to_port": "insight"},
            {"from": "szL", "from_port": "target",   "to": "rkL", "to_port": "target"},
            {"from": "atr", "from_port": "value",    "to": "rkL", "to_port": "atr"},
            {"from": "rkL", "from_port": "adjusted", "to": "e1L", "to_port": "adjusted"},
            {"from": "e1L", "from_port": "adjusted", "to": "e2L", "to_port": "adjusted"},
            {"from": "e2L", "from_port": "adjusted", "to": "e3L", "to_port": "adjusted"},
            {"from": "e3L", "from_port": "adjusted", "to": "xcL", "to_port": "adjusted"},
            {"from": "alS", "from_port": "insight",  "to": "fsS", "to_port": "insight"},
            {"from": "fsS", "from_port": "insight",  "to": "faS", "to_port": "insight"},
            {"from": "atr", "from_port": "value",    "to": "faS", "to_port": "value"},
            {"from": "faS", "from_port": "insight",  "to": "szS", "to_port": "insight"},
            {"from": "szS", "from_port": "target",   "to": "rkS", "to_port": "target"},
            {"from": "atr", "from_port": "value",    "to": "rkS", "to_port": "atr"},
            {"from": "rkS", "from_port": "adjusted", "to": "e1S", "to_port": "adjusted"},
            {"from": "e1S", "from_port": "adjusted", "to": "e2S", "to_port": "adjusted"},
            {"from": "e2S", "from_port": "adjusted", "to": "e3S", "to_port": "adjusted"},
            {"from": "e3S", "from_port": "adjusted", "to": "xcS", "to_port": "adjusted"},
        ]
    }


def make_limit_ob(lookback, count, min_pierce, tol, scan_max, expiry, atr_min, entry_ratio=0.5):
    return {
        "name": f"M15_LimOB_L{lookback}_P{min_pierce}_ER{entry_ratio}",
        "nodes": [
            {"id": "u1",  "type": "universe.single_asset",  "params": {"ticker": "XAUUSD", "timeframe": TF}},
            {"id": "atr", "type": "indicator.atr",           "params": {"period": 14}},
            {"id": "obL", "type": "indicator.order_block",   "params": {"direction": "long",  "scan_min": 3, "scan_max": scan_max, "entry_ratio": entry_ratio}},
            {"id": "alL", "type": "alpha.liquidity_sweep",   "params": {"lookback": lookback, "count": count, "tolerance_pips": tol, "min_pierce_pips": min_pierce, "direction": "long"}},
            {"id": "fsL", "type": "filter.session",          "params": {"start_hour": 7, "end_hour": 17}},
            {"id": "faL", "type": "filter.threshold",        "params": {"min": atr_min, "max": 100}},
            {"id": "szL", "type": "sizing.fixed_pct",        "params": {"risk_pct": 1.0}},
            {"id": "rkL", "type": "risk.structure_stop",     "params": {"buf_pips": 3}},
            {"id": "e1L", "type": "exit.target_and_trail",   "params": {"target_r": 4.0, "close_pct": 0.75, "trail_mode": "candle", "trail_buf": 2.0}},
            {"id": "e2L", "type": "exit.breakeven_at_r",     "params": {"be_at_r": 1.5}},
            {"id": "e3L", "type": "exit.time_exit",          "params": {"bars": 30}},
            {"id": "xcL", "type": "execution.limit_at",      "params": {"expiry_bars": expiry}},
            {"id": "obS", "type": "indicator.order_block",   "params": {"direction": "short", "scan_min": 3, "scan_max": scan_max, "entry_ratio": 1.0 - entry_ratio}},
            {"id": "alS", "type": "alpha.liquidity_sweep",   "params": {"lookback": lookback, "count": count, "tolerance_pips": tol, "min_pierce_pips": min_pierce, "direction": "short"}},
            {"id": "fsS", "type": "filter.session",          "params": {"start_hour": 7, "end_hour": 17}},
            {"id": "faS", "type": "filter.threshold",        "params": {"min": atr_min, "max": 100}},
            {"id": "szS", "type": "sizing.fixed_pct",        "params": {"risk_pct": 1.0}},
            {"id": "rkS", "type": "risk.structure_stop",     "params": {"buf_pips": 3}},
            {"id": "e1S", "type": "exit.target_and_trail",   "params": {"target_r": 4.0, "close_pct": 0.75, "trail_mode": "candle", "trail_buf": 2.0}},
            {"id": "e2S", "type": "exit.breakeven_at_r",     "params": {"be_at_r": 1.5}},
            {"id": "e3S", "type": "exit.time_exit",          "params": {"bars": 30}},
            {"id": "xcS", "type": "execution.limit_at",      "params": {"expiry_bars": expiry}},
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


print("=" * 95)
print(f"ARCHITECTURE A: M15 — Market execution + ATR stop")
print(f"{'LB':>4} {'Cnt':>4} {'Pier':>5} {'Tol':>4} {'Mult':>5} {'ATRf':>5} {'Sess':>5} | {'Trades':>7} {'WR%':>7} {'TotalR':>8} {'PF':>6} {'MaxDD%':>8}")
print("-" * 95)

configs_a = [
    # (lookback, count, min_pierce, tol, atr_mult, atr_filter, session_end)
    (20, 2, 2.0, 3, 0.7, 1.0, 17),
    (25, 2, 2.0, 3, 0.7, 1.0, 17),
    (30, 2, 3.0, 3, 0.7, 1.0, 17),
    (30, 2, 3.0, 3, 0.8, 1.0, 17),
    (30, 2, 3.0, 3, 1.0, 1.0, 17),
    (40, 2, 3.0, 4, 0.7, 1.0, 17),
    (40, 2, 4.0, 4, 0.7, 1.0, 17),
    (50, 2, 4.0, 4, 0.7, 1.0, 17),
    (50, 3, 3.0, 3, 0.7, 1.0, 17),
    (60, 2, 4.0, 4, 0.8, 1.0, 17),
    # London only
    (30, 2, 3.0, 3, 0.7, 1.0, 12),
    (40, 2, 3.0, 4, 0.7, 1.0, 12),
]

all_results = []
for cfg in configs_a:
    lb, cnt, pierce, tol, mult, atr_f, sess = cfg
    g = make_market_atr(lb, cnt, pierce, tol, mult, atr_f, sess)
    m, err = run(g)
    if m is None:
        print(f"{lb:>4} {cnt:>4} {pierce:>5} {tol:>4} {mult:>5} {atr_f:>5} {sess:>5} | ERROR: {err}")
        continue
    wr = m.get("wr", 0)
    tr = round(m.get("total_r", 0), 2)
    pf = round(m.get("profit_factor", 0), 2)
    dd = round(m.get("max_dd", 0), 1)
    trades = m.get("trades", 0)
    flag = " <<< HIT" if wr >= 60 else (" <-- CLOSE" if wr >= 50 else "")
    print(f"{lb:>4} {cnt:>4} {pierce:>5} {tol:>4} {mult:>5} {atr_f:>5} {sess:>5} | {trades:>7} {wr:>7.1f} {tr:>8} {pf:>6} {dd:>8}{flag}")
    all_results.append(("A", cfg, m))


print("\n" + "=" * 95)
print(f"ARCHITECTURE B: M15 — Limit at OB (entry_ratio=0.5 & 0.25) + structure stop")
print(f"{'LB':>4} {'Cnt':>4} {'Pier':>5} {'Tol':>4} {'SMax':>5} {'Exp':>4} {'ER':>5} | {'Trades':>7} {'WR%':>7} {'TotalR':>8} {'PF':>6} {'MaxDD%':>8}")
print("-" * 95)

configs_b = [
    # (lookback, count, min_pierce, tol, scan_max, expiry, entry_ratio)
    (20, 2, 2.0, 3, 15, 5,  0.5),
    (25, 2, 2.0, 3, 15, 8,  0.5),
    (30, 2, 3.0, 3, 15, 8,  0.5),
    (30, 2, 3.0, 3, 15, 8,  0.25),
    (30, 2, 3.0, 3, 20, 10, 0.5),
    (40, 2, 3.0, 4, 20, 10, 0.5),
    (40, 2, 3.0, 4, 20, 10, 0.25),
    (40, 2, 4.0, 4, 20, 10, 0.5),
    (50, 2, 4.0, 4, 20, 10, 0.5),
    (50, 3, 3.0, 3, 15, 8,  0.5),
]

for cfg in configs_b:
    lb, cnt, pierce, tol, smax, exp, er = cfg
    g = make_limit_ob(lb, cnt, pierce, tol, smax, exp, 1.0, er)
    m, err = run(g)
    if m is None:
        print(f"{lb:>4} {cnt:>4} {pierce:>5} {tol:>4} {smax:>5} {exp:>4} {er:>5} | ERROR: {err}")
        continue
    wr = m.get("wr", 0)
    tr = round(m.get("total_r", 0), 2)
    pf = round(m.get("profit_factor", 0), 2)
    dd = round(m.get("max_dd", 0), 1)
    trades = m.get("trades", 0)
    flag = " <<< HIT" if wr >= 60 else (" <-- CLOSE" if wr >= 50 else "")
    print(f"{lb:>4} {cnt:>4} {pierce:>5} {tol:>4} {smax:>5} {exp:>4} {er:>5} | {trades:>7} {wr:>7.1f} {tr:>8} {pf:>6} {dd:>8}{flag}")
    all_results.append(("B", cfg, m))

# Summary
print("\n=== TOP 5 BY WIN RATE ===")
all_results.sort(key=lambda x: x[2].get("wr", 0), reverse=True)
for arch, cfg, m in all_results[:5]:
    print(f"Arch={arch} cfg={cfg} | WR={m.get('wr',0):.1f}% Trades={m.get('trades')} TotalR={round(m.get('total_r',0),2)} PF={round(m.get('profit_factor',0),2)} MaxDD={round(m.get('max_dd',0),1)}%")
