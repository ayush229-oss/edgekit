"""
Starter graphs the builder loads when the user clicks 'Clone EMA cross' etc.
Each template is a complete, runnable graph — drop in, hit Run, see results.

Coordinates `x/y` are React Flow canvas positions so the layout is sane on
first open. Keep them spaced ~280px apart on the x axis.
"""
from __future__ import annotations
from typing import Dict, List, Any


_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id":          "blank",
        "name":        "Blank canvas",
        "description": "Start from scratch.",
        "graph": {
            "name":  "Untitled strategy",
            "nodes": [],
            "edges": [],
        },
    },
    {
        "id":          "ema_cross_starter",
        "name":        "EMA cross (starter)",
        "description": "Classic 20/50 EMA crossover with a session filter. Fast to grok.",
        "graph": {
            "name":  "EMA cross 20/50",
            "nodes": [
                {"id": "s1", "type": "signal.ema_cross",
                 "params": {"fast": 20, "slow": 50, "direction": "both"},
                 "position": {"x":   0, "y": 100}},
                {"id": "f1", "type": "filter.session",
                 "params": {"start_hour": 7, "end_hour": 18},
                 "position": {"x": 280, "y": 100}},
                {"id": "e1", "type": "entry.market",
                 "params": {},
                 "position": {"x": 560, "y": 100}},
                {"id": "r1", "type": "risk.atr_mult",
                 "params": {"period": 14, "mult": 1.5},
                 "position": {"x": 840, "y": 100}},
            ],
            "edges": [
                {"from": "s1", "to": "f1"},
                {"from": "f1", "to": "e1"},
                {"from": "e1", "to": "r1"},
            ],
        },
    },
    {
        "id":          "liquidity_sweep_starter",
        "name":        "Liquidity sweep + FVG",
        "description": "SMC-style: equal levels form, FVG appears, enter market with structure-based SL.",
        "graph": {
            "name":  "Liquidity sweep + FVG",
            "nodes": [
                {"id": "s1", "type": "signal.fvg",
                 "params": {"min_pips": 2, "direction": "both"},
                 "position": {"x":   0, "y": 100}},
                {"id": "f1", "type": "filter.atr_min",
                 "params": {"period": 14, "min_pips": 5},
                 "position": {"x": 280, "y":  40}},
                {"id": "f2", "type": "filter.cooldown",
                 "params": {"bars": 10},
                 "position": {"x": 280, "y": 180}},
                {"id": "e1", "type": "entry.market",
                 "params": {},
                 "position": {"x": 560, "y": 100}},
                {"id": "r1", "type": "risk.below_structure",
                 "params": {"lookback": 8, "buf_pips": 2},
                 "position": {"x": 840, "y": 100}},
            ],
            "edges": [
                {"from": "s1", "to": "f1"},
                {"from": "s1", "to": "f2"},
                {"from": "f1", "to": "e1"},
                {"from": "f2", "to": "e1"},
                {"from": "e1", "to": "r1"},
            ],
        },
    },
    {
        "id":          "rsi_reversion_starter",
        "name":        "RSI mean-reversion",
        "description": "Buy oversold bounces, short overbought rejections. Pullback entry to 20 EMA.",
        "graph": {
            "name":  "RSI mean-reversion",
            "nodes": [
                {"id": "s1", "type": "signal.rsi_threshold",
                 "params": {"period": 14, "oversold": 30, "overbought": 70, "direction": "both"},
                 "position": {"x":   0, "y": 100}},
                {"id": "f1", "type": "filter.session",
                 "params": {"start_hour": 8, "end_hour": 16},
                 "position": {"x": 280, "y": 100}},
                {"id": "e1", "type": "entry.pullback_ema",
                 "params": {"period": 20},
                 "position": {"x": 560, "y": 100}},
                {"id": "r1", "type": "risk.fixed_pips",
                 "params": {"pips": 15},
                 "position": {"x": 840, "y": 100}},
            ],
            "edges": [
                {"from": "s1", "to": "f1"},
                {"from": "f1", "to": "e1"},
                {"from": "e1", "to": "r1"},
            ],
        },
    },
]


def list_templates() -> List[Dict[str, Any]]:
    """Return templates without the full graph (just id/name/description for the picker)."""
    return [{"id": t["id"], "name": t["name"], "description": t["description"]} for t in _TEMPLATES]


def get_template(template_id: str) -> Dict[str, Any]:
    for t in _TEMPLATES:
        if t["id"] == template_id:
            return t["graph"]
    raise KeyError(f"Unknown template: {template_id}")
