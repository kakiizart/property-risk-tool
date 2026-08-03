"""/reports — create, list, fetch, and delete a user's saved risk reports.

Sprint 5 endpoints. Every route requires a valid Supabase access token
(:data:`app.api.deps.CurrentUserDep`). Row isolation is enforced in the database
via RLS (:func:`app.db.acquire_as_user`); the service layer additionally scopes
every query to the authenticated user.

``POST /reports`` re-runs the report pipeline server-side from the address, so
the stored snapshot is authentic (server-computed) rather than client-supplied,
and is byte-for-byte the shape of a live ``POST /report`` (shared mapping).

Error contract:
  401  missing / invalid / expired token
  404  address could not be geocoded (POST) or report id not found (GET/DELETE)
  422  request body/path fails validation
  503  geocoder unreachable (POST) or saved-report storage not configured
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep
from app.api.routes.report import ReportResponse, build_report_response
from app.services.geocoder import GeocoderError, NoMatchError
from app.services.report import build_report
from app.services.saved_reports import (
    SavedReport,
    SavedReportError,
    create_saved_report,
    delete_saved_report,
    get_saved_report,
    list_saved_reports,
)

router = APIRouter(prefix="/reports", tags=["saved reports"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class SaveReportRequest(BaseModel):
    address: str = Field(
        min_length=5,
        max_length=500,
        examples=["1600 Pennsylvania Ave NW, Washington, DC"],
        description="A US street address to build and save a risk report for.",
    )


class SavedReportSummary(BaseModel):
    """Lightweight list item — no full snapshot, for the saved-reports list."""

    id: str
    address: str
    overall_tier: str | None = Field(
        default=None, description="Overall risk tier from the saved snapshot, if scored"
    )
    created_at: datetime


class SavedReportDetail(BaseModel):
    """A saved report with its full, typed risk-report snapshot."""

    id: str
    address: str
    created_at: datetime
    updated_at: datetime
    result: ReportResponse


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------
def _to_detail(r: SavedReport) -> SavedReportDetail:
    return SavedReportDetail(
        id=r.id,
        address=r.address,
        created_at=r.created_at,
        updated_at=r.updated_at,
        result=ReportResponse.model_validate(r.result),
    )


def _to_summary(r: SavedReport) -> SavedReportSummary:
    overall = None
    composite = r.result.get("composite") if isinstance(r.result, dict) else None
    if isinstance(composite, dict):
        overall = composite.get("overall_tier")
    return SavedReportSummary(
        id=r.id, address=r.address, overall_tier=overall, created_at=r.created_at
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post(
    "",
    response_model=SavedReportDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Build and save a risk report for the current user",
)
async def save_report(body: SaveReportRequest, user: CurrentUserDep) -> SavedReportDetail:
    """Build a fresh report for *address* and persist it as the user's snapshot."""
    try:
        result = await build_report(body.address)
    except NoMatchError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GeocoderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    response = build_report_response(body.address, result)
    try:
        saved = await create_saved_report(user.id, body.address, response.model_dump())
    except SavedReportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return _to_detail(saved)


@router.get(
    "",
    response_model=list[SavedReportSummary],
    summary="List the current user's saved reports",
)
async def list_reports(user: CurrentUserDep) -> list[SavedReportSummary]:
    """Return the caller's saved reports (newest first)."""
    try:
        reports = await list_saved_reports(user.id)
    except SavedReportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return [_to_summary(r) for r in reports]


@router.get(
    "/{report_id}",
    response_model=SavedReportDetail,
    summary="Fetch one saved report by id",
)
async def get_report(report_id: str, user: CurrentUserDep) -> SavedReportDetail:
    """Return one of the caller's saved reports, or 404 if it isn't theirs."""
    try:
        report = await get_saved_report(user.id, report_id)
    except SavedReportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved report not found."
        )
    return _to_detail(report)


@router.delete(
    "/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one saved report by id",
)
async def delete_report(report_id: str, user: CurrentUserDep) -> Response:
    """Delete one of the caller's saved reports; 404 if it isn't theirs."""
    try:
        deleted = await delete_saved_report(user.id, report_id)
    except SavedReportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved report not found."
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
