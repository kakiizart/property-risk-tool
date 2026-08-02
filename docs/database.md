# Database

PostgreSQL + PostGIS, hosted on Supabase. Migrations live in `db/migrations/` and
are ordered and additive.

## Applying migrations

Any one of:
- **Supabase SQL editor** — paste the migration and run.
- **Supabase CLI** — `supabase db push` (or `supabase migration up`).
- **psql** — `psql "$DATABASE_URL" -f db/migrations/0001_init.sql`.

`0001_init.sql` assumes the Supabase `auth` schema exists (for `auth.users` and
`auth.uid()` in the RLS policies).

## Tables

### `nri_tract`
FEMA National Risk Index data, one row per census tract. Loaded by the Sprint 3
ETL from the NRI census-tract dataset (OpenFEMA download or the ArcGIS feature
service).
- `tract_geoid` (PK) — 11-digit GEOID, the join key from the geocoder.
- `risk_score`, `social_vulnerability`, `community_resilience` — 0–100.
- `eal_total` — Expected Annual Loss in USD.
- `peril_scores` (jsonb) — full per-peril score set.
- `geom` — `MultiPolygon, 4326`, tract boundary for the choropleth (GIST index).

### `lookup_cache`
Caches external NFHL/geocoder responses (R4 mitigation). Keyed by `cache_key`
with an `expires_at`; an index on `expires_at` supports cleanup.

### `saved_report`
User-owned risk reports (Sprint 5).
- `user_id` → `auth.users(id)`, cascade on delete.
- `result` (jsonb) — snapshot of the full report.
- Index on `(user_id, created_at desc)` for listing.
- **RLS enabled**; four policies restrict select/insert/update/delete to
  `auth.uid() = user_id`.

## Conventions
- `created_at` / `updated_at` on mutable tables; `updated_at` maintained by the
  `set_updated_at()` trigger.
- Indexes are added from real access patterns (tract lookup by GEOID via PK;
  spatial GIST on tract geometry; report listing by user).
- Isolation is enforced in the database (RLS), not only in the API.

## NRI ingestion (Sprint 3, planned)
1. Download the NRI census-tract table + tract geometry.
2. Normalize to the `nri_tract` columns; keep the full peril set in `peril_scores`.
3. Bulk load; verify row count and a few known tracts.
4. Document the source version (e.g., NRI v1.20) in the load script.
