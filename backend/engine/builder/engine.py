"""
GraphStrategy — adapts a node-graph JSON into the same interface as the
hand-coded strategy classes (so the existing simulator and API can run it
without changes).

Execution model (v1):
    for each bar i:
        d = signal.eval(df, i)              # "Bull" / "Bear" / None
        if d is None: continue
        if any filter.eval(df, i) == False: continue
        entry_px = entry.eval(df, i, d)
        sl_px    = risk.eval(df, i, d, entry_px)
        emit setup { signal_idx, direction, entry, sl, risk, ... }

Filters share the per-DataFrame cache (atr/ema/rsi pre-computes), and
stateful filters (e.g. cooldown) get their node-id injected so they can
maintain their own state slot.
"""
from __future__ import annotations
from typing import Any, Dict, List
import pandas as pd

from .nodes import NODE_LIBRARY, _cache
from .validate import validate_graph


class GraphStrategy:
    """
    Drop-in replacement for the hand-coded strategy classes.
    Constructed from a graph dict; exposes .detect(df, params) like every
    other strategy in the registry.
    """
    name        = "Custom strategy"
    description = "User-built strategy from the visual node builder."
    timeframes  = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
    instruments = ["XAUUSD", "EURUSD", "GBPUSD", "BTCUSD", "*"]
    param_schema: List[Any] = []     # graphs carry their own params per-node

    def __init__(self, graph: Dict[str, Any]):
        self.graph  = validate_graph(graph)
        # Bucket nodes by category for O(1) access during the bar loop.
        self._signal = self._risk = self._entry = None
        self._filters: List[dict] = []
        for n in self.graph["nodes"]:
            cat = NODE_LIBRARY[n["type"]].category
            if   cat == "signal":  self._signal = n
            elif cat == "entry":   self._entry  = n
            elif cat == "risk":    self._risk   = n
            elif cat == "filter":  self._filters.append(n)

    # Keeps the existing strategy interface — main.py merges these into params
    def default_params(self) -> Dict[str, Any]:
        return {"pip": 0.10}

    def detect(self, df: pd.DataFrame, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        # Wipe per-df cache so back-to-back runs don't share state across graphs.
        df.attrs.pop("__edgekit_node_cache__", None)
        pip = float(params.get("pip", 0.10))

        sig_spec  = NODE_LIBRARY[self._signal["type"]]
        ent_spec  = NODE_LIBRARY[self._entry["type"]]
        risk_spec = NODE_LIBRARY[self._risk["type"]]

        sig_p  = {**self._signal["params"], "pip": pip, "__node_id__": self._signal["id"]}
        ent_p  = {**self._entry["params"],  "pip": pip, "__node_id__": self._entry["id"]}
        risk_p = {**self._risk["params"],   "pip": pip, "__node_id__": self._risk["id"]}
        filters = [
            (NODE_LIBRARY[f["type"]], {**f["params"], "pip": pip, "__node_id__": f["id"]})
            for f in self._filters
        ]

        setups: List[Dict[str, Any]] = []
        cache = _cache(df)
        n = len(df)
        for i in range(n):
            direction = sig_spec.eval_fn(df, i, sig_p)
            if direction is None:
                continue

            # All filters must pass (logical AND).
            passed = True
            for fspec, fp in filters:
                if not fspec.eval_fn(df, i, fp):
                    passed = False
                    break
            if not passed:
                continue

            entry_px = ent_spec.eval_fn(df, i, ent_p, direction)
            sl_px    = risk_spec.eval_fn(df, i, risk_p, direction, entry_px)
            risk_amt = abs(entry_px - sl_px)
            if risk_amt < 1e-9:
                continue   # degenerate setup, skip

            # Commit any stateful filter changes (e.g. cooldown remembers this bar)
            for f in self._filters:
                if f["type"] == "filter.cooldown":
                    cache[f"_last_{f['id']}"] = i

            setups.append({
                "signal_idx": i,
                "direction":  direction,
                "entry":      float(entry_px),
                "sl":         float(sl_px),
                "risk":       float(risk_amt),
                "liq_level":  float(entry_px),
                "tps":        [],     # filled by simulator from target_r
                "meta":       {"source": "graph"},
            })
        return setups
