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
Sprints 0-5 complete. Sprint 5 = Supabase Auth (email/password) + user-owned
saved reports: JWT verification at the API boundary (`services/auth.py` +
`api/deps.py`) — verifies modern Supabase **ES256** tokens against the project
JWKS (`SUPABASE_URL`), with HS256 (`SUPABASE_JWT_SECRET`) as a fallback — plus an
RLS-scoped DB helper (`SET LOCAL ROLE authenticated` + `request.jwt.claims`) so
the `saved_report` policies enforce isolation in the DB even though the backend
uses asyncpg (not PostgREST), the `/reports` CRUD endpoints, migration `0002`
(authenticated grants), and the frontend auth + saved-reports UI. Deps: added
`asyncpg` + `pyjwt[crypto]` (also fixed `requirements.txt`, which was missing
asyncpg and broke the Docker image). Doc: `docs/security.md`.

Verified offline: ruff clean, 105 backend tests pass (+8 opt-in golden). Verified
LIVE against a provisioned Supabase project (`property-risk-tool`): DB-layer RLS
isolation (two users; cross-user read blocked, write blocked with `42501`) and
real ES256 token auth through the running API. The ES256/JWKS support was added
after live testing showed Supabase signs user tokens with ES256, not HS256 (an
HS256-only verifier rejected real users). Still pending: full DB-backed
CRUD-over-HTTP e2e (needs the project DB password). Next: Sprint 6 harden + deploy
(rate-limit `/reports`, deploy).

## Do not
- Provision cloud infra, push, deploy, or run destructive DB ops without explicit
  approval from the owner.
- Introduce new frameworks/dependencies without a concrete reason.
