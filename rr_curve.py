"""
Map the win-rate vs RR curve for M15 gold SMC.
Also test: long-only, no breakeven, different stops.
"""
import requests

BASE_URL = "http://127.0.0.1:8765"
TF = "M15"

def run(graph, target_r=4.0, be_r=None):
    payload = {
        "graph": graph,
        "symbol": "XAUUSD",
        "timeframe": TF,
        "n_bars": 10000,
        "target_r": target_r,
        "target_close_pct": 0.5,
        "trail_mode": "candle",
        "trail_start": "after_target",
        "trail_params": {"buf_pips": 2},
        "risk_pct": 0.01,
        "initial_equity": 100.0,
        "max_concurrent": 1
    }
    r = requests.post(f"{BASE_URL}/graph/v2/backtest", json=payload, timeout=90)
    if r.status_code != 200:
        return None
    m = r.json().get("metrics", {})
    return m


def make_graph(direction="both", lookback=30, pierce=3.0, tol=3, atr_mult=0.7, sess_end=17, use_be=True):
    nodes = [
        {"id": "u1",  "type": "universe.single_asset",  "params": {"ticker": "XAUUSD", "timeframe": TF}},
        {"id": "atr", "type": "indicator.atr",           "params": {"period": 14}},
    ]
    edges = []

    for side in (["long"] if direction == "long" else ["short"] if direction == "short" else ["long", "short"]):
        s = "L" if side == "long" else "S"
        dir_sweep = "long" if side == "long" else "short"

        nodes += [
            {"id": f"al{s}", "type": "alpha.liquidity_sweep",
             "params": {"lookback": lookback, "count": 2, "tolerance_pips": tol, "min_pierce_pips": pierce, "direction": dir_sweep}},
            {"id": f"fs{s}", "type": "filter.session",   "params": {"start_hour": 7, "end_hour": sess_end}},
            {"id": f"fa{s}", "type": "filter.threshold", "params": {"min": 1.0, "max": 100}},
            {"id": f"sz{s}", "type": "sizing.fixed_pct", "params": {"risk_pct": 1.0}},
            {"id": f"rk{s}", "type": "risk.atr_stop",    "params": {"mult": atr_mult}},
            {"id": f"e1{s}", "type": "exit.target_and_trail",
             "params": {"target_r": 4.0, "close_pct": 0.5, "trail_mode": "candle", "trail_buf": 2.0}},
            {"id": f"e3{s}", "type": "exit.time_exit",   "params": {"bars": 30}},
            {"id": f"xc{s}", "type": "execution.market", "params": {"expiry_bars": 3}},
        ]
        if use_be:
            nodes.append({"id": f"e2{s}", "type": "exit.breakeven_at_r", "params": {"be_at_r": 1.5}})

        edges += [
            {"from": f"al{s}", "from_port": "insight",  "to": f"fs{s}", "to_port": "insight"},
            {"from": f"fs{s}", "from_port": "insight",  "to": f"fa{s}", "to_port": "insight"},
            {"from": "atr",    "from_port": "value",    "to": f"fa{s}", "to_port": "value"},
            {"from": f"fa{s}", "from_port": "insight",  "to": f"sz{s}", "to_port": "insight"},
            {"from": f"sz{s}", "from_port": "target",   "to": f"rk{s}", "to_port": "target"},
            {"from": "atr",    "from_port": "value",    "to": f"rk{s}", "to_port": "atr"},
            {"from": f"rk{s}", "from_port": "adjusted", "to": f"e1{s}", "to_port": "adjusted"},
        ]
        if use_be:
            edges += [
                {"from": f"e1{s}", "from_port": "adjusted", "to": f"e2{s}", "to_port": "adjusted"},
                {"from": f"e2{s}", "from_port": "adjusted", "to": f"e3{s}", "to_port": "adjusted"},
            ]
        else:
            edges.append({"from": f"e1{s}", "from_port": "adjusted", "to": f"e3{s}", "to_port": "adjusted"})
        edges.append({"from": f"e3{s}", "from_port": "adjusted", "to": f"xc{s}", "to_port": "adjusted"})

    return {"name": f"SMC_{direction}_{TF}", "nodes": nodes, "edges": edges}


# ── Step 1: RR curve — best M15 config, both directions ─────────────────────
print("=" * 70)
print("RR CURVE: LB=40 Pierce=3.0 Tol=4 ATRmult=0.7 London+NY (7-17)")
print(f"{'Target R':>10} | {'Trades':>7} {'WR%':>7} {'TotalR':>9} {'PF':>6} {'MaxDD%':>8}")
print("-" * 70)

