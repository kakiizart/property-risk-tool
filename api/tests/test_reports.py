"""Tests for the /reports saved-report endpoints.

The saved_reports service and the report pipeline are mocked at the route
module level, so these exercise auth enforcement, request/response mapping, and
the error contract without a database or live external calls. RLS/isolation
itself is enforced in Postgres and is covered by the manual smoke test in
docs/security.md (no live DB in CI).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.routes.report import ReportResponse
from app.main import app
from app.services.geocoder import GeocoderError, NoMatchError
from app.services.saved_reports import SavedReport
from tests.conftest import USER_ID, auth_header

client = TestClient(app)

REPORT_ID = "99999999-8888-7777-6666-555555555555"

# A valid ReportResponse-shaped snapshot (what /report would return / persist).
SNAPSHOT: dict = {
    "address": "100 State St, Erie, PA",
    "geocode": {
        "lat": 42.1342,
        "lon": -80.0885,
        "tract_geoid": "42049000300",
        "matched_address": "100 STATE ST, ERIE, PA, 16507",
    },
    "flood": None,
    "nri": None,
    "composite": {
        "composite_score": 56.2,
        "composite_tier": "High",
        "overall_tier": "High",
        "flood_tier": "Low",
        "flood_is_sfha": False,
        "weights": {},
        "contributions": [],
        "methodology": "weighted average of region-relevant NRI perils",
    },
}


def _saved(**overrides) -> SavedReport:
    now = datetime(2026, 8, 3, tzinfo=timezone.utc)
    kwargs = dict(
        id=REPORT_ID,
        address="100 State St, Erie, PA",
        result=SNAPSHOT,
        created_at=now,
        updated_at=now,
    )
    kwargs.update(overrides)
    return SavedReport(**kwargs)


def _patch_build():
    """Patch the report pipeline so POST /reports doesn't need live services."""
    return (
        patch("app.api.routes.reports.build_report", AsyncMock(return_value=object())),
        patch(
            "app.api.routes.reports.build_report_response",
            return_value=ReportResponse.model_validate(SNAPSHOT),
        ),
    )


class TestSaveReport:
    def test_requires_auth(self) -> None:
        resp = client.post("/reports", json={"address": "100 State St, Erie, PA"})
        assert resp.status_code == 401

    def test_save_returns_201_with_snapshot(self, auth_configured) -> None:
        b1, b2 = _patch_build()
        with b1, b2, patch(
            "app.api.routes.reports.create_saved_report",
            AsyncMock(return_value=_saved()),
        ):
            resp = client.post(
                "/reports",
                json={"address": "100 State St, Erie, PA"},
                headers=auth_header(),
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == REPORT_ID
        assert body["result"]["composite"]["overall_tier"] == "High"
        assert body["result"]["geocode"]["tract_geoid"] == "42049000300"

    def test_save_scopes_to_authenticated_user(self, auth_configured) -> None:
        mock_create = AsyncMock(return_value=_saved())
        b1, b2 = _patch_build()
        with b1, b2, patch("app.api.routes.reports.create_saved_report", mock_create):
            client.post(
                "/reports",
                json={"address": "100 State St, Erie, PA"},
                headers=auth_header(),
            )
        # First positional arg to create_saved_report is the user id from the token.
        assert mock_create.await_args.args[0] == USER_ID

    def test_unmatched_address_returns_404(self, auth_configured) -> None:
        with patch(
            "app.api.routes.reports.build_report",
            AsyncMock(side_effect=NoMatchError("no match")),
        ):
            resp = client.post(
                "/reports", json={"address": "zzz not real"}, headers=auth_header()
            )
        assert resp.status_code == 404

    def test_geocoder_down_returns_503(self, auth_configured) -> None:
        with patch(
            "app.api.routes.reports.build_report",
            AsyncMock(side_effect=GeocoderError("service down")),
        ):
            resp = client.post(
                "/reports",
                json={"address": "100 State St, Erie, PA"},
                headers=auth_header(),
            )
        assert resp.status_code == 503

    def test_blank_address_returns_422(self, auth_configured) -> None:
        resp = client.post("/reports", json={"address": ""}, headers=auth_header())
        assert resp.status_code == 422


class TestListReports:
    def test_requires_auth(self) -> None:
        assert client.get("/reports").status_code == 401

    def test_list_returns_summaries_without_full_snapshot(self, auth_configured) -> None:
        with patch(
            "app.api.routes.reports.list_saved_reports",
            AsyncMock(return_value=[_saved()]),
        ):
            resp = client.get("/reports", headers=auth_header())
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["id"] == REPORT_ID
        assert body[0]["overall_tier"] == "High"
        assert "result" not in body[0]  # list items omit the heavy snapshot


class TestGetReport:
    def test_found_returns_detail(self, auth_configured) -> None:
        with patch(
            "app.api.routes.reports.get_saved_report",
            AsyncMock(return_value=_saved()),
        ):
            resp = client.get(f"/reports/{REPORT_ID}", headers=auth_header())
        assert resp.status_code == 200
        assert resp.json()["result"]["geocode"]["tract_geoid"] == "42049000300"

    def test_not_found_returns_404(self, auth_configured) -> None:
        with patch(
            "app.api.routes.reports.get_saved_report", AsyncMock(return_value=None)
        ):
            resp = client.get(
                "/reports/00000000-0000-0000-0000-000000000000", headers=auth_header()
            )
        assert resp.status_code == 404

    def test_requires_auth(self) -> None:
        assert client.get(f"/reports/{REPORT_ID}").status_code == 401


class TestDeleteReport:
    def test_delete_returns_204(self, auth_configured) -> None:
        with patch(
            "app.api.routes.reports.delete_saved_report", AsyncMock(return_value=True)
        ):
            resp = client.delete(f"/reports/{REPORT_ID}", headers=auth_header())
        assert resp.status_code == 204

    def test_delete_missing_returns_404(self, auth_configured) -> None:
        with patch(
            "app.api.routes.reports.delete_saved_report", AsyncMock(return_value=False)
        ):
            resp = client.delete(
                "/reports/00000000-0000-0000-0000-000000000000", headers=auth_header()
            )
        assert resp.status_code == 404

    def test_requires_auth(self) -> None:
        assert client.delete(f"/reports/{REPORT_ID}").status_code == 401
