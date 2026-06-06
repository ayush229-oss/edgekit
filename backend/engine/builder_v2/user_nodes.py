"""
User-defined nodes — dynamically registered per-graph run.

Supports all lanes: indicator, alpha, filter, sizing, risk, exit.

Formula namespace per lane
──────────────────────────
All lanes share:
    open, high, low, close, volume  — np.ndarray up to bar i
    <param_name>                    — each declared param by name
    np, pd                          — numpy and pandas
    i                               — current bar index
    pip                             — instrument pip size

Lane-specific extras:
    alpha   — receives named inputs from wired nodes (e.g. `ema_value`, `rsi_value`)
    filter  — receives `insight` (Insight object, may be None) and named inputs
    sizing  — receives `insight` (Insight object)
    risk    — receives `insight` and `entry_px` (float)
    exit    — receives `entry_px`, `sl_px`, `risk_pips` (floats)

Return values per lane:
    indicator   — scalar (number) or np.ndarray (series)
    alpha       — "Bull", "Bear", or None
    filter      — True (pass insight) or False (block)
    sizing      — float: risk fraction (e.g. 0.02 = 2% of equity)
    risk        — float: SL distance in pips (positive number)
    exit        — float: target R multiple (e.g. 3.0)

Security: every formula is AST-scanned before execution. Forbidden:
    imports, exec/eval, dunder access, os/sys/subprocess, file I/O.
    Execution is capped at 5 seconds via a daemon thread.
"""
from __future__ import annotations
import ast
import threading
import numpy as np
import pandas as pd
from typing import Any, Dict, List, Tuple

from .nodes import NodeSpec
from .types import PortType, RunContext, Insight, PortfolioTarget, AdjustedTarget


# ── Safe builtins allowlist ──────────────────────────────────────────────────
_SAFE_BUILTINS: Dict[str, Any] = {
    "abs": abs, "min": min, "max": max, "len": len,
    "sum": sum, "round": round, "int": int, "float": float,
    "bool": bool, "list": list, "range": range,
    "zip": zip, "enumerate": enumerate,
    "True": True, "False": False, "None": None,
}

_SAFE_GLOBALS: Dict[str, Any] = {
    "__builtins__": _SAFE_BUILTINS,
    "np": np,
    "pd": pd,
}

_FORBIDDEN_NODES = (
    ast.Import, ast.ImportFrom,
    ast.Global, ast.Nonlocal,
    ast.Delete,
    ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith,
    ast.Await, ast.YieldFrom,
)

_FORBIDDEN_NAMES = {
    "__import__", "__builtins__", "__class__",
    "exec", "eval", "compile", "open", "input", "print",
    "breakpoint", "globals", "locals", "vars", "dir",
    "getattr", "setattr", "delattr", "hasattr",
    "type", "object", "super",
    "exit", "quit", "help",
    "subprocess", "os", "sys", "io", "pathlib",
}

_FORMULA_TIMEOUT = 5.0


class FormulaSecurityError(ValueError):
    pass


def _check_formula(expr: str) -> None:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise FormulaSecurityError(f"Syntax error: {e}") from e
    for node in ast.walk(tree):
        if isinstance(node, _FORBIDDEN_NODES):
            raise FormulaSecurityError(f"Forbidden construct: {type(node).__name__}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise FormulaSecurityError(f"Forbidden attribute: {node.attr}")
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise FormulaSecurityError(f"Forbidden name: {node.id}")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_NAMES:
                raise FormulaSecurityError(f"Forbidden call: {node.func.id}")


def _eval_safe(expr: str, ns: Dict[str, Any], timeout: float = _FORMULA_TIMEOUT) -> Any:
    result = [None]; error = [None]
    def _run():
        try:
            result[0] = eval(expr, ns)  # noqa: S307
        except Exception as e:
            error[0] = e
    t = threading.Thread(target=_run, daemon=True)
    t.start(); t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"Formula timed out after {timeout}s")
    if error[0] is not None:
        raise error[0]
    return result[0]


def _ohlcv(df: "pd.DataFrame | Any", end: int | None = None) -> Dict[str, np.ndarray]:
    """Extract OHLCV arrays, compatible with both pd.DataFrame and _FrozenDF."""
    sl = slice(None, end)
    n  = end if end is not None else len(df)
    try:
        vol = df["V"].values[sl].astype(float)
    except (KeyError, IndexError, AttributeError):
        vol = np.zeros(n)
    return {
        "open":   df["O"].values[sl].astype(float),
        "high":   df["H"].values[sl].astype(float),
        "low":    df["L"].values[sl].astype(float),
        "close":  df["C"].values[sl].astype(float),
        "volume": vol,
    }


