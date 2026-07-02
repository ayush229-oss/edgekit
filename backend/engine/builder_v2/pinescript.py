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
from .user_nodes import build_user_node_spec


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

    if t == "indicator.sma":
        return {"value": f"sma_{nid}"}, [f"sma_{nid} = ta.sma(close, {p_('period')})"]

    if t == "indicator.cci":
        return {"value": f"cci_{nid}"}, [f"cci_{nid} = ta.cci(high, low, close, {p_('period')})"]

    if t == "indicator.williams_r":
        return {"value": f"wpr_{nid}"}, [f"wpr_{nid} = ta.wpr({p_('period')})"]

    if t == "indicator.roc":
        return {"value": f"roc_{nid}"}, [f"roc_{nid} = ta.roc(close, {p_('period')})"]

    if t == "indicator.supertrend":
        return ({"value": f"st_{nid}", "direction": f"std_{nid}"},
                [f"[st_{nid}, std_{nid}] = ta.supertrend({p_('mult')}, {p_('period')})"])

    if t == "indicator.order_block":
        # Approximate: track the high/mid/low of the last OB candle
        dir_ = p.get("direction", "bull")
        if dir_ == "bull":
            return ({"high": f"ob_h_{nid}", "mid": f"ob_m_{nid}", "low": f"ob_l_{nid}"},
                    [f"var float ob_h_{nid} = na",
                     f"var float ob_l_{nid} = na",
                     f"ob_m_{nid} = na",
                     f"// Bull OB: last red candle before a strong up move",
                     f"if close[1] < open[1] and close > high[1]",
                     f"    ob_h_{nid} := high[1]",
                     f"    ob_l_{nid} := low[1]",
                     f"ob_m_{nid} := (ob_h_{nid} + ob_l_{nid}) / 2"])
        else:
            return ({"high": f"ob_h_{nid}", "mid": f"ob_m_{nid}", "low": f"ob_l_{nid}"},
                    [f"var float ob_h_{nid} = na",
                     f"var float ob_l_{nid} = na",
                     f"ob_m_{nid} = na",
                     f"// Bear OB: last green candle before a strong down move",
                     f"if close[1] > open[1] and close < low[1]",
                     f"    ob_h_{nid} := high[1]",
                     f"    ob_l_{nid} := low[1]",
                     f"ob_m_{nid} := (ob_h_{nid} + ob_l_{nid}) / 2"])

    if t == "indicator.ichimoku":
        tp = p.get("tenkan_period", 9)
        kp = p.get("kijun_period",  26)
        sp = p.get("senkou_b_period", 52)
        return ({"tenkan": f"ich_t_{nid}", "kijun": f"ich_k_{nid}",
                 "senkou_a": f"ich_sa_{nid}", "senkou_b": f"ich_sb_{nid}"},
                [f"ich_t_{nid}  = math.avg(ta.highest(high, {p_('tenkan_period')}), ta.lowest(low, {p_('tenkan_period')}))",
                 f"ich_k_{nid}  = math.avg(ta.highest(high, {p_('kijun_period')}),  ta.lowest(low, {p_('kijun_period')}))",
                 f"ich_sa_{nid} = math.avg(ich_t_{nid}, ich_k_{nid})",
                 f"ich_sb_{nid} = math.avg(ta.highest(high, {p_('senkou_b_period')}), ta.lowest(low, {p_('senkou_b_period')}))"])

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

    if t == "alpha.order_block":
        # OB: last bearish candle before a bullish impulse (bull OB) or
        # last bullish candle before a bearish impulse (bear OB).
        # We detect: bull OB = prior red candle, current candle closes above prior high by 2+ bars
        # bear OB = prior green candle, current candle closes below prior low by 2+ bars
        bull_ob = "close[1] < open[1] and close > open[1]"   # current bar breaks above prior red candle
        bear_ob = "close[1] > open[1] and close < open[1]"   # current bar breaks below prior green candle
        long_c  = bull_ob if direction in ("long","both")  else "false"
        short_c = bear_ob if direction in ("short","both") else "false"
        return ({"long_cond": f"long_{nid}", "short_cond": f"short_{nid}"},
                [f"// Order Block detection (simplified — tune OB scan params above)",
                 f"long_{nid}  = {long_c}",
                 f"short_{nid} = {short_c}"])

    if t == "alpha.liquidity_sweep":
        # Liquidity sweep: price wicks below recent swing low then closes above (bull),
        # or wicks above recent swing high then closes below (bear).
        period = p.get("period", 10)
        swing_h = f"ta.highest(high[1], {nid}_period)"
        swing_l = f"ta.lowest(low[1],  {nid}_period)"
        long_c  = f"low < {swing_l}[1] and close > {swing_l}[1]" if direction in ("long","both")  else "false"
        short_c = f"high > {swing_h}[1] and close < {swing_h}[1]" if direction in ("short","both") else "false"
        return ({"long_cond": f"long_{nid}", "short_cond": f"short_{nid}"},
                [f"long_{nid}  = {long_c}",
                 f"short_{nid} = {short_c}"])

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


