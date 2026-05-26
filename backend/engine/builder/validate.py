"""
Graph structural validation. Run BEFORE execution to give the user
a clear error instead of a runtime stack trace.

A v1 graph must have:
  - exactly 1 node in category "signal"
  - exactly 1 node in category "entry"
  - exactly 1 node in category "risk"
  - 0..N filter nodes
  - every node.type registered in NODE_LIBRARY
  - every required param present (with a default if user didn't override)

Edges are accepted but not strictly enforced in v1 — the engine collects
nodes by category. (We add stricter wiring rules in v2 when nodes can
share data flows.)
"""
from __future__ import annotations
from typing import Any, Dict, List
from .nodes import NODE_LIBRARY


def validate_graph(graph: Dict[str, Any]) -> Dict[str, Any]:
    """Return the (possibly normalized) graph. Raise ValueError on problems."""
    if not isinstance(graph, dict):
        raise ValueError("Graph must be a JSON object.")
    nodes = graph.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("Graph must contain a non-empty 'nodes' array.")

    by_cat: Dict[str, List[dict]] = {"signal": [], "filter": [], "entry": [], "risk": []}
    seen_ids = set()
    for n in nodes:
        nid   = n.get("id")
        ntype = n.get("type")
        if not nid:                          raise ValueError("Every node needs an 'id'.")
        if nid in seen_ids:                  raise ValueError(f"Duplicate node id: {nid}")
        seen_ids.add(nid)
        if ntype not in NODE_LIBRARY:
            raise ValueError(f"Unknown node type: {ntype}")
        spec = NODE_LIBRARY[ntype]
        # Fill in defaults for any missing params
        params = dict(n.get("params") or {})
        for pspec in spec.params:
            if pspec["key"] not in params:
                params[pspec["key"]] = pspec["default"]
        n["params"] = params
        by_cat[spec.category].append(n)

    if len(by_cat["signal"]) != 1:
        raise ValueError(f"Graph needs exactly 1 Signal node (found {len(by_cat['signal'])}).")
    if len(by_cat["entry"]) != 1:
        raise ValueError(f"Graph needs exactly 1 Entry node (found {len(by_cat['entry'])}).")
    if len(by_cat["risk"]) != 1:
        raise ValueError(f"Graph needs exactly 1 Risk node (found {len(by_cat['risk'])}).")

    graph["nodes"] = nodes
    graph.setdefault("edges", [])
    return graph
