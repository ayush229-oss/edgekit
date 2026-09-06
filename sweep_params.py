"""
Run a systematic parameter search for the SMC Gold 1m strategy.
Tests different combinations of sweep and OB parameters.
"""
import requests, json, time
from itertools import product

BASE_URL = "http://127.0.0.1:8765"

def make_graph(lookback, count, min_pierce, tolerance, scan_max, expiry, atr_min, entry_ratio=0.5):
    return {
        "name": f"SMC_L{lookback}_C{count}_P{min_pierce}_SM{scan_max}_E{expiry}",
        "nodes": [
            {"id": "u1",  "type": "universe.single_asset",  "params": {"ticker": "XAUUSD", "timeframe": "M1"}},
            {"id": "atr", "type": "indicator.atr",           "params": {"period": 14}},
            {"id": "obL", "type": "indicator.order_block",   "params": {"direction": "long",  "scan_min": 3, "scan_max": scan_max, "entry_ratio": entry_ratio}},
            {"id": "alL", "type": "alpha.liquidity_sweep",   "params": {"lookback": lookback, "count": count, "tolerance_pips": tolerance, "min_pierce_pips": min_pierce, "direction": "long"}},
            {"id": "fsL", "type": "filter.session",          "params": {"start_hour": 7, "end_hour": 17}},
            {"id": "faL", "type": "filter.threshold",        "params": {"min": atr_min, "max": 100}},
            {"id": "szL", "type": "sizing.fixed_pct",        "params": {"risk_pct": 1.0}},
            {"id": "rkL", "type": "risk.structure_stop",     "params": {"buf_pips": 3}},
            {"id": "e1L", "type": "exit.target_and_trail",   "params": {"target_r": 4.0, "close_pct": 0.75, "trail_mode": "candle", "trail_buf": 2.0}},
            {"id": "e2L", "type": "exit.breakeven_at_r",     "params": {"be_at_r": 1.5}},
            {"id": "e3L", "type": "exit.time_exit",          "params": {"bars": 60}},
            {"id": "xcL", "type": "execution.limit_at",      "params": {"expiry_bars": expiry}},
            {"id": "obS", "type": "indicator.order_block",   "params": {"direction": "short", "scan_min": 3, "scan_max": scan_max, "entry_ratio": entry_ratio}},
            {"id": "alS", "type": "alpha.liquidity_sweep",   "params": {"lookback": lookback, "count": count, "tolerance_pips": tolerance, "min_pierce_pips": min_pierce, "direction": "short"}},
            {"id": "fsS", "type": "filter.session",          "params": {"start_hour": 7, "end_hour": 17}},
            {"id": "faS", "type": "filter.threshold",        "params": {"min": atr_min, "max": 100}},
            {"id": "szS", "type": "sizing.fixed_pct",        "params": {"risk_pct": 1.0}},
            {"id": "rkS", "type": "risk.structure_stop",     "params": {"buf_pips": 3}},
            {"id": "e1S", "type": "exit.target_and_trail",   "params": {"target_r": 4.0, "close_pct": 0.75, "trail_mode": "candle", "trail_buf": 2.0}},
            {"id": "e2S", "type": "exit.breakeven_at_r",     "params": {"be_at_r": 1.5}},
            {"id": "e3S", "type": "exit.time_exit",          "params": {"bars": 60}},
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

def run_backtest(graph):
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
    r = requests.post(f"{BASE_URL}/graph/v2/backtest", json=payload, timeout=90)
    if r.status_code == 200:
        d = r.json()
        m = d.get("metrics", {})
        return {
            "trades": m.get("trades", 0),
            "wr": round(m.get("wr", 0), 1),
            "total_r": round(m.get("total_r", 0), 2),
            "pf": round(m.get("profit_factor", 0), 2),
            "max_dd": round(m.get("max_dd", 0), 1),
            "ev": round(m.get("ev", 0) or 0, 3),
        }
    else:
        return None

# Parameter grid — focused search
configs = [
    # (lookback, count, min_pierce, tolerance, scan_max, expiry, atr_min)
    # --- baseline ---
    (15, 2, 0.5, 2, 6,  5,  0.25),   # current (bad)
    # --- higher pierce requirement ---
    (20, 2, 2.0, 3, 10, 10, 0.35),
    (25, 2, 3.0, 3, 15, 10, 0.35),
    (30, 2, 3.0, 3, 15, 15, 0.40),
    (30, 3, 2.0, 3, 15, 10, 0.35),
    # --- very strict pierce ---
    (40, 2, 5.0, 4, 20, 15, 0.40),
    (50, 2, 5.0, 4, 20, 20, 0.50),
    # --- 3-touch requirement ---
    (40, 3, 3.0, 3, 15, 10, 0.35),
    (50, 3, 3.0, 4, 20, 15, 0.40),
    # --- wide parameters ---
    (60, 2, 3.0, 4, 25, 20, 0.40),
    (80, 2, 4.0, 5, 30, 20, 0.50),
    # --- different entry ratio (deeper in OB) ---
    (30, 2, 3.0, 3, 15, 15, 0.40),   # entry_ratio=0.25
    (40, 2, 4.0, 4, 20, 15, 0.40),   # entry_ratio=0.25
]

results = []
print(f"{'LB':>4} {'Cnt':>4} {'Pier':>5} {'Tol':>4} {'SMax':>5} {'Exp':>4} {'ATR':>5} | {'Trades':>7} {'WR%':>7} {'TotalR':>8} {'PF':>6} {'MaxDD':>8}")
print("-" * 80)

for i, cfg in enumerate(configs):
    lb, cnt, pierce, tol, smax, exp, atr_min = cfg
    entry_ratio = 0.25 if i >= 11 else 0.5  # last 2 use deeper entry
    graph = make_graph(lb, cnt, pierce, tol, smax, exp, atr_min, entry_ratio)
    res = run_backtest(graph)
    if res:
        results.append((cfg, entry_ratio, res))
        wr_flag = " <-- " if res["wr"] >= 55 else ""
        print(f"{lb:>4} {cnt:>4} {pierce:>5} {tol:>4} {smax:>5} {exp:>4} {atr_min:>5} | "
              f"{res['trades']:>7} {res['wr']:>7} {res['total_r']:>8} {res['pf']:>6} {res['max_dd']:>8}{wr_flag}")
    else:
        print(f"{lb:>4} {cnt:>4} {pierce:>5} {tol:>4} {smax:>5} {exp:>4} {atr_min:>5} | ERROR")

# Find best configurations
print("\n=== TOP RESULTS BY WIN RATE ===")
results.sort(key=lambda x: x[2]["wr"], reverse=True)
for cfg, er, res in results[:5]:
    lb, cnt, pierce, tol, smax, exp, atr_min = cfg
    print(f"LB={lb} Cnt={cnt} Pierce={pierce} Tol={tol} SMax={smax} Exp={exp} ATR={atr_min} ER={er} | "
          f"WR={res['wr']}% Trades={res['trades']} TotalR={res['total_r']} PF={res['pf']} MaxDD={res['max_dd']}%")
