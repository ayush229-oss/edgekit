-- Edgekit user data schema. Run once in Supabase SQL Editor.
--
-- Tables created:
--   profiles         — synced from Clerk on first signin
--   custom_nodes     — user's AI-generated reusable nodes
--   api_keys         — encrypted at app-level (AES-256-GCM) + at-rest (Supabase)
--   saved_strategies — full graph snapshots the user has saved
--   backtests        — every backtest run's metrics (for analytics)
--   usage_events     — coarse activity log for analytics
--
-- Row Level Security: every table has policies so users can only see their
-- own rows. The service_role key bypasses RLS for admin work.

-- ─── profiles ───────────────────────────────────────────────────────────
create table if not exists profiles (
  id              text primary key,                -- Clerk user id (e.g. "user_2ab...")
  email           text not null,
  name            text,
  image_url       text,
  signin_method   text,                            -- "google", "email_link", etc.
  created_at      timestamptz default now() not null,
  last_seen_at    timestamptz default now() not null
);
create index if not exists profiles_email_idx on profiles(email);

-- ─── custom_nodes ───────────────────────────────────────────────────────
create table if not exists custom_nodes (
  id              uuid primary key default gen_random_uuid(),
  user_id         text not null references profiles(id) on delete cascade,
  name            text not null,
  description     text,
  graph           jsonb not null,                  -- the V2Graph json
  prompt          text,                            -- original AI prompt
  created_at      timestamptz default now() not null,
  updated_at      timestamptz default now() not null
);
create index if not exists custom_nodes_user_idx on custom_nodes(user_id);

-- ─── api_keys (encrypted) ───────────────────────────────────────────────
create table if not exists api_keys (
  id              uuid primary key default gen_random_uuid(),
  user_id         text not null references profiles(id) on delete cascade,
  provider        text not null,                   -- "gemini", "binance", "mt5", ...
  encrypted_value text not null,                   -- base64(iv || tag || ciphertext)
  hint            text,                            -- last 4 chars for UI display
  created_at      timestamptz default now() not null,
  updated_at      timestamptz default now() not null,
  unique(user_id, provider)
);
create index if not exists api_keys_user_idx on api_keys(user_id);

-- ─── saved_strategies ───────────────────────────────────────────────────
create table if not exists saved_strategies (
  id              uuid primary key default gen_random_uuid(),
  user_id         text not null references profiles(id) on delete cascade,
  name            text not null,
  graph           jsonb not null,
  symbol          text,
  timeframe       text,
  created_at      timestamptz default now() not null,
  updated_at      timestamptz default now() not null
);
create index if not exists saved_strategies_user_idx on saved_strategies(user_id);

-- ─── backtests ──────────────────────────────────────────────────────────
create table if not exists backtests (
  id              uuid primary key default gen_random_uuid(),
  user_id         text not null references profiles(id) on delete cascade,
  strategy_id     uuid references saved_strategies(id) on delete set null,
  graph_snapshot  jsonb not null,                  -- what was actually run
  symbol          text,
  timeframe       text,
  n_bars          integer,
  metrics         jsonb,                           -- trades, wr, total_r, etc.
  duration_ms     integer,
  created_at      timestamptz default now() not null
);
create index if not exists backtests_user_idx on backtests(user_id, created_at desc);

-- ─── usage_events ───────────────────────────────────────────────────────
create table if not exists usage_events (
  id              uuid primary key default gen_random_uuid(),
  user_id         text not null references profiles(id) on delete cascade,
  event_type      text not null,                   -- "page_view", "template_load", "describe_strategy", ...
  details         jsonb,
  created_at      timestamptz default now() not null
);
create index if not exists usage_events_user_idx on usage_events(user_id, created_at desc);

-- ─── Row Level Security ─────────────────────────────────────────────────
-- Server uses service_role (bypasses RLS). These policies protect the data
-- if anyone ever uses the anon key from the client side directly.

alter table profiles         enable row level security;
alter table custom_nodes     enable row level security;
alter table api_keys         enable row level security;
alter table saved_strategies enable row level security;
alter table backtests        enable row level security;
alter table usage_events     enable row level security;

-- Profile can only be read by its owner (anon never accesses this directly anyway)
drop policy if exists "profiles_self_read" on profiles;
create policy "profiles_self_read" on profiles
  for select using (auth.jwt() ->> 'sub' = id);

-- Same for everything else — user only sees their own rows
do $$
declare
  t text;
begin
  for t in select unnest(array['custom_nodes','api_keys','saved_strategies','backtests','usage_events'])
  loop
    execute format('drop policy if exists "%I_self" on %I', t, t);
    execute format(
      'create policy "%I_self" on %I for all using (auth.jwt() ->> ''sub'' = user_id) with check (auth.jwt() ->> ''sub'' = user_id)',
      t, t
    );
  end loop;
end $$;
