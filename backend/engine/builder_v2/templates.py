"""
v2 starter templates.

Each one is a complete 5-lane graph — Universe → Indicator(s) → Alpha
→ Sizing → Risk → Exit → Execution. These both demonstrate the model
and serve as the user's first-run starting points.
"""
from __future__ import annotations
from typing import Any, Dict, List


_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id":   "donchian_breakout_v2",
        "name": "Donchian breakout (canonical)",
        "description": "Classic trend-following: 20-bar channel break, ATR-target sizing, 2×ATR stop, trailing exit.",
        "graph": {
            "name":  "Donchian breakout",
            "nodes": [
                {"id": "u1",  "type": "universe.single_asset",
                 "params": {"ticker": "XAUUSD", "timeframe": "M15"},
                 "position": {"x":    0, "y":  60}},
                {"id": "d1",  "type": "indicator.donchian",
                 "params": {"period": 20},
                 "position": {"x":  260, "y":  20}},
                {"id": "a1",  "type": "indicator.atr",
                 "params": {"period": 14},
                 "position": {"x":  260, "y": 180}},
                {"id": "al1", "type": "alpha.channel_break",
                 "params": {"direction": "both"},
                 "position": {"x":  540, "y":  20}},
                {"id": "sz1", "type": "sizing.atr_target",
                 "params": {"risk_pct": 1.0, "atr_mult": 2.0},
                 "position": {"x":  820, "y": 100}},
                {"id": "rk1", "type": "risk.atr_stop",
                 "params": {"mult": 2.0},
                 "position": {"x": 1100, "y": 100}},
                {"id": "ex1", "type": "exit.target_and_trail",
                 "params": {"target_r": 3.0, "close_pct": 0.5,
                            "trail_mode": "candle", "trail_buf": 1.0},
                 "position": {"x": 1380, "y": 100}},
                {"id": "xc1", "type": "execution.market",
                 "params": {"expiry_bars": 20},
                 "position": {"x": 1660, "y": 100}},
            ],
            "edges": [
                {"from": "d1",  "from_port": "upper",    "to": "al1", "to_port": "upper"},
                {"from": "d1",  "from_port": "lower",    "to": "al1", "to_port": "lower"},
                {"from": "al1", "from_port": "insight",  "to": "sz1", "to_port": "insight"},
                {"from": "a1",  "from_port": "value",    "to": "sz1", "to_port": "atr"},
                {"from": "sz1", "from_port": "target",   "to": "rk1", "to_port": "target"},
                {"from": "a1",  "from_port": "value",    "to": "rk1", "to_port": "atr"},
                {"from": "rk1", "from_port": "adjusted", "to": "ex1", "to_port": "adjusted"},
                {"from": "ex1", "from_port": "adjusted", "to": "xc1", "to_port": "adjusted"},
            ],
        },
    },
    {
        "id":   "turtle_system_1",
        "name": "Turtle Trading (System 1)",
        "description": "Curtis Faith / Richard Dennis — 20-day Donchian breakout entry, 20-period ATR sizing (risk 1% per N), 2N ATR stop. The textbook trend-following system.",
        "graph": {
            "name":  "Turtle System 1 (20-day)",
            "nodes": [
                {"id": "u1",  "type": "universe.single_asset",
                 "params": {"ticker": "XAUUSD", "timeframe": "H1"},
                 "position": {"x":    0, "y": 180}},
                {"id": "d1",  "type": "indicator.donchian",
                 "params": {"period": 20},
                 "position": {"x":  260, "y":  40}},
                {"id": "a1",  "type": "indicator.atr",
                 "params": {"period": 20},
                 "position": {"x":  260, "y": 320}},
                {"id": "al1", "type": "alpha.channel_break",
                 "params": {"direction": "both"},
                 "position": {"x":  540, "y": 180}},
                {"id": "sz1", "type": "sizing.atr_target",
                 "params": {"risk_pct": 1.0, "atr_mult": 2.0},
                 "position": {"x":  820, "y": 180}},
                {"id": "rk1", "type": "risk.atr_stop",
                 "params": {"mult": 2.0},
                 "position": {"x": 1100, "y": 180}},
                # Turtle exit is 10-day opposite-channel break — we approximate
                # via high target_r + candle trail (rides until reversal).
                {"id": "ex1", "type": "exit.target_and_trail",
                 "params": {"target_r": 8.0, "close_pct": 0.0,
                            "trail_mode": "candle", "trail_buf": 1.0},
                 "position": {"x": 1380, "y": 180}},
                {"id": "xc1", "type": "execution.market",
                 "params": {"expiry_bars": 3},
                 "position": {"x": 1660, "y": 180}},
            ],
            "edges": [
                {"from": "d1",  "from_port": "upper",    "to": "al1", "to_port": "upper"},
                {"from": "d1",  "from_port": "lower",    "to": "al1", "to_port": "lower"},
                {"from": "al1", "from_port": "insight",  "to": "sz1", "to_port": "insight"},
                {"from": "a1",  "from_port": "value",    "to": "sz1", "to_port": "atr"},
                {"from": "sz1", "from_port": "target",   "to": "rk1", "to_port": "target"},
                {"from": "a1",  "from_port": "value",    "to": "rk1", "to_port": "atr"},
                {"from": "rk1", "from_port": "adjusted", "to": "ex1", "to_port": "adjusted"},
                {"from": "ex1", "from_port": "adjusted", "to": "xc1", "to_port": "adjusted"},
            ],
        },
    },
    {
        "id":   "livermore_pivot",
        "name": "Livermore Pivot break",
        "description": "Jesse Livermore's pivotal point method (Reminiscences of a Stock Operator) — buy on close above the recent N-bar high, sell on close below the N-bar low. Tape reading in node form.",
        "graph": {
            "name":  "Livermore Pivot",
            "nodes": [
                {"id": "u1",  "type": "universe.single_asset",
                 "params": {"ticker": "XAUUSD", "timeframe": "H1"},
                 "position": {"x":    0, "y": 240}},
                # Wires representing close, the swing high (resistance), swing low (support)
                {"id": "px",  "type": "indicator.price",
                 "params": {"source": "close"},
                 "position": {"x":  260, "y": 240}},
                {"id": "shi", "type": "indicator.swing_high",
                 "params": {"period": 20},
                 "position": {"x":  260, "y":  60}},
                {"id": "slo", "type": "indicator.swing_low",
                 "params": {"period": 20},
                 "position": {"x":  260, "y": 420}},
                # Two alphas: long break (close crosses above swing high) +
                #             short break (close crosses below swing low).
                {"id": "alL", "type": "alpha.crossover",
                 "params": {"direction": "long"},
                 "position": {"x":  540, "y": 100}},
                {"id": "alS", "type": "alpha.crossover",
                 "params": {"direction": "short"},
                 "position": {"x":  540, "y": 380}},
                {"id": "or1", "type": "alpha.combine_or",
                 "params": {},
                 "position": {"x":  820, "y": 240}},
                # ATR for sizing + stop
                {"id": "atr", "type": "indicator.atr",
                 "params": {"period": 14},
                 "position": {"x":  820, "y": 440}},
                {"id": "sz1", "type": "sizing.atr_target",
                 "params": {"risk_pct": 0.75, "atr_mult": 1.5},
                 "position": {"x": 1100, "y": 240}},
                {"id": "rk1", "type": "risk.atr_stop",
                 "params": {"mult": 1.5},
                 "position": {"x": 1380, "y": 240}},
                {"id": "ex1", "type": "exit.target_and_trail",
                 "params": {"target_r": 3.0, "close_pct": 0.5,
                            "trail_mode": "candle", "trail_buf": 2.0},
                 "position": {"x": 1660, "y": 240}},
                {"id": "xc1", "type": "execution.market",
                 "params": {"expiry_bars": 3},
                 "position": {"x": 1940, "y": 240}},
            ],
            "edges": [
                # close crosses above swing_high → Bull
                {"from": "px",  "from_port": "value",    "to": "alL", "to_port": "a"},
                {"from": "shi", "from_port": "value",    "to": "alL", "to_port": "b"},
                # close crosses below swing_low → Bear
                {"from": "px",  "from_port": "value",    "to": "alS", "to_port": "a"},
                {"from": "slo", "from_port": "value",    "to": "alS", "to_port": "b"},
                # OR the two
                {"from": "alL", "from_port": "insight",  "to": "or1", "to_port": "a"},
                {"from": "alS", "from_port": "insight",  "to": "or1", "to_port": "b"},
                # Pipe through sizing / risk / exit
                {"from": "or1", "from_port": "insight",  "to": "sz1", "to_port": "insight"},
                {"from": "atr", "from_port": "value",    "to": "sz1", "to_port": "atr"},
                {"from": "sz1", "from_port": "target",   "to": "rk1", "to_port": "target"},
                {"from": "atr", "from_port": "value",    "to": "rk1", "to_port": "atr"},
                {"from": "rk1", "from_port": "adjusted", "to": "ex1", "to_port": "adjusted"},
                {"from": "ex1", "from_port": "adjusted", "to": "xc1", "to_port": "adjusted"},
            ],
        },
    },
    {
        "id":   "ichimoku_tk_cross",
        "name": "Ichimoku TK Cross",
        "description": "Karen Peloille / classical Ichimoku — Tenkan crosses Kijun in the direction of the trade. The simplest Ichimoku entry; you can add Kumo (cloud) filters to tighten.",
        "graph": {
            "name":  "Ichimoku TK Cross",
            "nodes": [
                {"id": "u1",  "type": "universe.single_asset",
                 "params": {"ticker": "XAUUSD", "timeframe": "H1"},
                 "position": {"x":    0, "y": 180}},
                {"id": "ich", "type": "indicator.ichimoku",
                 "params": {"tenkan_period": 9, "kijun_period": 26, "senkou_b_period": 52},
                 "position": {"x":  260, "y": 180}},
                {"id": "al1", "type": "alpha.crossover",
                 "params": {"direction": "both"},
                 "position": {"x":  540, "y": 180}},
                {"id": "atr", "type": "indicator.atr",
                 "params": {"period": 14},
                 "position": {"x":  540, "y": 380}},
                {"id": "sz1", "type": "sizing.atr_target",
                 "params": {"risk_pct": 1.0, "atr_mult": 1.5},
                 "position": {"x":  820, "y": 180}},
                {"id": "rk1", "type": "risk.atr_stop",
                 "params": {"mult": 1.5},
                 "position": {"x": 1100, "y": 180}},
                {"id": "ex1", "type": "exit.target_and_trail",
                 "params": {"target_r": 3.0, "close_pct": 0.5,
                            "trail_mode": "candle", "trail_buf": 2.0},
                 "position": {"x": 1380, "y": 180}},
                {"id": "xc1", "type": "execution.market",
                 "params": {"expiry_bars": 3},
                 "position": {"x": 1660, "y": 180}},
            ],
            "edges": [
                # TK cross
                {"from": "ich", "from_port": "tenkan",   "to": "al1", "to_port": "a"},
                {"from": "ich", "from_port": "kijun",    "to": "al1", "to_port": "b"},
                {"from": "al1", "from_port": "insight",  "to": "sz1", "to_port": "insight"},
                {"from": "atr", "from_port": "value",    "to": "sz1", "to_port": "atr"},
                {"from": "sz1", "from_port": "target",   "to": "rk1", "to_port": "target"},
                {"from": "atr", "from_port": "value",    "to": "rk1", "to_port": "atr"},
                {"from": "rk1", "from_port": "adjusted", "to": "ex1", "to_port": "adjusted"},
                {"from": "ex1", "from_port": "adjusted", "to": "xc1", "to_port": "adjusted"},
            ],
        },
    },
    {
        "id":   "smc_fvg_v2",
        "name": "SMC: Sweep + Order Block (long + short)",
        "description": "Real SMC playbook in BOTH directions — bull sweeps (equal lows grabbed) enter at the Bull OB midpoint, bear sweeps (equal highs grabbed) enter at the Bear OB midpoint. Each direction has its own OB, SL, and exit chain so the math is correct for shorts too.",
        "graph": {
            "name":  "SMC: Sweep + OB (long + short)",
            "nodes": [
                # ── Shared upstream: Universe + ATR ─────────────────────────
                {"id": "u1",  "type": "universe.single_asset",
                 "params": {"ticker": "XAUUSD", "timeframe": "M15"},
                 "position": {"x":    0, "y": 320}},
                {"id": "atr", "type": "indicator.atr",
                 "params": {"period": 14},
                 "position": {"x":  280, "y": 320}},

                # ── LONG CHAIN ──────────────────────────────────────────────
                {"id": "obL", "type": "indicator.order_block",
                 "params": {"direction": "long", "scan_min": 3, "scan_max": 15, "entry_ratio": 0.5},
                 "position": {"x":  280, "y":  40}},
                {"id": "alL", "type": "alpha.liquidity_sweep",
                 "params": {"lookback": 30, "count": 2,
                            "tolerance_pips": 3, "min_pierce_pips": 1.0,
                            "direction": "long"},
                 "position": {"x":  580, "y": 140}},
                {"id": "fsL", "type": "filter.session",
                 "params": {"start_hour": 7, "end_hour": 17},
                 "position": {"x":  880, "y": 140}},
                {"id": "faL", "type": "filter.threshold",
                 "params": {"min": 0.2, "max": 100},
                 "position": {"x": 1180, "y": 140}},
                {"id": "szL", "type": "sizing.fixed_pct",
                 "params": {"risk_pct": 1.0},
                 "position": {"x": 1480, "y": 140}},
                {"id": "rkL", "type": "risk.structure_stop",
                 "params": {"buf_pips": 3},
                 "position": {"x": 1780, "y": 140}},
                {"id": "e1L", "type": "exit.target_and_trail",
                 "params": {"target_r": 3.0, "close_pct": 0.5,
                            "trail_mode": "candle", "trail_buf": 2.0},
                 "position": {"x": 2080, "y": 140}},
                {"id": "e2L", "type": "exit.breakeven_at_r",
                 "params": {"be_at_r": 1.0},
                 "position": {"x": 2380, "y": 140}},
                {"id": "e3L", "type": "exit.time_exit",
                 "params": {"bars": 40},
                 "position": {"x": 2680, "y": 140}},
                {"id": "xcL", "type": "execution.limit_at",
                 "params": {"expiry_bars": 10},
                 "position": {"x": 2980, "y": 140}},

                # ── SHORT CHAIN ─────────────────────────────────────────────
                {"id": "obS", "type": "indicator.order_block",
                 "params": {"direction": "short", "scan_min": 3, "scan_max": 15, "entry_ratio": 0.5},
                 "position": {"x":  280, "y": 600}},
                {"id": "alS", "type": "alpha.liquidity_sweep",
                 "params": {"lookback": 30, "count": 2,
                            "tolerance_pips": 3, "min_pierce_pips": 1.0,
                            "direction": "short"},
                 "position": {"x":  580, "y": 500}},
                {"id": "fsS", "type": "filter.session",
                 "params": {"start_hour": 7, "end_hour": 17},
                 "position": {"x":  880, "y": 500}},
                {"id": "faS", "type": "filter.threshold",
                 "params": {"min": 0.2, "max": 100},
                 "position": {"x": 1180, "y": 500}},
                {"id": "szS", "type": "sizing.fixed_pct",
                 "params": {"risk_pct": 1.0},
                 "position": {"x": 1480, "y": 500}},
                {"id": "rkS", "type": "risk.structure_stop",
                 "params": {"buf_pips": 3},
                 "position": {"x": 1780, "y": 500}},
                {"id": "e1S", "type": "exit.target_and_trail",
                 "params": {"target_r": 3.0, "close_pct": 0.5,
                            "trail_mode": "candle", "trail_buf": 2.0},
                 "position": {"x": 2080, "y": 500}},
                {"id": "e2S", "type": "exit.breakeven_at_r",
                 "params": {"be_at_r": 1.0},
                 "position": {"x": 2380, "y": 500}},
                {"id": "e3S", "type": "exit.time_exit",
                 "params": {"bars": 40},
                 "position": {"x": 2680, "y": 500}},
                {"id": "xcS", "type": "execution.limit_at",
                 "params": {"expiry_bars": 10},
                 "position": {"x": 2980, "y": 500}},
            ],
            "edges": [
                # ── LONG CHAIN wires ────────────────────────────────────────
                {"from": "alL", "from_port": "insight",  "to": "fsL", "to_port": "insight"},
                {"from": "fsL", "from_port": "insight",  "to": "faL", "to_port": "insight"},
                {"from": "atr", "from_port": "value",    "to": "faL", "to_port": "value"},
                {"from": "faL", "from_port": "insight",  "to": "szL", "to_port": "insight"},
                {"from": "szL", "from_port": "target",   "to": "rkL", "to_port": "target"},
                {"from": "obL", "from_port": "low",      "to": "rkL", "to_port": "swing"},
                {"from": "rkL", "from_port": "adjusted", "to": "e1L", "to_port": "adjusted"},
                {"from": "e1L", "from_port": "adjusted", "to": "e2L", "to_port": "adjusted"},
                {"from": "e2L", "from_port": "adjusted", "to": "e3L", "to_port": "adjusted"},
                {"from": "e3L", "from_port": "adjusted", "to": "xcL", "to_port": "adjusted"},
                {"from": "obL", "from_port": "entry",    "to": "xcL", "to_port": "price"},

                # ── SHORT CHAIN wires ───────────────────────────────────────
                {"from": "alS", "from_port": "insight",  "to": "fsS", "to_port": "insight"},
                {"from": "fsS", "from_port": "insight",  "to": "faS", "to_port": "insight"},
                {"from": "atr", "from_port": "value",    "to": "faS", "to_port": "value"},
                {"from": "faS", "from_port": "insight",  "to": "szS", "to_port": "insight"},
                {"from": "szS", "from_port": "target",   "to": "rkS", "to_port": "target"},
                # IMPORTANT: shorts use OB HIGH as the structural reference
                {"from": "obS", "from_port": "high",     "to": "rkS", "to_port": "swing"},
                {"from": "rkS", "from_port": "adjusted", "to": "e1S", "to_port": "adjusted"},
                {"from": "e1S", "from_port": "adjusted", "to": "e2S", "to_port": "adjusted"},
                {"from": "e2S", "from_port": "adjusted", "to": "e3S", "to_port": "adjusted"},
                {"from": "e3S", "from_port": "adjusted", "to": "xcS", "to_port": "adjusted"},
                {"from": "obS", "from_port": "entry",    "to": "xcS", "to_port": "price"},
            ],
        },
    },
    {
        "id":   "rsi_bb_rich",
        "name": "RSI + Bollinger (filtered)",
        "description": "Mean-reversion: RSI oversold cross + Bollinger lower band touch, gated by ADX (trend strength) and a 20-bar cooldown. Structure stop + break-even at 1R + time exit.",
        "graph": {
            "name":  "RSI + Bollinger (filtered)",
            "nodes": [
                # Universe
                {"id": "u1",  "type": "universe.single_asset",
                 "params": {"ticker": "XAUUSD", "timeframe": "M15"},
                 "position": {"x":    0, "y":  60}},
                # Indicators
                {"id": "rsi", "type": "indicator.rsi",       "params": {"period": 14},  "position": {"x": 260, "y":  20}},
                {"id": "adx", "type": "indicator.adx",       "params": {"period": 14},  "position": {"x": 260, "y": 160}},
                {"id": "slo", "type": "indicator.swing_low", "params": {"period": 10},  "position": {"x": 260, "y": 300}},
                # Alpha — RSI threshold cross
                {"id": "al1", "type": "alpha.threshold",
                 "params": {"long_level": 30, "short_level": 70, "direction": "long"},
                 "position": {"x":  540, "y":  60}},
                # Filters — ADX > 20 (trend present) AND cooldown
                {"id": "f1",  "type": "filter.threshold",
                 "params": {"min": 20, "max": 1000000},
                 "position": {"x":  820, "y":  60}},
                {"id": "f2",  "type": "filter.cooldown",
                 "params": {"bars": 20},
                 "position": {"x": 1100, "y":  60}},
                # Sizing → Risk → Exits (stacked: target/trail + BE + time)
                {"id": "sz1", "type": "sizing.fixed_pct", "params": {"risk_pct": 1.0}, "position": {"x": 1380, "y":  60}},
                {"id": "rk1", "type": "risk.structure_stop", "params": {"buf_pips": 2}, "position": {"x": 1660, "y":  60}},
                {"id": "ex1", "type": "exit.target_and_trail",
                 "params": {"target_r": 2.5, "close_pct": 0.5, "trail_mode": "candle", "trail_buf": 1.0},
                 "position": {"x": 1940, "y":  60}},
                {"id": "ex2", "type": "exit.breakeven_at_r", "params": {"be_at_r": 1.0},   "position": {"x": 2220, "y":  60}},
                {"id": "ex3", "type": "exit.time_exit",     "params": {"bars": 60},        "position": {"x": 2500, "y":  60}},
                {"id": "xc1", "type": "execution.market",   "params": {"expiry_bars": 5},  "position": {"x": 2780, "y":  60}},
            ],
            "edges": [
                {"from": "rsi", "from_port": "value",    "to": "al1", "to_port": "value"},
                {"from": "al1", "from_port": "insight",  "to": "f1",  "to_port": "insight"},
                {"from": "adx", "from_port": "value",    "to": "f1",  "to_port": "value"},
                {"from": "f1",  "from_port": "insight",  "to": "f2",  "to_port": "insight"},
                {"from": "f2",  "from_port": "insight",  "to": "sz1", "to_port": "insight"},
                {"from": "sz1", "from_port": "target",   "to": "rk1", "to_port": "target"},
                {"from": "slo", "from_port": "value",    "to": "rk1", "to_port": "swing"},
                {"from": "rk1", "from_port": "adjusted", "to": "ex1", "to_port": "adjusted"},
                {"from": "ex1", "from_port": "adjusted", "to": "ex2", "to_port": "adjusted"},
                {"from": "ex2", "from_port": "adjusted", "to": "ex3", "to_port": "adjusted"},
                {"from": "ex3", "from_port": "adjusted", "to": "xc1", "to_port": "adjusted"},
            ],
        },
    },
    {
        "id":   "ema_cross_v2",
        "name": "EMA cross 20/50",
        "description": "Two EMAs piped through a Crossover alpha — proves the typed-wire model with the simplest possible strategy.",
        "graph": {
            "name":  "EMA cross 20/50",
            "nodes": [
                {"id": "u1",  "type": "universe.single_asset",
                 "params": {"ticker": "XAUUSD", "timeframe": "M15"},
                 "position": {"x":    0, "y":  60}},
                {"id": "ef",  "type": "indicator.ema",
                 "params": {"period": 20},
                 "position": {"x":  260, "y":  20}},
                {"id": "es",  "type": "indicator.ema",
                 "params": {"period": 50},
                 "position": {"x":  260, "y": 180}},
                {"id": "al1", "type": "alpha.crossover",
                 "params": {"direction": "both"},
                 "position": {"x":  540, "y": 100}},
                {"id": "sz1", "type": "sizing.fixed_pct",
                 "params": {"risk_pct": 1.0},
                 "position": {"x":  820, "y": 100}},
                {"id": "rk1", "type": "risk.fixed_pips",
                 "params": {"pips": 30},
                 "position": {"x": 1100, "y": 100}},
                {"id": "ex1", "type": "exit.target_and_trail",
                 "params": {"target_r": 3.0, "close_pct": 0.5,
                            "trail_mode": "candle", "trail_buf": 1.0},
                 "position": {"x": 1380, "y": 100}},
                {"id": "xc1", "type": "execution.market",
                 "params": {"expiry_bars": 10},
                 "position": {"x": 1660, "y": 100}},
            ],
            "edges": [
                {"from": "ef",  "from_port": "value",    "to": "al1", "to_port": "a"},
                {"from": "es",  "from_port": "value",    "to": "al1", "to_port": "b"},
                {"from": "al1", "from_port": "insight",  "to": "sz1", "to_port": "insight"},
                {"from": "sz1", "from_port": "target",   "to": "rk1", "to_port": "target"},
                {"from": "rk1", "from_port": "adjusted", "to": "ex1", "to_port": "adjusted"},
                {"from": "ex1", "from_port": "adjusted", "to": "xc1", "to_port": "adjusted"},
            ],
        },
    },
]


