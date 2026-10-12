# Deployment

Three independently deployed pieces, all on free tiers.

## Database — Supabase
1. Create a Supabase project (choose a region near Erie, PA, e.g. `us-east`).
2. In the SQL editor, run `db/migrations/0001_init.sql` (enables PostGIS), then
   `db/migrations/0002_saved_report_grants.sql`.
3. **Connect → Session pooler** connection string → the backend's `DATABASE_URL`
   (IPv4-compatible; the direct `db.<ref>.supabase.co` host is IPv6-only).
4. Project URL → the backend's `SUPABASE_URL` (JWKS token verification) and the
   frontend's `NEXT_PUBLIC_SUPABASE_URL`; publishable key →
   `NEXT_PUBLIC_SUPABASE_ANON_KEY`. Only older projects still on the legacy
   signing secret also need `SUPABASE_JWT_SECRET`.

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
