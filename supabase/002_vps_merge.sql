-- 002_vps_merge.sql
-- Move the VPS-only tables (backtest_runs, forward_tests, live_trades) into
-- Supabase so there is a SINGLE source of truth. These are written/read by the
-- FastAPI backend using the service-role key (which bypasses RLS). RLS is
-- enabled with NO public policies, so browser/anon clients cannot touch them
-- directly — only the backend can.
--
-- Safe to run multiple times (CREATE TABLE IF NOT EXISTS). Non-destructive:
-- it only ADDS empty tables; nothing existing is changed or dropped.

-- ── Backtest run log (every run, incl. anonymous — powers global stats) ──────
create table if not exists public.backtest_runs (
  id              bigint generated always as identity primary key,
  user_id         text,                                  -- Clerk id; null for anonymous
  strategy_id     text not null,
  params_snapshot jsonb not null default '{}'::jsonb,
  metrics         jsonb not null default '{}'::jsonb,
  symbol          text not null default '',
  timeframe       text not null default '',
  bars            integer not null default 0,
  created_at      timestamptz not null default now()
);
create index if not exists backtest_runs_created_idx  on public.backtest_runs(created_at desc);
create index if not exists backtest_runs_strategy_idx on public.backtest_runs(strategy_id);
create index if not exists backtest_runs_user_idx     on public.backtest_runs(user_id);

-- ── Forward (paper) tests ────────────────────────────────────────────────────
create table if not exists public.forward_tests (
  id          bigint generated always as identity primary key,
  user_id     text,                                      -- Clerk id; null for anonymous
  name        text not null default '',
  symbol      text not null default 'XAUUSD',
  timeframe   text not null default 'M15',
  graph       jsonb not null default '{}'::jsonb,
  mgmt        jsonb not null default '{}'::jsonb,
  baseline    jsonb not null default '{}'::jsonb,
  started_at  timestamptz not null,
  status      text not null default 'active',
  latest      jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists forward_tests_user_idx   on public.forward_tests(user_id);
create index if not exists forward_tests_status_idx on public.forward_tests(status);

-- ── Live-trade ledger (append-only) for demo-execution forward tests ─────────
create table if not exists public.live_trades (
  id              bigint generated always as identity primary key,
  forward_test_id bigint not null references public.forward_tests(id) on delete cascade,
  ts              timestamptz not null default now(),
  action          text not null default 'open',
  symbol          text not null default '',
  side            text not null default '',
  volume          double precision not null default 0,
  requested_price double precision not null default 0,
  fill_price      double precision not null default 0,
  slippage        double precision not null default 0,
  spread          double precision not null default 0,
  sl              double precision not null default 0,
  tp              double precision not null default 0,
  ticket          bigint not null default 0,
  profit          double precision not null default 0,
  comment         text not null default ''
);
create index if not exists live_trades_ft_idx on public.live_trades(forward_test_id);
create index if not exists live_trades_ts_idx on public.live_trades(ts);

-- ── Lock down: service-role only (the backend). No public policies. ─────────
alter table public.backtest_runs enable row level security;
alter table public.forward_tests enable row level security;
alter table public.live_trades  enable row level security;