def _exit_lines(exit_nodes: List[str], nodes: Dict[str, Any]) -> List[str]:
    """
    Emit Pine lines for exit-lane nodes.
    These lines are inserted just before the strategy.exit calls so they can
    update entrySLLong/entrySLShort (trail logic).
    """
    lines: List[str] = []
    for nid in exit_nodes:
        node = nodes[nid]
        t    = node["type"]
        rid  = _sanitize(nid)
        p    = node["params"]
        if t == "exit.target_and_trail":
            trail = p.get("trail_mode", "none")
            if trail == "candle":
                lines += [
                    "// Trail: candle — ratchet SL to prior bar low/high while in profit",
                    "if strategy.position_size > 0 and close > strategy.position_avg_price",
                    f"    entrySLLong := math.max(entrySLLong, low[1] - {rid}_trail_buf * syminfo.mintick * 10)",
                    "if strategy.position_size < 0 and close < strategy.position_avg_price",
                    f"    entrySLShort := math.min(entrySLShort, high[1] + {rid}_trail_buf * syminfo.mintick * 10)",
                ]
            elif trail == "atr":
                lines += [
                    "// Trail: ATR-based trail stop",
                    "_atr_trail = ta.atr(14)",
                    "if strategy.position_size > 0 and close > strategy.position_avg_price",
                    f"    entrySLLong := math.max(entrySLLong, close - _atr_trail * {rid}_trail_buf)",
                    "if strategy.position_size < 0 and close < strategy.position_avg_price",
                    f"    entrySLShort := math.min(entrySLShort, close + _atr_trail * {rid}_trail_buf)",
                ]
            elif trail == "pips":
                lines += [
                    "// Trail: fixed-pip trail stop",
                    "if strategy.position_size > 0 and close > strategy.position_avg_price",
                    f"    entrySLLong := math.max(entrySLLong, close - {rid}_trail_buf * syminfo.mintick * 10)",
                    "if strategy.position_size < 0 and close < strategy.position_avg_price",
                    f"    entrySLShort := math.min(entrySLShort, close + {rid}_trail_buf * syminfo.mintick * 10)",
                ]
            elif trail == "swing":
                lines += [
                    "// Trail: swing-based trail (5-bar lookback)",
                    "_swing_trail_l = ta.lowest(low[1], 5)",
                    "_swing_trail_h = ta.highest(high[1], 5)",
                    "if strategy.position_size > 0 and close > strategy.position_avg_price",
                    "    entrySLLong := math.max(entrySLLong, _swing_trail_l)",
                    "if strategy.position_size < 0 and close < strategy.position_avg_price",
                    "    entrySLShort := math.min(entrySLShort, _swing_trail_h)",
                ]
            # trail == "none" → no extra lines needed
    return lines


