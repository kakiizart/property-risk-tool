-- 0001_init.sql
-- Initial schema for the Property Risk & Hazard Exposure tool.
-- Target: Supabase Postgres (assumes the Supabase `auth` schema exists for RLS).
--
-- Apply with the Supabase SQL editor, the Supabase CLI, or psql against DATABASE_URL.

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
create extension if not exists postgis;      -- spatial types + point-in-polygon
create extension if not exists pgcrypto;     -- gen_random_uuid()

-- ---------------------------------------------------------------------------
-- Shared: auto-maintain updated_at
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- FEMA National Risk Index — per census tract (loaded by the Sprint 3 ETL)
-- ---------------------------------------------------------------------------
create table if not exists public.nri_tract (
    tract_geoid            text primary key,           -- 11-digit census tract GEOID
    state_abbr             text,
    county_name            text,
    risk_score             numeric,                    -- composite 0-100
    social_vulnerability   numeric,                    -- 0-100
    community_resilience   numeric,                    -- 0-100
    eal_total              numeric,                    -- expected annual loss, USD
    -- Per-peril relative scores (0-100). Full 18-peril set kept in peril_scores.
    peril_scores           jsonb   not null default '{}'::jsonb,
    geom                   geometry(MultiPolygon, 4326),  -- tract boundary for choropleth
    created_at             timestamptz not null default now(),
    updated_at             timestamptz not null default now()
);

create index if not exists nri_tract_geom_gix on public.nri_tract using gist (geom);

create trigger nri_tract_set_updated_at
    before update on public.nri_tract
    for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Cache for external lookups (NFHL / geocoder) — R4 mitigation
-- ---------------------------------------------------------------------------
create table if not exists public.lookup_cache (
    cache_key   text primary key,
    payload     jsonb       not null,
    created_at  timestamptz not null default now(),
    expires_at  timestamptz not null
);

create index if not exists lookup_cache_expires_idx on public.lookup_cache (expires_at);

-- ---------------------------------------------------------------------------
-- Saved reports — user-owned, isolated by row-level security (Sprint 5)
-- ---------------------------------------------------------------------------
create table if not exists public.saved_report (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references auth.users (id) on delete cascade,
    address     text not null,
    result      jsonb not null,               -- full risk report snapshot
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index if not exists saved_report_user_idx on public.saved_report (user_id, created_at desc);

create trigger saved_report_set_updated_at
    before update on public.saved_report
    for each row execute function public.set_updated_at();

-- Row-level security: a user may only touch their own rows.
alter table public.saved_report enable row level security;

create policy saved_report_select_own
    on public.saved_report for select
    using (auth.uid() = user_id);

create policy saved_report_insert_own
    on public.saved_report for insert
    with check (auth.uid() = user_id);

create policy saved_report_update_own
    on public.saved_report for update
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

create policy saved_report_delete_own
    on public.saved_report for delete
    using (auth.uid() = user_id);
