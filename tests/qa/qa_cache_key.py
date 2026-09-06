"""QA check for FINDING-9: builder backtest cache key must cover all result-affecting fields.

The old key was a hand-picked subset (graph/symbol/timeframe/n_bars/target_r/
close_pct/trail_mode). The fix keys on the full request body. We verify that
sliders the old key ignored now bust the cache, while identical requests still hit.
"""
from backend.api.routes_graph_v2 import GraphBacktestV2Request
from backend.api.cache import BacktestCache

cache = BacktestCache()
GRAPH = {"nodes": [{"id": "a", "type": "indicator.ema", "params": {"len": 20}}], "edges": []}

results = []


def check(name, cond, detail=""):
    results.append(cond)
    print(("[PASS] " if cond else "[FAIL] ") + name + (f" -- {detail}" if detail else ""))


def old_key(req):
    """The previous hand-picked subset key."""
    return {
        "graph": req.graph, "symbol": req.symbol, "timeframe": req.timeframe,
        "n_bars": req.n_bars, "target_r": req.target_r,
        "close_pct": req.target_close_pct, "trail_mode": req.trail_mode,
    }


def new_key(req):
    """The fixed full-request key (mirrors the route)."""
    return req.model_dump(mode="json", exclude={"csv_data_id"})


def k(d):
    return cache._key(d)


def main():
    base = GraphBacktestV2Request(graph=GRAPH)

    # Pairs that differ ONLY by a slider the OLD key ignored
    variants = {
        "spread_pips":    GraphBacktestV2Request(graph=GRAPH, spread_pips=2.0),
        "commission":     GraphBacktestV2Request(graph=GRAPH, commission=7.0),
        "slippage_pips":  GraphBacktestV2Request(graph=GRAPH, slippage_pips=1.5),
        "risk_pct":       GraphBacktestV2Request(graph=GRAPH, risk_pct=0.02),
        "initial_equity": GraphBacktestV2Request(graph=GRAPH, initial_equity=5000.0),
        "trail_params":   GraphBacktestV2Request(graph=GRAPH, trail_params={"buf_pips": 9}),
        "date_range":     GraphBacktestV2Request(graph=GRAPH, start_date="2025-01-01"),
        "max_concurrent": GraphBacktestV2Request(graph=GRAPH, max_concurrent=3),
    }

    print("--- OLD key (demonstrates the bug: collisions) ---")
    old_collisions = 0
    for name, v in variants.items():
        collided = k(old_key(base)) == k(old_key(v))
        if collided:
            old_collisions += 1
        print(f"   {name:15} old-key collision: {collided}")
    check("OLD key collided on ignored sliders", old_collisions == len(variants),
          f"{old_collisions}/{len(variants)} collided")

    print("\n--- NEW key (the fix: every slider busts the cache) ---")
    for name, v in variants.items():
        distinct = k(new_key(base)) != k(new_key(v))
        check(f"NEW key busts on {name}", distinct)

    # Cache must still HIT for an identical request (no over-busting)
    base2 = GraphBacktestV2Request(graph=GRAPH)
    check("NEW key stable for identical request", k(new_key(base)) == k(new_key(base2)))

    # The graph itself (node param sliders) must also bust
    g2 = {"nodes": [{"id": "a", "type": "indicator.ema", "params": {"len": 50}}], "edges": []}
    base3 = GraphBacktestV2Request(graph=g2)
    check("NEW key busts on node-param change", k(new_key(base)) != k(new_key(base3)))

    ok = all(results)
    print(f"\nCACHE-KEY CHECK: {'PASS' if ok else 'FAIL'} ({sum(results)}/{len(results)})")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