def _ns(arrs: Dict, params: Dict, extras: Dict | None = None) -> Dict[str, Any]:
    ns = dict(_SAFE_GLOBALS)
    ns.update(arrs)
    ns.update(params)
    if extras:
        ns.update(extras)
    return ns


def _to_float(val: Any) -> float:
    if isinstance(val, (np.ndarray, list)):
        return float(val[-1]) if len(val) > 0 else float("nan")
    return float(val)


# ── Port type maps ───────────────────────────────────────────────────────────

_LANE_OUTPUT_TYPE: Dict[str, PortType] = {
    "indicator": PortType.NUMBER,   # or SERIES — detected from output defs
    "alpha":     PortType.INSIGHT,
    "filter":    PortType.INSIGHT,
    "sizing":    PortType.TARGET,
    "risk":      PortType.ADJUSTED,
    "exit":      PortType.ADJUSTED,
}

_LANE_INPUT_TYPES: Dict[str, List[Tuple[str, PortType]]] = {
    "indicator": [],
    "alpha":     [],
    "filter":    [("insight",  PortType.INSIGHT)],
    "sizing":    [("insight",  PortType.INSIGHT)],
    "risk":      [("target",   PortType.TARGET)],      # receives PortfolioTarget from sizing
    "exit":      [("adjusted", PortType.ADJUSTED)],    # receives AdjustedTarget from risk
}


