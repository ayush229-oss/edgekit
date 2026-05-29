"""
v2 graph engine — multi-lane execution with typed wires.

Execution model per bar i:
    1. Resolve every wire's value by topo-walking the graph from sources → sinks.
       Each node sees its inputs already-resolved (dict[port_name] -> value).
    2. Sink = execution.* node. Its output (OrderIntent) becomes a setup.
    3. Setups are batched and handed to the existing simulator for fills + PnL.

Why one big graph walk per bar:
  - Lets indicators feed multiple consumers (sizing AND risk AND exit can all
    read the same ATR — no recomputation).
  - Lets us catch lookahead leaks: nodes receive a frozen df-view that hides bars > i.
  - Keeps the engine ~50 lines instead of a switch over lane types.
"""
from __future__ import annotations
from typing import Any, Dict, List
import pandas as pd

from .nodes import NODE_LIBRARY, NodeSpec
from .types import RunContext, OrderIntent
from .validate import validate_graph
from .safety import frozen_view


class GraphV2Strategy:
    """Drop-in replacement for the v1 hand-coded strategy classes."""
    name        = "Custom strategy (v2)"
    description = "User-built strategy from the visual node builder (5-lane model)."
    timeframes  = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
    instruments = ["XAUUSD", "EURUSD", "GBPUSD", "BTCUSD", "*"]
    param_schema: List[Any] = []

    def __init__(self, graph: Dict[str, Any]):
        self.graph = validate_graph(graph)
        self.nodes = {n["id"]: n for n in self.graph["nodes"]}
        self.edges = self.graph["edges"]

        # Pre-build adjacency: node_id -> list of (input_port, source_id, source_port)
        self._incoming: Dict[str, List[tuple]] = {nid: [] for nid in self.nodes}
        for e in self.edges:
            self._incoming[e["to"]].append((e["to_port"], e["from"], e["from_port"]))

        # Topological order — guaranteed by validate_graph (DAG check)
        self._topo = self.graph["__topo__"]

        # Identify the execution sinks (final nodes that produce OrderIntents)
        self._sinks = [nid for nid, n in self.nodes.items()
                       if NODE_LIBRARY[n["type"]].lane == "execution"]

    def default_params(self):
        return {"pip": 0.10}

    def detect(self, df: pd.DataFrame, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        ctx = RunContext(pip=float(params.get("pip", 0.10)))
        # Save for post-run inspection (chart preview reads ctx.cache for
        # indicator series so the frontend can plot them as line overlays).
        self.ctx = ctx

        # 1) prepare-phase: precompute indicator series + set warmup_bars, then
        #    collect any chart artifacts (zones/levels/markers) the node exposes.
        for nid in self._topo:
            n    = self.nodes[nid]
            spec = NODE_LIBRARY[n["type"]]
            if spec.prepare_fn:
                spec.prepare_fn(df, ctx, n["params"])
            if getattr(spec, "artifacts_fn", None):
                try:
                    for a in (spec.artifacts_fn(df, ctx, n["params"]) or []):
                        a.setdefault("node_id", nid)
                        a["node_type"] = n["type"]
                        a["lane"]      = spec.lane
                        ctx.trace.append(a)
                except Exception:
                    # Visualization must never break a backtest.
                    pass

        setups: List[Dict[str, Any]] = []
        n_bars = len(df)
        for i in range(ctx.warmup_bars, n_bars):
            fview = frozen_view(df, i)

            # Per-bar wire resolution table: (node_id, port_name) -> value
            resolved: Dict[tuple, Any] = {}

            for nid in self._topo:
                n    = self.nodes[nid]
                spec = NODE_LIBRARY[n["type"]]

                # Assemble inputs from incoming edges
                inputs = {}
                for (in_port, src_id, src_port) in self._incoming[nid]:
                    inputs[in_port] = resolved.get((src_id, src_port))

                # Stash node id so stateful nodes (xover, cooldown) get unique slots
                ctx.state["__current_node__"] = nid

                out = spec.eval_fn(fview, i, ctx, inputs, n["params"])
                if out:
                    for k, v in out.items():
                        resolved[(nid, k)] = v

            # Collect setups from every execution sink
            for sink_id in self._sinks:
                order = resolved.get((sink_id, "order"))
                if isinstance(order, OrderIntent):
                    setups.append(order.to_setup())

        return setups
