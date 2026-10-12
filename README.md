# Property Risk & Hazard Exposure Tool

A full-stack web app that takes a US property address and returns a transparent,
source-traceable multi-peril risk profile — built on authoritative FEMA data and
rendered on an interactive map.

> **Scope note:** This is a **geospatial property risk / hazard-exposure tool**,
> not a catastrophe model. It orchestrates authoritative federal data (FEMA
> National Risk Index + National Flood Hazard Layer) through a documented scoring
> function. Every number in the output is traceable to a source.

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js (App Router, TypeScript), Tailwind, Leaflet |
| Backend | Python, FastAPI |
| Database | PostgreSQL + PostGIS (Supabase) |
| Data | FEMA NRI, FEMA NFHL, US Census Geocoder (all free, no API key) |
| Hosting | Vercel (web) · Railway/Fly (api) · Supabase (db) |

## Repository layout

```
api/    FastAPI backend (health + geocode + flood + NRI + report + saved reports)
web/    Next.js frontend
db/     SQL migrations (PostGIS + tables + RLS + grants)
docs/   architecture, database, security, methodology, deployment, runbook
```

## Quick start

### Backend
```bash
cd api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
# -> http://localhost:8000/health
```

### Frontend
```bash
cd web
npm install
cp .env.example .env.local     # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
# -> http://localhost:3000
```

### Auth (optional)
Saved reports need Supabase. Set `SUPABASE_URL` (api) and
`NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` (web), then apply
`db/migrations/0002_saved_report_grants.sql`. Leave them unset to run the public
risk lookup without accounts (the saved-report UI hides itself). See
`docs/security.md` for the auth + RLS model and an isolation smoke test.

### Verify
```bash
cd api && ruff check . && pytest -q          # lint + tests
cd web && npm run typecheck && npm run build # typecheck + build
```

## Project status

| Sprint | Scope | Status |
|--------|-------|--------|
| 0 | Foundation: scaffold, health checks, migration, CI, docs | ✅ done |
| 1 | Geocode slice (address → coordinates + census tract) | ✅ done |
| 2 | Flood-zone slice (NFHL point lookup + map polygon) | ✅ done |
| 3 | NRI ingestion + multi-peril scores | ✅ done |
| 4 | Composite scoring + result report (`POST /report`) | ✅ done |
| 5 | Auth + saved reports (Supabase Auth + RLS) | ✅ done¹ |
| 6 | Harden + deploy | ⬜ |

¹ Code complete and verified offline (lint, tests, typecheck, build). Live
end-to-end verification (real Supabase sign-in + RLS isolation) is pending a
provisioned Supabase project — steps in `docs/security.md`.

See `docs/` for architecture, the scoring methodology, security, and the runbook.