# ── Ship every starter with realistic execution costs ──────────────────────
# Each template gets a standalone `execution.costs` node so backtests model
# real slippage/spread out of the box instead of assuming perfect fills. The
# defaults are tuned for XAUUSD (every template's default symbol); users should
# adjust per instrument/broker via the node's params. No wires — it writes its
# values into the run context, which the backtest reads.
_DEFAULT_COSTS = {"slippage_pips": 1.0, "spread_pips": 2.0, "commission": 0.0}


def _ensure_costs_node(graph: Dict[str, Any]) -> None:
    nodes = graph["nodes"]
    if any(n.get("type") == "execution.costs" for n in nodes):
        return
    ys = [n.get("position", {}).get("y", 0) for n in nodes]
    nodes.append({
        "id":       "costs",
        "type":     "execution.costs",
        "params":   dict(_DEFAULT_COSTS),
        "position": {"x": 0, "y": (max(ys) if ys else 0) + 160},
    })


for _t in _TEMPLATES:
    _ensure_costs_node(_t["graph"])


def list_templates():
    return [{"id": t["id"], "name": t["name"], "description": t["description"]} for t in _TEMPLATES]


def get_template(template_id: str) -> Dict[str, Any]:
    for t in _TEMPLATES:
        if t["id"] == template_id:
            return t["graph"]
    raise KeyError(f"Unknown template: {template_id}")
