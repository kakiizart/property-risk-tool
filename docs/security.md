# Security

How the app authenticates users, authorizes access to user-owned data, and where
the trust boundaries are. Scope is the Sprint 5 auth + saved-reports slice; the
public risk-lookup endpoints (`/geocode`, `/flood`, `/nri`, `/report`) require no
account and expose only authoritative public data.

## Trust model at a glance

```
Browser ──(Supabase Auth: email+password)──► Supabase issues a signed JWT
   │
   │  Authorization: Bearer <access token>
   ▼
FastAPI  ── verifies JWT (HS256 signature, exp, aud) ──► trusted user id (sub)
   │
   │  per request: SET LOCAL ROLE authenticated
   │               set_config('request.jwt.claims', {sub,role}, local=true)
   ▼
Postgres ── RLS policies (auth.uid() = user_id) ──► only the user's rows
```

Two independent checks protect saved reports: the **API** verifies the token and
scopes every query to the caller, and the **database** enforces row isolation via
RLS. Neither alone is the sole gate.

## Authentication

- **Provider:** Supabase Auth, email + password. Sign-up / sign-in / sign-out and
  token refresh are handled client-side by `@supabase/supabase-js`
  (`web/src/lib/auth.tsx`). The browser never sees a service-role key — only the
  public anon key and the user's own access token.
- **Verification (API):** `app/services/auth.py` verifies the access token with
  the project's HS256 **JWT secret** and checks:
  - signature (rejects forged / tampered tokens),
  - `exp` (rejects expired tokens),
  - `aud` (must be `authenticated`),
  - presence of `sub` (the user's UUID).
- **Boundary:** `app/api/deps.py::get_current_user` is the single dependency that
  protects `/reports*`. Missing/invalid/expired → **401**; server not configured
  with a secret → **503**. Route code only ever runs with a verified user.

### Why HS256 shared secret (and not JWKS)

Supabase can also sign tokens with asymmetric keys (ES256/RS256) served from a
JWKS endpoint. This slice deliberately uses the **HS256 shared secret**: it is
available on every project, needs no network fetch, and keeps the trust boundary
to a single documented secret. The trade-off is that the secret is symmetric —
so it must be stored only server-side and rotated via Supabase if leaked.
Migrating to JWKS/asymmetric verification is a clean future enhancement (swap the
key resolution in `verify_token`, keep everything else).

## Authorization

- **Horizontal (user ↔ user):** the primary risk — user A must never read/modify
  user B's reports. Enforced in the database by RLS on `saved_report`
  (`auth.uid() = user_id`) for select/insert/update/delete, **and** by the API
  scoping every query to the authenticated user.
- **How RLS is made to work over asyncpg:** the backend connects to Postgres
  directly, not through Supabase's PostgREST, so `auth.uid()` is not populated for
  free — and a table-owner connection would bypass RLS entirely. `app/db.py::
  acquire_as_user` fixes both: for each request it opens a transaction, switches
  to the non-owning `authenticated` role (`SET LOCAL ROLE`), and sets the request
  JWT claims (`set_config('request.jwt.claims', …, local=true)`). Then
  `auth.uid()` resolves to the caller and the policies enforce isolation. Both
  settings are transaction-local, so they reset when the connection returns to
  the pool (safe under transaction pooling). Migration `0002` grants the
  `authenticated` role table privileges so the scoped role can operate.
- **Vertical (privilege levels):** there are no admin or cross-user endpoints;
  every `/reports*` route resolves rows for `user.id` only. There is no path to
  escalate to another user's data or to a service role from the browser.

## Input handling & injection

- All SQL uses **parameterized queries** (asyncpg `$1…`); no string interpolation
  of user input. The RLS claims value is passed as a bound parameter; the only
  literal in `acquire_as_user` is the fixed role name `authenticated`.
- Report ids from the URL are parsed/validated as UUIDs; anything malformed is
  treated as "not found" (404), never fed into a query.
- Request bodies are validated at the boundary by Pydantic (address length, etc.).

## Secrets

- Everything sensitive comes from environment variables; `.env` is gitignored and
  `.env.example` documents the keys. Nothing secret is logged.
- Server: `SUPABASE_JWT_SECRET`, `DATABASE_URL`. Browser: `NEXT_PUBLIC_SUPABASE_URL`,
  `NEXT_PUBLIC_SUPABASE_ANON_KEY` (both are safe to ship to the client by design).
- The Supabase **service-role** key is never used by this app and must never be
  put in the web build.

## CORS

`CORSMiddleware` allows only the configured `CORS_ORIGINS` (the web origin) with
credentials. Set this to the exact deployed web origin in production.

## Known limitations / future work

- **Rate limiting** is not yet applied to `POST /reports` (which triggers a full
  pipeline run). Add a per-user limit before public deployment.
- **JWKS / asymmetric JWT** verification (see trade-off above).
- **Audit logging** for saved-report mutations is not implemented.
- **Dependency scanning:** `npm audit` reports pre-existing advisories in the
  Next.js toolchain; triage during Sprint 6 hardening.

## Manual verification (needs a live Supabase project)

CI runs fully mocked (no live DB), so RLS isolation is verified manually. With a
Supabase project and `0001` + `0002` applied:

1. Configure the API (`SUPABASE_JWT_SECRET`, `DATABASE_URL`) and the web app
   (`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`).
2. Create **two** users (A and B) via the app or the Supabase dashboard.
3. As A, save a report; note its `id`.
4. Get B's access token (sign in as B) and try to read A's report:
   ```bash
   curl -sS -o /dev/null -w "%{http_code}\n" \
     -H "Authorization: Bearer $TOKEN_B" \
     "$API/reports/$A_REPORT_ID"          # expect 404 (RLS hides A's row from B)
   curl -sS -H "Authorization: Bearer $TOKEN_B" "$API/reports"  # expect only B's reports
   ```
5. Negative auth checks:
   ```bash
   curl -sS -o /dev/null -w "%{http_code}\n" "$API/reports"                      # 401 (no token)
   curl -sS -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer bad" "$API/reports"  # 401
   ```

A direct database check (isolation independent of the API):

```sql
begin;
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"<USER_B_UUID>","role":"authenticated"}', true);
select count(*) from public.saved_report;   -- only B's rows are visible
rollback;
```
