"""
Visual node builder — strategies as data, not code.

A user-built strategy is a JSON graph:
    {
      "name":   "My EMA strategy",
      "nodes":  [{"id": "s1", "type": "signal.ema_cross", "params": {...}}, ...],
      "edges":  [{"from": "s1", "to": "f1"}, ...]
    }

The engine reads the graph, walks every bar, evaluates the signal node,
applies filter nodes (AND), and emits setups using the entry + risk nodes.
Trade management (target R, trail) is handled universally downstream
by the existing simulator.

Public API:
    NODE_LIBRARY               — dict[node_type, NodeSpec]   (introspect for UI)
    GraphStrategy(graph)       — strategy adapter: .detect(df, params) → setups
    validate_graph(graph)      — raises ValueError if structurally invalid
    list_templates() / get_template(id)
"""
from .nodes import NODE_LIBRARY, NodeSpec
from .engine import GraphStrategy
from .validate import validate_graph
from .templates import list_templates, get_template

__all__ = [
    "NODE_LIBRARY", "NodeSpec",
    "GraphStrategy",
    "validate_graph",
    "list_templates", "get_template",
]
