# Database

PostgreSQL + PostGIS, hosted on Supabase. Migrations live in `db/migrations/` and
are ordered and additive.

## Applying migrations

Apply migrations in order (`0001` then `0002`). Any one of:
- **Supabase SQL editor** — paste each migration and run.
- **Supabase CLI** — `supabase db push` (or `supabase migration up`).
- **psql** — `psql "$DATABASE_URL" -f db/migrations/0001_init.sql` then
  `... -f db/migrations/0002_saved_report_grants.sql`.

Both assume the Supabase `auth` schema and roles exist (`auth.users`,
`auth.uid()` for the RLS policies; the `authenticated` role for `0002`).

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
- `result` (jsonb) — snapshot of the full report (same shape as `POST /report`).
- Index on `(user_id, created_at desc)` for listing.
- **RLS enabled** (`0001`); four policies restrict select/insert/update/delete to
  `auth.uid() = user_id`.
- **`0002_saved_report_grants.sql`** grants the `authenticated` role
  select/insert/update/delete on the table.

**How RLS is enforced over asyncpg.** The API connects directly (not via
PostREST), so `auth.uid()` isn't set for free and a table-owner connection would
bypass RLS. Per request, `app/db.py::acquire_as_user` opens a transaction,
`SET LOCAL ROLE authenticated`, and sets `request.jwt.claims` (transaction-local),
so `auth.uid()` resolves to the caller and the policies enforce isolation in the
database. The `0002` grants are what let the scoped role touch the table at all;
RLS still governs *which rows*. See `docs/security.md` for the threat model and a
manual isolation test.

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
