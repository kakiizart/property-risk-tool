-- 0003_lock_down_public_data_tables.sql
-- Close the Supabase Data API (PostgREST) write path to the reference tables.
--
-- Supabase exposes every table in `public` through its REST API and, by
-- default, grants the browser-facing `anon` and `authenticated` roles full
-- privileges on them. nri_tract and lookup_cache were created without RLS, so
-- anyone holding the project's publishable (anon) key — which ships in the web
-- build by design — could insert, update, or delete FEMA risk scores and cached
-- lookups directly, bypassing the API.
--
-- Neither table is meant to be reached from the browser: the FastAPI backend
-- reads and writes them over its own connection as the table owner (owners
-- bypass RLS unless FORCE is set), and the web app only uses Supabase for auth.
-- So: enable RLS with no policies (deny-by-default for API roles) and revoke
-- the default grants as a second layer.
--
-- saved_report is unaffected: it keeps its RLS policies (0001) and the
-- `authenticated` grants (0002) that the backend's RLS-scoped connection uses.
--
-- Idempotent; safe to re-run. Rollback: `disable row level security` and
-- re-grant, though there is no reason to expose these tables to API roles.

alter table public.nri_tract    enable row level security;
alter table public.lookup_cache enable row level security;

revoke all on public.nri_tract    from anon, authenticated;
revoke all on public.lookup_cache from anon, authenticated;
