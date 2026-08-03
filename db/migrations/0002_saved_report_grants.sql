-- 0002_saved_report_grants.sql
-- Sprint 5: let the RLS-scoped `authenticated` role operate on saved_report.
--
-- The API connects to Postgres directly (asyncpg), not through Supabase's
-- PostgREST. Per request it runs (see app.db.acquire_as_user):
--     SET LOCAL ROLE authenticated;
--     SELECT set_config('request.jwt.claims',
--                       '{"sub":"<user-uuid>","role":"authenticated"}', true);
-- so Supabase's auth.uid() resolves and the saved_report RLS policies added in
-- 0001 actually enforce per-user isolation *in the database* — not only in app
-- code. Switching to the non-owning `authenticated` role is also what makes RLS
-- apply at all (a table owner would bypass it).
--
-- For that to work the `authenticated` role needs table privileges. On Supabase
-- these are typically present via default privileges; this migration makes them
-- explicit and idempotent so isolation holds regardless of project defaults.
--
-- RLS still governs *which rows* the role may touch (auth.uid() = user_id);
-- these grants only decide that the role may touch the table at all.
--
-- Assumes the Supabase `authenticated` role exists (as 0001 assumes auth.users).
-- Apply with the Supabase SQL editor, the Supabase CLI, or psql against DATABASE_URL.

grant usage on schema public to authenticated;

grant select, insert, update, delete on public.saved_report to authenticated;
