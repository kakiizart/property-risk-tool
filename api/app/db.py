"""
Async database connection pool (asyncpg / Supabase Postgres).

The pool is initialised in the FastAPI lifespan context manager so it starts
up once and is shared across all requests. If DATABASE_URL is not set (early
sprints or local dev without a database), the pool is left as None and the
NRI lookup service returns a 503 instead of crashing.

Connection string format (Supabase):
  postgresql://postgres.<project-ref>:<password>@aws-0-us-east-1.pooler.supabase.com:6543/postgres

Usage in request handlers:
  pool = get_pool()          # raises RuntimeError if pool not initialised
  async with pool.acquire() as conn:
      row = await conn.fetchrow("SELECT ...")
"""

from __future__ import annotations

import logging

import asyncpg

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def init_pool(database_url: str) -> None:
    """Create the connection pool.  Called from the FastAPI lifespan handler."""
    global _pool  # noqa: PLW0603
    _pool = await asyncpg.create_pool(
        database_url,
        min_size=1,
        max_size=10,
        command_timeout=10,
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
