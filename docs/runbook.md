# Runbook

## Run locally
```bash
# Backend
cd api && source .venv/bin/activate && uvicorn app.main:app --reload

# Frontend (separate terminal)
cd web && npm run dev
```
Backend: http://localhost:8000 · Frontend: http://localhost:3000

## Health
- Liveness: `GET /health` → `{"status":"ok",...}`
- Readiness: `GET /health/ready` → checks config; `status:"degraded"` if a
  required setting is missing.

## Verify before committing
```bash
cd api && ruff check . && pytest -q
cd web && npm run typecheck && npm run build
```

## Common tasks
- **Add a backend route:** create it under `app/api/routes/`, include it in
  `app/main.py`, add a test in `tests/`.
- **Add a DB change:** new numbered file in `db/migrations/`; never edit an applied
  migration. Update `docs/database.md`.
- **Rotate a secret:** change it in the host's env settings; never commit it.

## Troubleshooting
| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Frontend shows "Backend unreachable" | API not running or wrong `NEXT_PUBLIC_API_URL` | Start the API; check the env value |
| `/health/ready` is `degraded` | Missing required env in production | Set `DATABASE_URL` and origins |
| CORS error in browser | Frontend origin not in `CORS_ORIGINS` | Add it to the backend env |
| Migration fails on `auth.users` | Not running against Supabase | Apply against the Supabase project |

## Recovery (from Sprint 6)
Rely on Supabase's managed backups for the database. To roll back the app,
redeploy the previous image/commit on Railway/Fly and Vercel. RTO/RPO targets are
set in Sprint 6.
