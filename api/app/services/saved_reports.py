"""
Saved reports — user-owned report snapshots, isolated by row-level security.

Every function runs through :func:`app.db.acquire_as_user`, so queries execute
as the Supabase ``authenticated`` role with the caller's JWT claims set. The
``saved_report`` RLS policies (``auth.uid() = user_id``) therefore enforce
isolation in the database. We also pass ``user_id`` explicitly on writes for
clarity and defence in depth — the API and the database agree on ownership.

Report ids are UUIDs. Callers pass them as strings (from the URL); we parse and
validate them here, treating anything malformed as "not found" rather than an
error, so a junk id can never leak into a query or a 500.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

from app.db import acquire_as_user, pool_available

logger = logging.getLogger(__name__)


class SavedReportError(Exception):
    """Saved-report storage is unavailable (no DATABASE_URL / pool). Maps to 503."""


@dataclass(frozen=True)
class SavedReport:
    id: str
    address: str
    result: dict[str, Any]        # full risk-report snapshot (ReportResponse shape)
    created_at: datetime
    updated_at: datetime


def _require_db() -> None:
    if not pool_available():
        raise SavedReportError(
            "Saved reports require a database. Set DATABASE_URL to enable them."
        )


def _parse_id(report_id: str) -> uuid.UUID | None:
    """Return the UUID, or None if *report_id* is not a valid UUID."""
    try:
        return uuid.UUID(report_id)
    except (ValueError, TypeError):
        return None


def _row_to_report(row: asyncpg.Record) -> SavedReport:
    result = row["result"]
    if isinstance(result, str):  # defensive: only if the jsonb codec is absent
        result = json.loads(result)
    return SavedReport(
        id=str(row["id"]),
        address=row["address"],
        result=result,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def create_saved_report(
    user_id: str, address: str, result: dict[str, Any]
) -> SavedReport:
    """Persist a report snapshot for *user_id* and return the stored row."""
    _require_db()
    async with acquire_as_user(user_id) as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO public.saved_report (user_id, address, result)
            VALUES ($1, $2, $3)
            RETURNING id, address, result, created_at, updated_at
            """,
            uuid.UUID(user_id),
            address,
            result,
        )
    return _row_to_report(row)


async def list_saved_reports(user_id: str) -> list[SavedReport]:
    """Return the caller's saved reports, newest first (RLS scopes to the user)."""
    _require_db()
    async with acquire_as_user(user_id) as conn:
        rows = await conn.fetch(
            """
            SELECT id, address, result, created_at, updated_at
            FROM public.saved_report
            ORDER BY created_at DESC
            """
        )
    return [_row_to_report(r) for r in rows]


async def get_saved_report(user_id: str, report_id: str) -> SavedReport | None:
    """Return one saved report by id, or None if it does not exist for this user."""
    _require_db()
    rid = _parse_id(report_id)
    if rid is None:
        return None
    async with acquire_as_user(user_id) as conn:
        row = await conn.fetchrow(
            """
            SELECT id, address, result, created_at, updated_at
            FROM public.saved_report
            WHERE id = $1
            """,
            rid,
        )
    return _row_to_report(row) if row is not None else None


async def delete_saved_report(user_id: str, report_id: str) -> bool:
    """Delete one saved report. Returns True if a row was deleted, else False."""
    _require_db()
    rid = _parse_id(report_id)
    if rid is None:
        return False
    async with acquire_as_user(user_id) as conn:
        status = await conn.execute(
            "DELETE FROM public.saved_report WHERE id = $1",
            rid,
        )
    # asyncpg returns the command tag, e.g. "DELETE 1" / "DELETE 0".
    return status.rsplit(" ", 1)[-1] != "0"
