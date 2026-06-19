# Edgekit

**No-code backtesting for any strategy, any market.**

Operated by [Satyasakshi](https://www.satyasakshi.com) as a separate product brand.

## Status — Day 1–4 done ✅

Backend, API, and frontend scaffold all live. 10 strategy templates working end-to-end.

### What's wired

| Layer | Status |
|-------|--------|
| **Strategy engine** | ✅ 10 templates, universal simulator, partial-TPs, trailing SL |
| **Data loaders** | ✅ CSV (MT5/MT4/TradingView/Binance/Yahoo auto-detect) + MT5 live |
| **Pip detection** | ✅ Symbol lookup + price-magnitude fallback for unknowns |
| **Indicators** | ✅ EMA, SMA, RSI, MACD, ATR, BB, VWAP, Supertrend, Pivots |
| **Metrics** | ✅ WR, EV, PF, drawdown, equity curve, exit breakdown |
| **FastAPI service** | ✅ `/strategies`, `/backtest`, `/upload-csv`, `/healthz` |
| **Next.js frontend** | ✅ Strategy gallery + per-strategy tuner UI |
| **Signup / beta** | ✅ Clerk auth on the landing page (`/waitlist` is a legacy redirect → `/`) |
| **Therapeutic theme** | ✅ Cream + sage palette across backend + frontend |

### 10 templates

`ob_fvg_liq` · `ema_cross` · `rsi_mr` · `bb_bounce` · `donchian` · `orb` · `macd_cross` · `vwap_pullback` · `supertrend` · `liq_engulf`

## Run it

```powershell
# Backend
cd C:\Users\Ayush\projects\edgekit
python -m uvicorn backend.api.main:app --reload --port 8765

# Frontend (separate terminal)
cd C:\Users\Ayush\projects\edgekit\frontend
npm install
npm run dev
# → http://localhost:3000
```

See [`docs/RUNBOOK.md`](docs/RUNBOOK.md) for details.

## What's next

- Day 5: Postgres schema + Clerk auth wiring
- Day 6: Lemon Squeezy billing → Free/Trader/Pro tier gating
- Day 7: CSV upload UI flow
- Day 8+: Closed beta invites + waitlist marketing
- Week 5+: Visual node builder (Pro tier) in parallel
