"""
Async database connection pool (asyncpg / Supabase Postgres).

The pool is initialised in the FastAPI lifespan context manager so it starts
up once and is shared across all requests. If DATABASE_URL is not set (early
sprints or local dev without a database), the pool is left as None and the
NRI lookup service returns a 503 instead of crashing.

Connection string format (Supabase "Session pooler", recommended):
  postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres

The session pooler works over IPv4 (the direct db.<ref>.supabase.co host is
IPv6-only on the free tier). The transaction pooler (port 6543) also works:
the pool disables asyncpg's named prepared-statement cache, which transaction
pooling does not support.

Usage in request handlers:
  pool = get_pool()          # raises RuntimeError if pool not initialised
  async with pool.acquire() as conn:
      row = await conn.fetchrow("SELECT ...")
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Per-connection setup: decode Postgres json/jsonb as Python objects.

    asyncpg returns json/jsonb columns as raw JSON strings unless a codec is
    registered, which would force every caller to json.loads the value itself.
    Registering the codec here means rows come back with dict/list values
    everywhere (and dicts are encoded back to JSON on write).
    """
    for typename in ("json", "jsonb"):
        await conn.set_type_codec(
            typename,
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )


async def init_pool(database_url: str) -> None:
    """Create the connection pool.  Called from the FastAPI lifespan handler."""
    global _pool  # noqa: PLW0603
    _pool = await asyncpg.create_pool(
        database_url,
        min_size=1,
        max_size=10,
        command_timeout=10,
        # Supabase's transaction pooler (Supavisor, port 6543) cannot keep
        # named prepared statements across transactions; disabling asyncpg's
        # statement cache keeps the pool safe on either pooler mode.
        statement_cache_size=0,
        init=_init_connection,
    )
    logger.info("Database pool ready")


async def close_pool() -> None:
    """Drain and close the connection pool on shutdown."""
    global _pool  # noqa: PLW0603
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


def get_pool() -> asyncpg.Pool:
    """Return the active pool.  Raises RuntimeError if not initialised."""
    if _pool is None:
        raise RuntimeError("Database pool not initialised; DATABASE_URL may not be set.")
    return _pool


def pool_available() -> bool:
    """True if the pool has been initialised (DATABASE_URL was set at startup)."""
    return _pool is not None


@asynccontextmanager
async def acquire_as_user(user_id: str) -> AsyncIterator[asyncpg.Connection]:
    """Acquire a pooled connection scoped to *user_id* for row-level security.

    The backend connects to Postgres directly (asyncpg), not through Supabase's
    PostgREST, so ``auth.uid()`` is not populated automatically and — worse — a
    table-owner connection would *bypass* RLS entirely. This context manager
    fixes both: inside a transaction it switches to the non-owning
    ``authenticated`` role and sets the request's JWT claims, so ``auth.uid()``
    resolves to this user and the ``saved_report`` RLS policies actually enforce
    row isolation in the database (defence in depth alongside the API's own
    per-user filtering).

    Both settings are transaction-local (``SET LOCAL ROLE`` /
    ``set_config(..., is_local => true)``), so they reset automatically when the
    connection is returned to the pool — safe under transaction pooling.

    The claims value is passed as a bound parameter (never string-formatted), so
    it cannot be used for SQL injection.
    """
    pool = get_pool()
    claims = json.dumps({"sub": user_id, "role": "authenticated"})
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Role name cannot be parameterised; "authenticated" is a fixed
            # literal, never user input.
            await conn.execute("SET LOCAL ROLE authenticated")
            await conn.execute(
                "SELECT set_config('request.jwt.claims', $1, true)", claims
            )
            yield conn
