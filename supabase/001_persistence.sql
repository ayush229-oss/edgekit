-- ============================================================
-- Edgekit — persistence tables
-- Run once in Supabase → SQL Editor
-- ============================================================

-- 1. saved_results ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS saved_results (
  id            uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id       text        NOT NULL,
  name          text        NOT NULL,
  strategy_name text,
  symbol        text,
  timeframe     text,
  bars          integer,
  metrics       jsonb       NOT NULL,
  equity_curve  jsonb,
  graph         jsonb,
  created_at    timestamptz DEFAULT now()
);

-- 2. saved_strategies ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS saved_strategies (
  id          uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id     text        NOT NULL,
  name        text        NOT NULL,
  graph       jsonb       NOT NULL,
  symbol      text        DEFAULT 'XAUUSD',
  timeframe   text        DEFAULT 'M15',
  created_at  timestamptz DEFAULT now(),
  updated_at  timestamptz DEFAULT now()
);

-- 3. testimonials ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS testimonials (
  id         uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id    text,
  name       text        NOT NULL,
  role       text,
  text       text        NOT NULL,
  tags       text[]      DEFAULT '{}',
  status     text        DEFAULT 'pending',  -- pending | approved | rejected
  avatar     text,
  created_at timestamptz DEFAULT now()
);

-- 4. broker_connections ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS broker_connections (
  id              uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id         text        NOT NULL,
  source_id       text        NOT NULL,
  label           text,
  config          jsonb       DEFAULT '{}',  -- non-sensitive: host, port
  credentials_enc text,                       -- AES-256-GCM encrypted sensitive fields
  is_active       boolean     DEFAULT false,
  created_at      timestamptz DEFAULT now(),
  UNIQUE(user_id, source_id)
);

-- 5. is_admin column on profiles ───────────────────────────────
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS is_admin boolean DEFAULT false;

-- ── Indexes for fast per-user lookups ─────────────────────────
CREATE INDEX IF NOT EXISTS saved_results_user_id_idx     ON saved_results(user_id);
CREATE INDEX IF NOT EXISTS saved_strategies_user_id_idx  ON saved_strategies(user_id);
CREATE INDEX IF NOT EXISTS testimonials_status_idx       ON testimonials(status);
CREATE INDEX IF NOT EXISTS broker_connections_user_idx   ON broker_connections(user_id);
