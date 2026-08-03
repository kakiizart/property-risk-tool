# CLAUDE.md — working notes for AI assistants

## What this is
A geospatial property-risk web app for an Erie Insurance internship portfolio.
Address in → FEMA hazard data → transparent risk profile on a map.

**Framing guardrail:** never describe this as "catastrophe modeling" or as ML
loss prediction. It is authoritative-data orchestration plus a documented scoring
function. Keep resume/interview claims honest (see `docs/methodology.md`).

## Architecture (one line)
`web (Next.js)` → `api (FastAPI)` → `Postgres/PostGIS (Supabase)`, with live calls
to the US Census Geocoder and FEMA NFHL, and NRI data loaded locally.

## Conventions
- **Backend:** routes → services → data access, separated. Validate at the
  boundary. Structured JSON logs, never log secrets. Timeouts + bounded retries
  on external calls. Tests in `api/tests`.
- **Frontend:** keep fetch logic in `web/src/lib`, not in components. Provide
  loading / empty / error / success states.
- **DB:** migrations in `db/migrations`, ordered and additive. `created_at` /
  `updated_at` on mutable tables. RLS on any user-owned table; enforce isolation
  in the database, not just the app.
- **Secrets:** only via env. `.env` is gitignored; `.env.example` documents keys.

## Definition of done (per task)
Implemented + integrated + tested + lint/typecheck clean + docs updated +
authorization/regression considered. Code existing is not the same as done.

## Verify commands
```bash
cd api && ruff check . && pytest -q
cd web && npm run typecheck && npm run build
```

## Current state
Sprints 0-4 complete: health/readiness, geocode (US Census), flood zone (FEMA
NFHL), NRI multi-peril scores (FEMA NRI in Postgres), and composite scoring +
the `POST /report` result endpoint, plus the initial migration (PostGIS +
nri_tract + lookup_cache + saved_report with RLS), CI, docs. Verified end-to-end
against live FEMA/Census + Postgres: 74 backend tests pass offline (+8 opt-in
live golden-address checks, RUN_GOLDEN=1), ruff clean; web typechecks, lints,
and builds clean. Next: Sprint 5 auth + saved reports (Supabase Auth + RLS).

## Do not
- Provision cloud infra, push, deploy, or run destructive DB ops without explicit
  approval from the owner.
- Introduce new frameworks/dependencies without a concrete reason.
