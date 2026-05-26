-- ============================================================
-- Edgekit — full schema (run once in Supabase SQL Editor)
-- Idempotent: safe to re-run.
-- ============================================================

-- ─── profiles ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS profiles (
  id            text PRIMARY KEY,
  email         text NOT NULL,
  name          text,
  image_url     text,
  signin_method text,
  is_admin      boolean DEFAULT false,
  created_at    timestamptz DEFAULT now() NOT NULL,
  last_seen_at  timestamptz DEFAULT now() NOT NULL
);
CREATE INDEX IF NOT EXISTS profiles_email_idx ON profiles(email);

-- Add is_admin if the table already existed without it
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS is_admin boolean DEFAULT false;

-- ─── custom_nodes ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS custom_nodes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     text NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  name        text NOT NULL,
  description text,
  graph       jsonb NOT NULL,
  prompt      text,
  created_at  timestamptz DEFAULT now() NOT NULL,
  updated_at  timestamptz DEFAULT now() NOT NULL
);
CREATE INDEX IF NOT EXISTS custom_nodes_user_idx ON custom_nodes(user_id);

-- ─── api_keys (encrypted) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_keys (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         text NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  provider        text NOT NULL,
  encrypted_value text NOT NULL,
  hint            text,
  created_at      timestamptz DEFAULT now() NOT NULL,
  updated_at      timestamptz DEFAULT now() NOT NULL,
  UNIQUE(user_id, provider)
);
CREATE INDEX IF NOT EXISTS api_keys_user_idx ON api_keys(user_id);

-- ─── saved_strategies ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS saved_strategies (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    text NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  name       text NOT NULL,
  graph      jsonb NOT NULL,
  symbol     text DEFAULT 'XAUUSD',
  timeframe  text DEFAULT 'M15',
  created_at timestamptz DEFAULT now() NOT NULL,
  updated_at timestamptz DEFAULT now() NOT NULL
);
CREATE INDEX IF NOT EXISTS saved_strategies_user_idx ON saved_strategies(user_id);

-- ─── saved_results (backtest snapshots) ───────────────────────
CREATE TABLE IF NOT EXISTS saved_results (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       text NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  name          text NOT NULL,
  strategy_name text,
  symbol        text,
  timeframe     text,
  bars          integer,
  metrics       jsonb NOT NULL,
  equity_curve  jsonb,
  graph         jsonb,
  created_at    timestamptz DEFAULT now() NOT NULL
);
CREATE INDEX IF NOT EXISTS saved_results_user_idx ON saved_results(user_id);

-- ─── backtests ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS backtests (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        text NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  strategy_id    uuid REFERENCES saved_strategies(id) ON DELETE SET NULL,
  graph_snapshot jsonb NOT NULL,
  symbol         text,
  timeframe      text,
  n_bars         integer,
  metrics        jsonb,
  duration_ms    integer,
  created_at     timestamptz DEFAULT now() NOT NULL
);
CREATE INDEX IF NOT EXISTS backtests_user_idx ON backtests(user_id, created_at DESC);

-- ─── testimonials ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS testimonials (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    text,
  name       text NOT NULL,
  role       text,
  text       text NOT NULL,
  tags       text[] DEFAULT '{}',
  status     text DEFAULT 'pending',
  avatar     text,
  created_at timestamptz DEFAULT now() NOT NULL
);
CREATE INDEX IF NOT EXISTS testimonials_status_idx ON testimonials(status);

-- ─── broker_connections ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS broker_connections (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         text NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  source_id       text NOT NULL,
  label           text,
  config          jsonb DEFAULT '{}',
  credentials_enc text,
  is_active       boolean DEFAULT false,
  created_at      timestamptz DEFAULT now() NOT NULL,
  UNIQUE(user_id, source_id)
);
CREATE INDEX IF NOT EXISTS broker_connections_user_idx ON broker_connections(user_id);

-- ─── usage_events ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS usage_events (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    text NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  event_type text NOT NULL,
  details    jsonb,
  created_at timestamptz DEFAULT now() NOT NULL
);
CREATE INDEX IF NOT EXISTS usage_events_user_idx ON usage_events(user_id, created_at DESC);

-- ─── Row Level Security ───────────────────────────────────────
ALTER TABLE profiles           ENABLE ROW LEVEL SECURITY;
ALTER TABLE custom_nodes       ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys           ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_strategies   ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_results      ENABLE ROW LEVEL SECURITY;
ALTER TABLE backtests          ENABLE ROW LEVEL SECURITY;
ALTER TABLE testimonials       ENABLE ROW LEVEL SECURITY;
ALTER TABLE broker_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events       ENABLE ROW LEVEL SECURITY;

-- profiles: owner can read their own row
DROP POLICY IF EXISTS "profiles_self_read" ON profiles;
CREATE POLICY "profiles_self_read" ON profiles
  FOR SELECT USING (auth.jwt() ->> 'sub' = id);

-- all user-scoped tables: owner sees only their rows
DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT unnest(ARRAY[
    'custom_nodes','api_keys','saved_strategies','saved_results',
    'backtests','broker_connections','usage_events'
  ])
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS "%s_self" ON %I', t, t);
    EXECUTE format(
      'CREATE POLICY "%s_self" ON %I FOR ALL
       USING (auth.jwt() ->> ''sub'' = user_id)
       WITH CHECK (auth.jwt() ->> ''sub'' = user_id)',
      t, t
    );
  END LOOP;
END $$;

-- testimonials: anyone can read approved ones; submitter can read their own
DROP POLICY IF EXISTS "testimonials_read_approved" ON testimonials;
CREATE POLICY "testimonials_read_approved" ON testimonials
  FOR SELECT USING (status = 'approved' OR auth.jwt() ->> 'sub' = user_id);