best_cfg_graph = make_graph(direction="both", lookback=40, pierce=3.0, tol=4, atr_mult=0.7, sess_end=17, use_be=False)
for tr in [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]:
    m = run(best_cfg_graph, target_r=tr)
    if m:
        wr = m.get("wr", 0)
        flag = " <<< 60%+" if wr >= 60 else (" <-- 50%+" if wr >= 50 else "")
        print(f"{tr:>10} | {m.get('trades',0):>7} {wr:>7.1f} {round(m.get('total_r',0),2):>9} {round(m.get('profit_factor',0),2):>6} {round(m.get('max_dd',0),1):>8}{flag}")

# ── Step 2: Long-only (gold bias) ─────────────────────────────────────────────
print("\n" + "=" * 70)
print("LONG-ONLY (gold upward bias): LB=40 Pierce=3.0 ATRmult=0.7")
print(f"{'Target R':>10} | {'Trades':>7} {'WR%':>7} {'TotalR':>9} {'PF':>6} {'MaxDD%':>8}")
print("-" * 70)

long_graph = make_graph(direction="long", lookback=40, pierce=3.0, tol=4, atr_mult=0.7, sess_end=17, use_be=False)
for tr in [2.0, 3.0, 4.0, 5.0]:
    m = run(long_graph, target_r=tr)
    if m:
        wr = m.get("wr", 0)
        flag = " <<< 60%+" if wr >= 60 else (" <-- 50%+" if wr >= 50 else "")
        print(f"{tr:>10} | {m.get('trades',0):>7} {wr:>7.1f} {round(m.get('total_r',0),2):>9} {round(m.get('profit_factor',0),2):>6} {round(m.get('max_dd',0),1):>8}{flag}")

# ── Step 3: London-only, long-only ───────────────────────────────────────────
print("\n" + "=" * 70)
print("LONDON ONLY (7-12) + LONG-ONLY: vary pierce + lookback at 4R target")
print(f"{'LB':>4} {'Pierce':>7} {'Mult':>6} | {'Trades':>7} {'WR%':>7} {'TotalR':>9} {'PF':>6} {'MaxDD%':>8}")
print("-" * 70)

for lb, pierce, mult in [(30,2.0,0.7),(30,3.0,0.7),(40,3.0,0.7),(40,4.0,0.7),(50,3.0,0.7),(50,4.0,0.8),(60,4.0,0.8)]:
    g = make_graph(direction="long", lookback=lb, pierce=pierce, tol=4, atr_mult=mult, sess_end=12, use_be=False)
    m = run(g, target_r=4.0)
    if m:
        wr = m.get("wr", 0)
        flag = " <<< 60%+" if wr >= 60 else (" <-- 50%+" if wr >= 50 else "")
        print(f"{lb:>4} {pierce:>7} {mult:>6} | {m.get('trades',0):>7} {wr:>7.1f} {round(m.get('total_r',0),2):>9} {round(m.get('profit_factor',0),2):>6} {round(m.get('max_dd',0),1):>8}{flag}")

# ── Step 4: EMA trend filter for direction ───────────────────────────────────
# Use EMA crossover as a confirm: only go long when price > EMA50
# (simulate by using EMA50 node + threshold alpha, then combine_and)
# But we can simulate direction-bias differently:
# Use London ONLY + LONG only, most profitable combination found above

# ── Step 5: Summary stats at best config ─────────────────────────────────────
print("\n" + "=" * 70)
print("BEST CONFIG DEEP DIVE: LB=40 Pierce=3.0 Long+Short London 7-12")
print("Testing different ATR multipliers at 4R target")
print(f"{'ATRmult':>8} | {'Trades':>7} {'WR%':>7} {'TotalR':>9} {'PF':>6} {'MaxDD%':>8} {'AvgWin':>8}")
print("-" * 70)

for mult in [0.5, 0.6, 0.7, 0.8, 1.0, 1.2, 1.5]:
    g = make_graph(direction="both", lookback=40, pierce=3.0, tol=4, atr_mult=mult, sess_end=12, use_be=False)
    m = run(g, target_r=4.0)
    if m:
        wr = m.get("wr", 0)
        avg_w = m.get("avg_win", m.get("avg_rr", 0)) or 0
        flag = " <<< 60%+" if wr >= 60 else (" <-- 50%+" if wr >= 50 else "")
        print(f"{mult:>8} | {m.get('trades',0):>7} {wr:>7.1f} {round(m.get('total_r',0),2):>9} {round(m.get('profit_factor',0),2):>6} {round(m.get('max_dd',0),1):>8} {round(avg_w,2):>8}{flag}")
