"""
v2 graph validator.

Rules:
  1. Every node.type registered in NODE_LIBRARY.
  2. Graph is a DAG (no cycles).
  3. At least one execution node (sink).
  4. Every node's required inputs are wired.
  5. Each edge wires compatible PortTypes.
  6. Missing params filled in with their declared default.
  7. Topological order is attached as graph["__topo__"].
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from .nodes import NODE_LIBRARY


def validate_graph(graph: Dict[str, Any], node_library: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Validate and normalise a V2 graph dict.

    node_library — pass an already-merged library (NODE_LIBRARY + user defs) to
    avoid re-registering user nodes on every call. When omitted the global
    NODE_LIBRARY is used and any graph.user_defs are registered inline.
    """
    if not isinstance(graph, dict):
        raise ValueError("Graph must be an object.")

    if node_library is None:
        from .user_nodes import build_user_node_spec
        lib = dict(NODE_LIBRARY)
        for udef in graph.get("user_defs", []):
            spec = build_user_node_spec(udef)
            lib[spec.type] = spec
    else:
        lib = node_library
    nodes = graph.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("Graph must contain a non-empty 'nodes' array.")
    edges = graph.get("edges", []) or []

    # 1) Validate node types + fill defaults
    by_id: Dict[str, dict] = {}
    for n in nodes:
        nid   = n.get("id")
        ntype = n.get("type")
        if not nid:                          raise ValueError("Every node needs an 'id'.")
        if nid in by_id:                     raise ValueError(f"Duplicate node id: {nid}")
        spec = lib.get(ntype)
        if spec is None:
            raise ValueError(f"Unknown node type: {ntype}")
        params = dict(n.get("params") or {})
        for pspec in spec.params:
            params.setdefault(pspec["key"], pspec["default"])
        n["params"] = params
        by_id[nid] = n

    # 2) Validate edges + types
    norm_edges = []
    out_ports_by_src = {nid: {p[0]: p[1] for p in lib[n["type"]].outputs}
                        for nid, n in by_id.items()}
    in_ports_by_tgt  = {nid: {p[0]: p[1] for p in lib[n["type"]].inputs}
                        for nid, n in by_id.items()}

    for e in edges:
        src = e.get("from"); tgt = e.get("to")
        if src not in by_id: raise ValueError(f"Edge source missing: {src}")
        if tgt not in by_id: raise ValueError(f"Edge target missing: {tgt}")
        sp = e.get("from_port") or next(iter(out_ports_by_src[src].keys()), None)
        tp = e.get("to_port")   or next(iter(in_ports_by_tgt[tgt].keys()),  None)
        if sp not in out_ports_by_src[src]:
            raise ValueError(f"Node {src} has no output port '{sp}'")
        if tp not in in_ports_by_tgt[tgt]:
            raise ValueError(f"Node {tgt} has no input port '{tp}'")
        src_type = out_ports_by_src[src][sp]
        tgt_type = in_ports_by_tgt[tgt][tp]
        if src_type != tgt_type:
            raise ValueError(
                f"Type mismatch on edge {src}.{sp} → {tgt}.{tp}: "
                f"{src_type.value} ≠ {tgt_type.value}")
        norm_edges.append({"from": src, "to": tgt, "from_port": sp, "to_port": tp})
    graph["edges"] = norm_edges

    # 3) DAG check via Kahn's algorithm; produces topo order as side-effect
    indeg = {nid: 0 for nid in by_id}
    adj:  Dict[str, List[str]] = {nid: [] for nid in by_id}
    for e in norm_edges:
        adj[e["from"]].append(e["to"])
        indeg[e["to"]] += 1
    queue = [nid for nid, d in indeg.items() if d == 0]
    topo  = []
    while queue:
        nid = queue.pop(0)
        topo.append(nid)
        for nxt in adj[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0: queue.append(nxt)
    if len(topo) != len(by_id):
        raise ValueError("Graph contains a cycle — wires must flow one direction.")
    graph["__topo__"] = topo

    # 4) At least one execution sink
    sinks = [n for n in nodes if lib[n["type"]].lane == "execution"]
    if not sinks:
        raise ValueError("Graph needs at least one Execution node (the sink).")

    # 5) Every required input on every node must be wired
    wired = {(e["to"], e["to_port"]) for e in norm_edges}
    for nid, n in by_id.items():
        for in_port, _t in lib[n["type"]].inputs:
            if (nid, in_port) not in wired:
                raise ValueError(f"Node {nid} ({n['type']}) has unwired input '{in_port}'.")

    return graph
