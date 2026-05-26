# Edgekit API — endpoint reference

Base URL (dev): `http://127.0.0.1:8765`

## Auth headers

For local dev:
```
X-Dev-User: someone@example.com           # creates a Free user
X-Dev-User: someone@example.com:pro       # creates a Pro user
X-Dev-User: someone@example.com:trader    # creates a Trader user
```

For production:
```
Authorization: Bearer <clerk-jwt>
```

## Endpoints

### Public

| Method | Path | Purpose |
|--------|------|---------|
| GET    | `/healthz`          | Service health |
| GET    | `/strategies`       | List all strategy templates |
| GET    | `/strategies/{id}`  | Single strategy + param schema |
| POST   | `/upload-csv`       | Upload OHLCV CSV → returns data_id |
| POST   | `/backtest`         | Run a backtest (anonymous in dev; quota-gated when authed) |
| POST   | `/waitlist`         | Join early-access waitlist |
| GET    | `/waitlist/count`   | Public waitlist size |

### Authenticated

| Method | Path | Tier required | Purpose |
|--------|------|---------------|---------|
| GET    | `/me`                       | any   | Profile + tier limits |
| GET    | `/saved-strategies`         | any   | List my saved strategies |
| POST   | `/saved-strategies`         | any (cap by tier) | Save a strategy config |
| DELETE | `/saved-strategies/{sid}`   | any   | Delete one |
| GET    | `/runs?limit=N`             | any   | My backtest history |
| POST   | `/billing/checkout`         | any   | Start Lemon Squeezy checkout (stub if not configured) |
| POST   | `/billing/webhook`          | (LS signed) | LS subscription events |

## Tier limits (from `backend/api/limits.py`)

| Limit             | Free | Trader | Pro |
|-------------------|------|--------|-----|
| Daily backtests   | 3    | ∞      | ∞   |
| Saved strategies  | 1    | 10     | 100 |
| CSV upload        | —    | ✓      | ✓   |
| Node builder      | —    | —      | ✓   |
