"""
Pine Script v5 code generator.

Walks a validated v2 graph and emits a standalone TradingView strategy
script that mirrors the Edgekit graph's behavior as closely as Pine allows.

Strategy:
  1. Collect all tunable params as `input.*` declarations so users can re-tune in TV
  2. Emit indicator definitions in topological order
  3. Build LONG/SHORT condition expressions from Alpha + Filter chain
  4. Generate strategy.entry / strategy.exit calls for sizing+risk+exit

Caveats (called out in the generated script as comments):
  - Pine has limited support for some custom logic (e.g. stacked exits — we
    flatten into a single strategy.exit call with the most aggressive params)
  - Stateful filters like cooldown use Pine's `var` counter pattern
  - Cross-bar lookups (FVG, engulfing) use bar references (close[2], etc.)
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

from .validate import validate_graph
from .nodes    import NODE_LIBRARY


def _sanitize(node_id: str) -> str:
    return node_id.replace("-", "_").replace(".", "_")


def _input_decl(node_id: str, p: Dict[str, Any], spec_param: Dict[str, Any]) -> str:
    """Emit a single `input.*` line for a node parameter."""
    var  = f"{_sanitize(node_id)}_{spec_param['key']}"
    title = f'"{spec_param["label"]} ({_sanitize(node_id)})"'
    t = spec_param["type"]
    default = p.get(spec_param["key"], spec_param["default"])
    if t == "int":
        mn = spec_param.get("min");  mx = spec_param.get("max")
        rng = f", minval={int(mn)}" if mn is not None else ""
        rng += f", maxval={int(mx)}" if mx is not None else ""
        return f"{var} = input.int({int(default)}, {title}{rng})"
    if t == "float":
        mn = spec_param.get("min");  mx = spec_param.get("max"); step = spec_param.get("step")
        rng = f", minval={float(mn)}" if mn is not None else ""
        rng += f", maxval={float(mx)}" if mx is not None else ""
        rng += f", step={float(step)}" if step is not None else ""
        return f"{var} = input.float({float(default)}, {title}{rng})"
    if t == "select":
        opts = spec_param.get("options") or []
        opts_str = ", ".join(f'"{o}"' for o in opts)
        return f'{var} = input.string("{default}", {title}, options=[{opts_str}])'
    if t == "bool":
        return f"{var} = input.bool({str(bool(default)).lower()}, {title})"
    # string fallback
    return f'{var} = input.string("{default}", {title})'


# ── Per-node Pine emitters ────────────────────────────────────────────────
# Each returns (var_outputs, lines).
# var_outputs maps the node's logical port name -> the Pine variable holding it.
# lines is the body lines to insert into the indicator section.

def _emit_indicator(node: dict, in_vars: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    nid  = _sanitize(node["id"])
    t    = node["type"]
    p    = node["params"]
    p_   = lambda k: f"{nid}_{k}"     # generated input variable name

    if t == "indicator.ema":
        return {"value": f"ema_{nid}"}, [f"ema_{nid} = ta.ema(close, {p_('period')})"]
    if t == "indicator.atr":
        return {"value": f"atr_{nid}"}, [f"atr_{nid} = ta.atr({p_('period')})"]
    if t == "indicator.rsi":
        return {"value": f"rsi_{nid}"}, [f"rsi_{nid} = ta.rsi(close, {p_('period')})"]
    if t == "indicator.donchian":
        return ({"upper": f"dch_u_{nid}", "lower": f"dch_l_{nid}"},
                [f"dch_u_{nid} = ta.highest(high[1], {p_('period')})",
                 f"dch_l_{nid} = ta.lowest(low[1],  {p_('period')})"])
    if t == "indicator.bollinger":
        return ({"upper": f"bb_u_{nid}", "middle": f"bb_m_{nid}", "lower": f"bb_l_{nid}"},
                [f"[bb_m_{nid}, bb_u_{nid}, bb_l_{nid}] = ta.bb(close, {p_('period')}, {p_('mult')})"])
    if t == "indicator.macd":
        return ({"macd": f"mac_m_{nid}", "signal": f"mac_s_{nid}", "histogram": f"mac_h_{nid}"},
                [f"[mac_m_{nid}, mac_s_{nid}, mac_h_{nid}] = ta.macd(close, {p_('fast')}, {p_('slow')}, {p_('signal')})"])
    if t == "indicator.adx":
        return ({"value": f"adx_{nid}"},
                [f"[_diplus_{nid}, _diminus_{nid}, adx_{nid}] = ta.dmi({p_('period')}, {p_('period')})"])
    if t == "indicator.stochastic":
        return ({"k": f"stk_{nid}", "d": f"std_{nid}"},
                [f"stk_{nid} = ta.stoch(close, high, low, {p_('k_period')})",
                 f"std_{nid} = ta.sma(stk_{nid}, {p_('d_period')})"])
    if t == "indicator.vwap":
        return {"value": f"vwap_{nid}"}, [f"vwap_{nid} = ta.vwap"]
    if t == "indicator.swing_high":
        return {"value": f"sh_{nid}"}, [f"sh_{nid} = ta.highest(high[1], {p_('period')})"]
    if t == "indicator.swing_low":
        return {"value": f"sl_{nid}"}, [f"sl_{nid} = ta.lowest(low[1], {p_('period')})"]
    if t == "indicator.price":
        src = p.get("source", "close")
        return {"value": src}, []

    return {}, [f"// TODO: indicator '{t}' has no Pine translator yet"]


def _emit_alpha(node: dict, in_vars: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    nid = _sanitize(node["id"])
    t   = node["type"]
    p   = node["params"]
    direction = p.get("direction", "both")

    if t == "alpha.crossover":
        a, b = in_vars.get("a", "na"), in_vars.get("b", "na")
        long_c  = f"ta.crossover({a}, {b})"  if direction in ("long","both")  else "false"
        short_c = f"ta.crossunder({a}, {b})" if direction in ("short","both") else "false"
        return ({"long_cond": f"long_{nid}", "short_cond": f"short_{nid}"},
                [f"long_{nid}  = {long_c}",
                 f"short_{nid} = {short_c}"])

    if t == "alpha.channel_break":
        u, l = in_vars.get("upper", "na"), in_vars.get("lower", "na")
        long_c  = f"ta.crossover(close, {u})"  if direction in ("long","both")  else "false"
        short_c = f"ta.crossunder(close, {l})" if direction in ("short","both") else "false"
        return ({"long_cond": f"long_{nid}", "short_cond": f"short_{nid}"},
                [f"long_{nid}  = {long_c}",
                 f"short_{nid} = {short_c}"])

    if t == "alpha.threshold":
        v = in_vars.get("value", "na")
        ll = f"{nid}_long_level"; sl = f"{nid}_short_level"
        long_c  = f"ta.crossover({v}, {ll})"  if direction in ("long","both")  else "false"
        short_c = f"ta.crossunder({v}, {sl})" if direction in ("short","both") else "false"
        return ({"long_cond": f"long_{nid}", "short_cond": f"short_{nid}"},
                [f"long_{nid}  = {long_c}",
                 f"short_{nid} = {short_c}"])

    if t == "alpha.engulfing":
        long_c  = "close[1] < open[1] and close > open and close >= open[1] and open <= close[1]" if direction in ("long","both") else "false"
        short_c = "close[1] > open[1] and close < open and close <= open[1] and open >= close[1]" if direction in ("short","both") else "false"
        return ({"long_cond": f"long_{nid}", "short_cond": f"short_{nid}"},
                [f"long_{nid}  = {long_c}",
                 f"short_{nid} = {short_c}"])

    if t == "alpha.fvg":
        # 3-bar imbalance: low[0] - high[2] >= N*pip (bull) / low[2] - high[0] >= N*pip (bear)
        minpx = f"{nid}_min_pips * syminfo.mintick * 10"
        long_c  = f"(low - high[2]) >= {minpx}" if direction in ("long","both") else "false"
        short_c = f"(low[2] - high) >= {minpx}" if direction in ("short","both") else "false"
        return ({"long_cond": f"long_{nid}", "short_cond": f"short_{nid}"},
                [f"long_{nid}  = {long_c}",
                 f"short_{nid} = {short_c}"])

    if t == "alpha.combine_and":
        # Pine doesn't pass insights — we AND the long_cond and short_cond from the two parents
        # in_vars carries strings like "long_<parent>" / "short_<parent>" — but the way the graph
        # wires, both a and b feed an "insight" port. We need to look up the upstream node's
        # long/short condition names. Best-effort: the wiring passes "insight" naming.
        a = in_vars.get("a", "")
        b = in_vars.get("b", "")
        return ({"long_cond": f"long_{nid}", "short_cond": f"short_{nid}"},
                [f"long_{nid}  = ({a.replace('insight_','long_')}) and ({b.replace('insight_','long_')})",
                 f"short_{nid} = ({a.replace('insight_','short_')}) and ({b.replace('insight_','short_')})"])

    if t == "alpha.combine_or":
        a = in_vars.get("a", "");  b = in_vars.get("b", "")
        return ({"long_cond": f"long_{nid}", "short_cond": f"short_{nid}"},
                [f"long_{nid}  = ({a.replace('insight_','long_')}) or ({b.replace('insight_','long_')})",
                 f"short_{nid} = ({a.replace('insight_','short_')}) or ({b.replace('insight_','short_')})"])

    return {}, [f"// TODO: alpha '{t}' has no Pine translator yet"]


def _emit_filter(node: dict, in_vars: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    nid = _sanitize(node["id"])
    t   = node["type"]

    if t == "filter.session":
        gate = f"(hour >= {nid}_start_hour and hour < {nid}_end_hour)"
    elif t == "filter.threshold":
        v = in_vars.get("value", "na")
        gate = f"({v} >= {nid}_min and {v} <= {nid}_max)"
    elif t == "filter.cooldown":
        # Counter-style state
        return ({"long_cond": f"long_{nid}", "short_cond": f"short_{nid}"}, [
            f"var int last_fire_{nid} = -10000",
            f"_cd_pass_{nid} = (bar_index - last_fire_{nid}) >= {nid}_bars",
            f"long_{nid}  = ({in_vars.get('long_cond',  'false')}) and _cd_pass_{nid}",
            f"short_{nid} = ({in_vars.get('short_cond', 'false')}) and _cd_pass_{nid}",
            f"if long_{nid} or short_{nid}",
            f"    last_fire_{nid} := bar_index",
        ])
    else:
        return {}, [f"// TODO: filter '{t}' has no Pine translator yet"]

    return ({"long_cond": f"long_{nid}", "short_cond": f"short_{nid}"},
            [f"long_{nid}  = ({in_vars.get('long_cond',  'false')}) and {gate}",
             f"short_{nid} = ({in_vars.get('short_cond', 'false')}) and {gate}"])


# ── Top-level generator ───────────────────────────────────────────────────
def generate(graph: Dict[str, Any], mgmt: Optional[Dict[str, Any]] = None) -> str:
    """
    Convert a v2 graph + trade-management config into a Pine Script v5 strategy.
    Returns the full source string.
    """
    graph = validate_graph(graph)
    mgmt  = mgmt or {}
    topo  = graph["__topo__"]
    nodes = {n["id"]: n for n in graph["nodes"]}
    edges = graph["edges"]
    name  = graph.get("name") or "Edgekit strategy"

    # Bucket nodes by lane
    by_lane: Dict[str, List[str]] = {}
    for nid in topo:
        by_lane.setdefault(NODE_LIBRARY[nodes[nid]["type"]].lane, []).append(nid)

    # Resolve incoming wires: per node, {input_port_name: parent_pine_var_name}
    # We compute these incrementally as we walk topo order.
    out_vars: Dict[Tuple[str, str], str] = {}     # (node_id, port_name) -> pine var
    cond_vars: Dict[str, Tuple[str, str]] = {}    # for alpha+filter: node_id -> (long_var, short_var)

    indicator_lines: List[str] = []
    alpha_lines:     List[str] = []
    filter_lines:    List[str] = []

    def collect_inputs(nid: str) -> Dict[str, str]:
        """For node `nid`, return {input_port: parent's pine var name}."""
        inputs: Dict[str, str] = {}
        for e in edges:
            if e["to"] != nid: continue
            parent = e["from"]; pport = e["from_port"]; tport = e["to_port"]
            # For alpha/filter chained-input edges, the parent emits long/short conds
            if NODE_LIBRARY[nodes[parent]["type"]].lane in ("alpha", "filter"):
                # Pass a "tagged" name so combine nodes can swap long/short
                lv, sv = cond_vars.get(parent, ("false", "false"))
                inputs[tport] = f"insight_{lv}|{sv}"
                inputs["__" + tport + "_long"]  = lv
                inputs["__" + tport + "_short"] = sv
            else:
                inputs[tport] = out_vars.get((parent, pport), "na")
        return inputs

    for nid in topo:
        node = nodes[nid]
        spec = NODE_LIBRARY[node["type"]]
        in_vars = collect_inputs(nid)

        if spec.lane == "indicator":
            outs, lines = _emit_indicator(node, in_vars)
            indicator_lines.extend(lines)
            for port, var in outs.items():
                out_vars[(nid, port)] = var

        elif spec.lane == "alpha":
            outs, lines = _emit_alpha(node, in_vars)
            alpha_lines.extend(lines)
            if "long_cond" in outs and "short_cond" in outs:
                cond_vars[nid] = (outs["long_cond"], outs["short_cond"])

        elif spec.lane == "filter":
            # Pull parent's long/short conds from in_vars helpers
            for k in list(in_vars.keys()):
                if k.startswith("__"): continue
                # provide long_cond / short_cond aliases
                long_alias  = in_vars.get(f"__{k}_long",  "false")
                short_alias = in_vars.get(f"__{k}_short", "false")
                in_vars["long_cond"]  = long_alias
                in_vars["short_cond"] = short_alias
            outs, lines = _emit_filter(node, in_vars)
            filter_lines.extend(lines)
            if "long_cond" in outs and "short_cond" in outs:
                cond_vars[nid] = (outs["long_cond"], outs["short_cond"])

    # Determine the final long/short conditions — last alpha/filter in chain (topo-wise)
    final_long  = "false"
    final_short = "false"
    for nid in topo:
        lane = NODE_LIBRARY[nodes[nid]["type"]].lane
        if lane in ("alpha", "filter") and nid in cond_vars:
            final_long, final_short = cond_vars[nid]

    # Risk node — find first SL recipe
    sl_expr_long  = "close - 30 * syminfo.mintick * 10"
    sl_expr_short = "close + 30 * syminfo.mintick * 10"
    sl_comment    = "// (no Risk node — defaulting to 30 pips)"
    for nid in by_lane.get("risk", []):
        node = nodes[nid]; t = node["type"]; rid = _sanitize(nid)
        if t == "risk.fixed_pips":
            sl_expr_long  = f"close - {rid}_pips * syminfo.mintick * 10"
            sl_expr_short = f"close + {rid}_pips * syminfo.mintick * 10"
            sl_comment    = "// Fixed-pips SL"
        elif t == "risk.atr_stop":
            # Find the wired ATR var
            atr_src = "ta.atr(14)"
            for e in edges:
                if e["to"] == nid and e["to_port"] == "atr":
                    atr_src = out_vars.get((e["from"], e["from_port"]), "ta.atr(14)")
            sl_expr_long  = f"close - {atr_src} * {rid}_mult"
            sl_expr_short = f"close + {atr_src} * {rid}_mult"
            sl_comment    = "// ATR-based SL"
        elif t == "risk.structure_stop":
            swing_src = "ta.lowest(low[1], 10)"
            for e in edges:
                if e["to"] == nid and e["to_port"] == "swing":
                    swing_src = out_vars.get((e["from"], e["from_port"]), swing_src)
            sl_expr_long  = f"{swing_src} - {rid}_buf_pips * syminfo.mintick * 10"
            sl_expr_short = f"{swing_src} + {rid}_buf_pips * syminfo.mintick * 10"
            sl_comment    = "// Structure SL (recent swing)"
        break  # first risk node wins

    # Trade management from request body
    target_r       = float(mgmt.get("target_r")         or 3.0)
    close_pct      = float(mgmt.get("target_close_pct") or 1.0)
    trail_mode     = mgmt.get("trail_mode") or "none"

    # ── Assemble the script ──────────────────────────────────────────────
    inputs_block: List[str] = []
    for nid in topo:
        node = nodes[nid]; spec = NODE_LIBRARY[node["type"]]
        for sp in spec.params:
            inputs_block.append(_input_decl(nid, node["params"], sp))

    # Trade-management inputs at the top so they're easy to find in TV
    tm_inputs = [
        f'target_r = input.float({target_r}, "Target R:R", minval=1, maxval=10, step=0.5)',
        f'close_pct = input.float({close_pct}, "Close % at target", minval=0, maxval=1, step=0.05)',
        f'trail_mode = input.string("{trail_mode}", "Trail mode", options=["none","candle","atr","pips","swing"])',
        f'risk_pct = input.float(1.0, "Risk per trade (%)", minval=0.1, maxval=10, step=0.1)',
    ]

    lines: List[str] = [
        "//@version=6",
        f'strategy("{name}", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=10, commission_type=strategy.commission.percent, commission_value=0.05, pyramiding=0)',
        "",
        "// ────────── Inputs (tune these in the TradingView dialog) ──────────",
        *tm_inputs,
        *inputs_block,
        "",
        "// ────────── Indicators ──────────",
        *indicator_lines,
        "",
        "// ────────── Alpha (long/short conditions) ──────────",
        *alpha_lines,
        "",
        "// ────────── Filters ──────────",
        *filter_lines,
        "",
        "// ────────── Final conditions ──────────",
        f"longCondition  = {final_long}",
        f"shortCondition = {final_short}",
        "",
        f"// ────────── Risk (SL) ──────────",
        f"{sl_comment}",
        f"slPriceLong  = {sl_expr_long}",
        f"slPriceShort = {sl_expr_short}",
        "",
        "// ────────── Sizing ──────────",
        "// Risk-% sizing: position size = (equity * risk%) / SL distance",
        "qtyLong  = (strategy.equity * risk_pct / 100) / math.max(close - slPriceLong, syminfo.mintick)",
        "qtyShort = (strategy.equity * risk_pct / 100) / math.max(slPriceShort - close, syminfo.mintick)",
        "",
        "// ────────── Entries ──────────",
        "if longCondition and strategy.position_size == 0",
        '    strategy.entry("Long", strategy.long, qty=qtyLong)',
        "if shortCondition and strategy.position_size == 0",
        '    strategy.entry("Short", strategy.short, qty=qtyShort)',
        "",
        "// ────────── Exits ──────────",
        "// Target = entry + target_r * (entry - SL).  Trailing not perfectly mirrored — Pine uses",
        "// trail_offset based on points; the Edgekit candle/atr/swing trail modes need manual",
        "// fine-tuning after import. Use trail_mode input to choose; default is plain TP+SL.",
        "tpLong  = strategy.position_avg_price + target_r * (strategy.position_avg_price - slPriceLong)",
        "tpShort = strategy.position_avg_price - target_r * (slPriceShort - strategy.position_avg_price)",
        "",
        "if strategy.position_size > 0",
        '    strategy.exit("ExitL", from_entry="Long",  stop=slPriceLong,  limit=tpLong)',
        "if strategy.position_size < 0",
        '    strategy.exit("ExitS", from_entry="Short", stop=slPriceShort, limit=tpShort)',
        "",
        "// ────────── Plots ──────────",
        "plot(slPriceLong,  title='SL (long)',  color=color.red,    style=plot.style_linebr)",
        "plot(slPriceShort, title='SL (short)', color=color.red,    style=plot.style_linebr)",
        "plotshape(longCondition,  title='Long',  style=shape.triangleup,   location=location.belowbar, color=color.green)",
        "plotshape(shortCondition, title='Short', style=shape.triangledown, location=location.abovebar, color=color.red)",
        "",
        "// ────────── Notes ──────────",
        f"// Generated by Edgekit from graph: {name!r}",
        "// Edgekit's runtime trail modes (candle / ATR / swing / pips) are richer than what",
        "// strategy.exit supports natively — TV will give a reasonable approximation. For",
        "// exact behavior, port the strategy to Pine library functions or run it live in Edgekit.",
    ]
    return "\n".join(lines)
