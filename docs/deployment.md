# Deployment

Three independently deployed pieces, all on free tiers.

## Database — Supabase
1. Create a Supabase project (choose a region near Erie, PA, e.g. `us-east`).
2. In the SQL editor, run `db/migrations/0001_init.sql` (enables PostGIS).
3. Copy the connection string into the backend's `DATABASE_URL`.
4. Copy the project URL and anon/public key for the frontend auth work (Sprint 5).

> Provisioning the Supabase project is an owner action — do not automate it
> without approval.

## Backend — Railway or Fly
- The `api/Dockerfile` builds a runnable image; the container listens on `$PORT`.
- Set env vars from `api/.env.example` (at minimum `ENVIRONMENT=production`,
  `DATABASE_URL`, and `CORS_ORIGINS` = the deployed frontend origin).
- Health check path: `/health`. Readiness: `/health/ready`.
- In production the app fails fast on startup if `DATABASE_URL` is missing.

## Frontend — Vercel
- Import the repo, set the project root to `web/`.
- Env var: `NEXT_PUBLIC_API_URL` = the deployed backend URL.
- Build command `npm run build`, output handled by Next.js automatically.

## Post-deploy smoke test
```bash
curl -s https://<api-host>/health          # expect {"status":"ok",...}
# open https://<web-host> and confirm "Backend healthy" renders
```

## Environments
`development` (local), `staging` (optional preview), `production`. CORS origins
and `DATABASE_URL` differ per environment; never reuse production secrets locally.