def build_user_node_spec(udef: Dict[str, Any]) -> NodeSpec:
    """
    Build a NodeSpec from a user-defined node dict. Supports all lanes.

    udef keys:
        type         str   — "user.<slug>"
        label        str
        description  str
        lane         str   — indicator | alpha | filter | sizing | risk | exit
        outputs      list  — [{name, type}]   (indicator only; others are auto)
        extra_inputs list  — [{name, type}]   additional wired inputs (alpha)
        params_spec  list  — [{key, label, type, default, min?, max?}]
        formulas     dict  — {output_name: expr}
                              For non-indicator lanes: {"main": expr}
    """
    lane:    str  = udef.get("lane", "indicator")
    node_id: str  = udef["type"]
    params_spec   = udef.get("params_spec", [])
    formulas: Dict[str, str] = udef.get("formulas", {})

    # Pre-scan all formulas
    for port, expr in formulas.items():
        try:
            _check_formula(expr)
        except FormulaSecurityError as e:
            raise ValueError(f"Formula '{port}' failed security check: {e}") from e

    # ── Build port lists ────────────────────────────────────────────────────
    if lane == "indicator":
        out_defs = [(p["name"], PortType(p["type"])) for p in udef.get("outputs", [])]
        in_defs  = [(p["name"], PortType(p["type"])) for p in udef.get("extra_inputs", [])]
    else:
        # Non-indicator lanes auto-declare their standard inputs/outputs
        std_inputs = _LANE_INPUT_TYPES.get(lane, [])
        extra_in   = [(p["name"], PortType(p["type"])) for p in udef.get("extra_inputs", [])]
        in_defs    = std_inputs + extra_in
        out_type   = _LANE_OUTPUT_TYPE.get(lane, PortType.NUMBER)
        out_defs   = [("insight" if lane in ("alpha", "filter") else
                       "target"  if lane == "sizing" else
                       "adjusted", out_type)]

    # ── prepare_fn — cache OHLCV-based series for indicator lane ────────────
    def prepare(df: pd.DataFrame, ctx: RunContext, params: Dict) -> None:
        if lane != "indicator":
            return
        arrs = _ohlcv(df)
        for port_name, port_type in out_defs:
            if port_type != PortType.SERIES:
                continue
            key  = f"{node_id}|{port_name}"
            expr = formulas.get(port_name, "close")
            try:
                result = _eval_safe(expr, _ns(arrs, params))
                if isinstance(result, pd.Series):
                    result = result.values
                ctx.cache[key] = np.asarray(result, dtype=float)
            except Exception:
                ctx.cache[key] = np.full(len(df), np.nan)

    # ── eval_fn ─────────────────────────────────────────────────────────────
    def eval_fn(df: pd.DataFrame, i: int, ctx: RunContext, inputs: Dict, params: Dict) -> Dict:
        arrs   = _ohlcv(df, i + 1)
        extras = {"i": i, "pip": ctx.pip}
        # Expose wired numeric inputs by name
        for name, val in inputs.items():
            if isinstance(val, (int, float, np.floating, np.integer)):
                extras[name] = float(val)
            elif isinstance(val, np.ndarray):
                extras[name] = val
        ns = _ns(arrs, params, extras)

        # ── INDICATOR ───────────────────────────────────────────────────────
        if lane == "indicator":
            out: Dict[str, Any] = {}
            for port_name, port_type in out_defs:
                if port_type == PortType.SERIES:
                    arr = ctx.cache.get(f"{node_id}|{port_name}")
                    out[port_name] = float(arr[i]) if arr is not None and i < len(arr) else float("nan")
                else:
                    expr = formulas.get(port_name, "close[-1]")
                    try:
                        out[port_name] = _to_float(_eval_safe(expr, ns))
                    except Exception:
                        out[port_name] = float("nan")
            return out

        # ── ALPHA ────────────────────────────────────────────────────────────
        if lane == "alpha":
            expr = formulas.get("main", "None")
            try:
                result = _eval_safe(expr, ns)
                if result in ("Bull", "Bear"):
                    return {"insight": Insight(direction=result, bar_idx=i)}
            except Exception:
                pass
            return {"insight": None}

        # ── FILTER ───────────────────────────────────────────────────────────
        if lane == "filter":
            sig  = inputs.get("insight")
            if sig is None:
                return {"insight": None}
            # Add insight metadata to namespace
            ns["direction"] = sig.direction
            ns["confidence"] = sig.confidence
            expr = formulas.get("main", "True")
            try:
                result = _eval_safe(expr, ns)
                return {"insight": sig if bool(result) else None}
            except Exception:
                return {"insight": sig}   # fail-open: pass the signal through

        # ── SIZING ───────────────────────────────────────────────────────────
        if lane == "sizing":
            sig = inputs.get("insight")
            if sig is None:
                return {"target": None}
            ns["direction"] = sig.direction
            ns["confidence"] = sig.confidence
            expr = formulas.get("main", "0.01")
            try:
                qty = max(0.0, min(1.0, float(_eval_safe(expr, ns))))
            except Exception:
                qty = 0.01
            entry_px = float(df["C"].values[i])
            return {"target": PortfolioTarget(insight=sig, qty=qty, entry_px=entry_px)}

        # ── RISK ─────────────────────────────────────────────────────────────
        # Receives a PortfolioTarget (from sizing); returns AdjustedTarget with SL set.
        # Formula returns SL distance in pips.
        # Extras: entry_px, direction, qty
        if lane == "risk":
            tgt = inputs.get("target")
            if tgt is None:
                return {"adjusted": None}
            entry_px  = float(tgt.entry_px)
            direction = tgt.insight.direction
            ns["entry_px"]  = entry_px
            ns["direction"] = direction
            ns["qty"]       = float(tgt.qty)
            expr = formulas.get("main", "10.0")
            try:
                sl_pips = max(1.0, float(_eval_safe(expr, ns)))
            except Exception:
                sl_pips = 10.0
            sl_px = (entry_px - sl_pips * ctx.pip if direction == "Bull"
                     else entry_px + sl_pips * ctx.pip)
            return {"adjusted": AdjustedTarget(target=tgt, sl_px=sl_px)}

        # ── EXIT ─────────────────────────────────────────────────────────────
        # Receives an AdjustedTarget (from risk); returns AdjustedTarget with target_r set.
        # Formula returns target R multiple.
        # Extras: entry_px, sl_px, risk_pips, direction
        if lane == "exit":
            adj = inputs.get("adjusted")
            if adj is None:
                return {"adjusted": None}
            entry_px  = float(adj.target.entry_px)
            direction = adj.target.insight.direction
            ns["entry_px"]   = entry_px
            ns["sl_px"]      = float(adj.sl_px)
            ns["risk_pips"]  = float(adj.risk) / ctx.pip if ctx.pip > 0 else 0.0
            ns["direction"]  = direction
            expr = formulas.get("main", "3.0")
            try:
                target_r = max(0.5, float(_eval_safe(expr, ns)))
            except Exception:
                target_r = 3.0
            adj.target_r = target_r
            return {"adjusted": adj}

        return {}

    return NodeSpec(
        type=node_id,
        lane=lane,
        label=udef.get("label", node_id),
        description=udef.get("description", f"User-defined {lane} node"),
        inputs=in_defs,
        outputs=out_defs,
        params=params_spec,
        prepare_fn=prepare,
        eval_fn=eval_fn,
    )
