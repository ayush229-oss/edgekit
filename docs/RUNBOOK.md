# Edgekit — Local Runbook

## Backend (Python + FastAPI)

```powershell
cd C:\Users\Ayush\projects\edgekit
python -m uvicorn backend.api.main:app --reload --port 8765
```

- Health:    http://127.0.0.1:8765/healthz
- Docs:      http://127.0.0.1:8765/docs   (Swagger UI auto-generated)
- Strategies: http://127.0.0.1:8765/strategies

MT5 must be open + logged in for live-data backtests to work.

## Frontend (Next.js + Tailwind)

```powershell
cd C:\Users\Ayush\projects\edgekit\frontend
npm install            # one-time
npm run dev            # opens http://localhost:3000
```

Make sure the backend is running first — the home page queries `/strategies`.

## Smoke test (no frontend)

```powershell
cd C:\Users\Ayush\projects\edgekit
python -m backend.engine.test_smoke
```

## Project layout

```
edgekit/
├── backend/
│   ├── engine/          ← strategy engine (10 templates, simulator, metrics)
│   └── api/             ← FastAPI service layer
├── frontend/            ← Next.js 14 + Tailwind + Recharts
│   ├── src/app/
│   │   ├── page.tsx                 ← strategy gallery (home)
│   │   └── strategy/[id]/page.tsx   ← params + backtest UI
│   ├── src/components/  ← ParamForm, MetricsPanel, EquityChart
│   └── src/lib/api.ts   ← typed API client
└── docs/                ← ARCHITECTURE.md, RUNBOOK.md (this file)
```

## What's wired right now (build day 1–4)

- ✅ 10 strategy templates (OB+FVG+Liq, EMA Cross, RSI MR, BB Bounce, Donchian,
  ORB, MACD, VWAP Pullback, Supertrend, Liquidity Grab + Engulfing)
- ✅ Universal simulator (handles partial TPs, trailing, concurrent limit)
- ✅ Universal metrics (WR, EV, PF, drawdown, equity curve)
- ✅ CSV upload pipeline (MT5/MT4/TV/Binance/Yahoo format auto-detect)
- ✅ MT5 live fetch
- ✅ FastAPI service — `/strategies`, `/upload-csv`, `/backtest`, `/healthz`
- ✅ Form-Wizard UI scaffold (auto-generates inputs from each strategy's param_schema)
- ✅ Therapeutic light theme (cream + sage), mobile-responsive grid

## Next milestones

- Day 5–6: Database (Postgres via Supabase), user auth (Clerk), persistence of saved strategies
- Day 7: Lemon Squeezy billing → Free / Trader / Pro gating
- Day 8: Landing page with waitlist signup (Hybrid beta plan)
- Day 9–10: CSV upload UI + "Bring your own data" flow
- Week 5+: Visual node builder (Pro tier) in parallel
```
