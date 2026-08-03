# Architecture

## Components

- **web** — Next.js (App Router, TypeScript) + Tailwind + Leaflet. Renders the
  address form, the map (property point, flood-zone polygon, tract choropleth),
  and the result panel. All API access goes through `src/lib`.
- **api** — FastAPI. Owns geocoding, external hazard lookups, the scoring
  service, and (from Sprint 5) authenticated saved reports.
- **db** — PostgreSQL + PostGIS on Supabase. Stores the NRI tract dataset (with
  tract geometry for the choropleth), a lookup cache, and user-owned saved
  reports protected by row-level security.

## Data flow

Assembled server-side by `POST /report` (geocode → flood + NRI in parallel →
composite scoring); flood and NRI degrade to null independently if unavailable.

```
address string
   │
   ▼
Census Geocoder ── lat/lon + census tract GEOID ──┐
   │                                               │
   ▼                                               ▼
FEMA NFHL REST                        PostGIS: nri_tract (lookup by GEOID)
 point-in-polygon                      → per-peril scores + EAL($) + geometry
 → flood zone (AE/X/VE…)                          │
   │                                               │
   └───────────────┬───────────────────────────────┘
                   ▼
          Scoring service → composite score + per-peril tiers + EAL
                   │
                   ▼
          FastAPI JSON → Next.js → Leaflet map + result panel
```

## Saved reports & auth (Sprint 5)

The public risk lookup needs no account. Signed-in users can additionally save
report snapshots, isolated per user:

```
Browser (Supabase Auth: email+password) ──► access token (JWT)
   │  Authorization: Bearer <token>
   ▼
POST /reports ─ verify JWT (app.services.auth) ─► re-run pipeline ─► store snapshot
GET/DELETE /reports[/id] ─ verify JWT ─► RLS-scoped query (own rows only)
```

- The API verifies the Supabase JWT, then runs saved-report queries as the
  `authenticated` role with the request's JWT claims set, so the `saved_report`
  RLS policies enforce isolation **in the database** (see `docs/security.md`).
- `POST /reports` re-runs the pipeline server-side and persists the same shape a
  live `POST /report` returns (shared mapping) — the stored snapshot is
  server-computed, not client-supplied.

## External services

| Service | Use | Auth | Notes |
|---------|-----|------|-------|
| US Census Geocoder | address → lat/lon + tract GEOID | none | `geographies/onelineaddress` returns coordinates and census geographies in one call |
| FEMA NFHL (ArcGIS REST) | authoritative flood zone at a point | none | public MapServer; supports JSON/geoJSON queries |
| FEMA NRI | per-tract multi-peril scores + Expected Annual Loss | none | static dataset loaded into PostGIS (Sprint 3 ETL) |
| Supabase Auth | user sign-in; issues JWTs the API verifies | anon key (browser) + JWT secret (API) | email/password; HS256 token verification server-side |

## Key decisions

- **FastAPI** for the backend so one Python/FastAPI competence spans this and the
  separate Copilot RAG project.
- **PostGIS** because point-in-polygon and choropleth queries belong in the
  database, not the app layer. It also extends the relational-DB skillset from the
  Oracle/APEX work into geospatial.
- **Score is derived, not invented.** Every component links to FEMA NRI/NFHL and a
  documented formula. This is the project's core credibility guarantee.
- **Public core, authenticated layer.** The risk lookup is usable without an
  account (so it stays demoable); auth adds saved reports isolated by RLS.

## Resilience

External calls use a bounded timeout and a single retry; identical lookups are
cached in `lookup_cache`. A failing external service degrades gracefully rather
than crashing the request.
