# TASK: Database merge (#4) — move VPS SQLite tables into Supabase

## ✅ COMPLETE — 2026-06-05

All five steps finished and deployed. Supabase is now the sole source of
truth for `backtest_runs`, `forward_tests`, and `live_trades`. SQLite
remains in use only for `users` / `saved_strategies` / auth.

### What was done

1. ✅ **Supabase tables created** — `supabase/002_vps_merge.sql` run in
   dashboard SQL editor. `backtest_runs`, `forward_tests`, `live_trades`
   with RLS on, service-role only. DDL additions: `vps_id`, `ft_vps_id`
   columns on `forward_tests` and `live_trades`.

2. ✅ **`backend/api/supa.py`** — PostgREST client (insert, update, select,
   count, upsert, get_forward_test, get_forward_test_by_id,
   get_forward_tests_by_vps_ids, get_live_trades). `SUPABASE_URL` +
   `SUPABASE_SERVICE_ROLE_KEY` set in `/opt/edgekit/backend/.env`.

3. ✅ **Backtest dual-write** — `main.py` `/backtest` and
   `routes_graph_v2.py` `/graph/v2/backtest` both log to Supabase.
   Verified: 9 rows landed in `backtest_runs`.

4. ✅ **Reads switched to Supabase** — `/stats/global` reads from Supabase
   (with SQLite max() guard). Forward-test list/get/refresh/stop all read
   from Supabase with SQLite fallback.

5. ✅ **SQLite retired** — All writes to `backtest_runs`, `forward_tests`,
   `live_trades` removed. Scheduler reads/writes Supabase only via
   `_refresh_supa`. Quota check (`limits.py`) reads `backtest_runs` from
   Supabase by `clerk_id`. `live_event` inserts directly to Supabase.

5b. ✅ **SQLite ORM models dropped** — `BacktestRun`, `ForwardTest`, `LiveTrade`
    removed from `models.py` and all imports cleaned up. `init_db()` no longer
    creates these tables. `/user/runs` reads from Supabase by `clerk_id`.
    `/stats/global` has no SQLite fallback for backtest count.
    SQLite file on VPS is inert (tables still exist physically but nothing
    reads or writes them).

### Remaining (out of scope for this task)
- Migrate `users` / `saved_strategies` / auth off SQLite (separate task).
