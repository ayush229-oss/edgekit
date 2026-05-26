# Edgekit — Architecture Overview

> Last updated: 2026-05-23 (Day 1 scaffold)

## Mission
No-code strategy backtesting for any market. Tiered: Free → Trader → Pro.
Form-wizard builder in v1; visual node builder in v2 (Pro tier).

## Repo Layout

```
edgekit/
├── backend/
│   ├── engine/                  ← strategy-agnostic core
│   │   ├── core/
│   │   │   ├── data_loader.py   ← CSV + MT5 + (future) broker adapters
│   │   │   ├── indicators.py    ← EMA, RSI, MACD, ATR, BB, VWAP, Supertrend
│   │   │   ├── simulator.py     ← universal simulate() — works for any strategy
│   │   │   └── metrics.py       ← win rate, EV, PF, drawdown, equity curve
│   │   ├── strategies/
│   │   │   ├── base.py          ← Strategy ABC + ParamSpec (drives UI)
│   │   │   ├── ob_fvg_liq.py    ← flagship SMC template (Day 1)
│   │   │   └── …                ← 9 more templates land Day 4–10
│   │   ├── builder/
│   │   │   └── compiler.py      ← (future) form-wizard config → Strategy instance
│   │   └── test_smoke.py
│   └── api/                     ← FastAPI service (Day 15+)
├── frontend/                    ← Next.js + Tailwind (Day 11+)
└── docs/
    └── ARCHITECTURE.md
```

## Layering principle
- `engine.core.simulator` is a pure function of `(df, setups, kwargs)` → trade log.
- Strategies only implement `detect()`. They never touch trade management.
- This means a new template ≈ 100–200 lines of detection code. Engine never changes.

## Data flow
```
User uploads CSV  ─┐
                   ├─▶ data_loader → normalized OHLCV DataFrame
MT5 live fetch  ─┘                              │
                                                ▼
                          strategy.detect(df, params) → setups
                                                │
                                                ▼
                          simulator.simulate(df, setups, ...) → trade log
                                                │
                                                ▼
                          metrics.compute_metrics(log) → headline stats
                                                │
                                                ▼
                                       Frontend charts + UI
```

## Tier → feature mapping
| Tier    | Templates | Custom builder       | Data sources              | Concurrent backtests |
|---------|-----------|----------------------|---------------------------|----------------------|
| Free    | 3         | —                    | MT5 only                  | 3 / day              |
| Trader  | 10        | Form wizard (v1)     | MT5 + CSV + broker APIs   | Unlimited            |
| Pro     | 10        | + Node builder (v2)  | All + portfolio multi-sym | Unlimited + queue    |
```