# ── Top-level generator ───────────────────────────────────────────────────
def generate(graph: Dict[str, Any], mgmt: Optional[Dict[str, Any]] = None) -> str:
    """
    Convert a v2 graph + trade-management config into a Pine Script v5 strategy.
    Returns the full source string.
    """
    # Merge in this graph's own custom Formula Node definitions (same pattern
    # GraphV2Strategy uses) — without this, any strategy built with a custom
    # node crashes here with a bare KeyError the moment it's referenced below,
    # since the global NODE_LIBRARY has no entry for a "user.*" type.
    lib = dict(NODE_LIBRARY)
    for udef in graph.get("user_defs", []):
        spec = build_user_node_spec(udef)
        lib[spec.type] = spec

    graph = validate_graph(graph, node_library=lib)
    mgmt  = mgmt or {}
    topo  = graph["__topo__"]
    nodes = {n["id"]: n for n in graph["nodes"]}
    edges = graph["edges"]
    name  = graph.get("name") or "Edgekit strategy"

    # Bucket nodes by lane
    by_lane: Dict[str, List[str]] = {}
    for nid in topo:
        by_lane.setdefault(lib[nodes[nid]["type"]].lane, []).append(nid)

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
            if lib[nodes[parent]["type"]].lane in ("alpha", "filter"):
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
        spec = lib[node["type"]]
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
        lane = lib[nodes[nid]["type"]].lane
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
        node = nodes[nid]; spec = lib[node["type"]]
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
        "// ────────── Entries (SL anchored at entry bar, not floating) ──────────",
        "var float entrySLLong  = na",
        "var float entrySLShort = na",
        "var int   entryBar     = na",
        "if longCondition and strategy.position_size == 0",
        "    entrySLLong := slPriceLong",
        "    entryBar    := bar_index",
        '    strategy.entry("Long", strategy.long, qty=qtyLong)',
        "if shortCondition and strategy.position_size == 0",
        "    entrySLShort := slPriceShort",
        "    entryBar     := bar_index",
        '    strategy.entry("Short", strategy.short, qty=qtyShort)',
        "",
        "// ────────── Exits ──────────",
        "tpLong  = strategy.position_avg_price + target_r * (strategy.position_avg_price - entrySLLong)",
        "tpShort = strategy.position_avg_price - target_r * (entrySLShort - strategy.position_avg_price)",
        "",
        *_exit_lines(by_lane.get("exit", []), nodes),
        "if strategy.position_size > 0",
        '    strategy.exit("ExitL", from_entry="Long",  stop=entrySLLong,  limit=tpLong)',
        "if strategy.position_size < 0",
        '    strategy.exit("ExitS", from_entry="Short", stop=entrySLShort, limit=tpShort)',
        "",
        "// ────────── Plots ──────────",
        "// SL lines — only visible while a trade is open",
        "plot(strategy.position_size > 0 ? slPriceLong  : na, title='SL (long)',  color=color.red,   style=plot.style_linebr, linewidth=1)",
        "plot(strategy.position_size < 0 ? slPriceShort : na, title='SL (short)', color=color.red,   style=plot.style_linebr, linewidth=1)",
        "// TP lines — only visible while a trade is open",
        "plot(strategy.position_size > 0 ? tpLong  : na, title='TP (long)',  color=color.green, style=plot.style_linebr, linewidth=1)",
        "plot(strategy.position_size < 0 ? tpShort : na, title='TP (short)', color=color.green, style=plot.style_linebr, linewidth=1)",
        "// Entry signals",
        "plotshape(longCondition,  title='Long',  style=shape.triangleup,   location=location.belowbar, color=color.new(color.green, 20), size=size.small)",
        "plotshape(shortCondition, title='Short', style=shape.triangledown, location=location.abovebar, color=color.new(color.red,   20), size=size.small)",
        "",
        "// ────────── Notes ──────────",
        f"// Generated by Edgekit from graph: {name!r}",
        "// Edgekit's runtime trail modes (candle / ATR / swing / pips) are richer than what",
        "// strategy.exit supports natively — TV will give a reasonable approximation. For",
        "// exact behavior, port the strategy to Pine library functions or run it live in Edgekit.",
    ]
    return "\n".join(lines)
