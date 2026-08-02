"""Tests for the POST /report endpoint and report assembly.

The three upstream services (geocode, flood, NRI) are mocked at the
app.services.report module level so the assembly + degradation logic is
exercised without HTTP or a database.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.flood_zone import FloodZoneResult
from app.services.geocoder import GeocoderError, GeocodeResult, NoMatchError
from app.services.nri import NriResult, PerilScore

client = TestClient(app)

_GEO = GeocodeResult(
    lat=42.1342, lon=-80.0885, tract_geoid="42049000300",
    matched_address="100 STATE ST, ERIE, PA, 16507",
)
_FLOOD = FloodZoneResult(
    zone_code="X", flood_tier="Low", description="Zone X (unshaded): minimal.", geometry={},
)


def _nri(**overrides) -> NriResult:
    perils = [
        PerilScore("Riverine Flooding", "RFLD", 30.0, 90_000.0, "Moderate"),
        PerilScore("Strong Wind", "SWND", 45.0, 190_000.0, "Moderate"),
        PerilScore("Hail", "HAIL", 55.0, 220_000.0, "High"),
        PerilScore("Tornado", "TRND", 50.0, 160_000.0, "High"),
        PerilScore("Winter Weather", "WNTW", 75.0, 260_000.0, "High"),
        PerilScore("Ice Storm", "ISTM", 70.0, 210_000.0, "High"),
    ]
    kwargs = dict(
        tract_geoid="42049000300", composite_score=41.7,
        eal_total_usd=1_180_000.0, perils=perils,
    )
    kwargs.update(overrides)
    return NriResult(**kwargs)


def _patch(geo=None, geo_exc=None, flood=_FLOOD, flood_exc=None, nri=None, nri_exc=None):
    """Build patchers for the three report dependencies."""
    g = AsyncMock(side_effect=geo_exc) if geo_exc else AsyncMock(return_value=geo or _GEO)
    f = AsyncMock(side_effect=flood_exc) if flood_exc else AsyncMock(return_value=flood)
    n = AsyncMock(side_effect=nri_exc) if nri_exc else AsyncMock(return_value=nri or _nri())
    return (
        patch("app.services.report.geocode_address", g),
        patch("app.services.report.get_flood_zone", f),
        patch("app.services.report.get_nri_scores", n),
    )


class TestReportSuccess:
    def test_full_report_has_all_sections(self) -> None:
        p1, p2, p3 = _patch()
        with p1, p2, p3:
            resp = client.post("/report", json={"address": "100 State St, Erie, PA"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["geocode"]["tract_geoid"] == "42049000300"
        assert body["flood"]["flood_tier"] == "Low"
        assert body["nri"]["tract_geoid"] == "42049000300"
        assert body["nri"]["composite_score"] == 41.7
        assert body["composite"] is not None

    def test_composite_is_weighted_average_and_traceable(self) -> None:
        p1, p2, p3 = _patch()
        with p1, p2, p3:
            body = client.post("/report", json={"address": "100 State St, Erie, PA"}).json()
        comp = body["composite"]
        assert comp["composite_score"] is not None
        # contributions sum to the composite (traceability)
        total = sum(
            c["contribution"] for c in comp["contributions"] if c["contribution"] is not None
        )
        assert abs(total - comp["composite_score"]) < 0.1
        assert len(comp["contributions"]) == 6

    def test_flood_high_lifts_overall_tier(self) -> None:
        high_flood = FloodZoneResult("AE", "High", "SFHA", {})
        p1, p2, p3 = _patch(flood=high_flood)
        with p1, p2, p3:
            body = client.post("/report", json={"address": "somewhere coastal, FL"}).json()
        assert body["composite"]["flood_is_sfha"] is True
        assert body["composite"]["overall_tier"] == "High"


class TestReportDegradation:
    def test_nri_unavailable_returns_null_nri_and_composite(self) -> None:
        p1, p2, p3 = _patch(nri_exc=Exception("db down"))
        with p1, p2, p3:
            resp = client.post("/report", json={"address": "100 State St, Erie, PA"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["nri"] is None
        assert body["composite"] is None       # nothing to score
        assert body["flood"] is not None        # flood still present

    def test_flood_unavailable_still_scores_with_unknown_flood(self) -> None:
        p1, p2, p3 = _patch(flood_exc=Exception("nfhl down"))
        with p1, p2, p3:
            body = client.post("/report", json={"address": "100 State St, Erie, PA"}).json()
        assert body["flood"] is None
        assert body["composite"] is not None
        assert body["composite"]["flood_tier"] == "Unknown"


class TestReportErrors:
    def test_no_match_returns_404(self) -> None:
        p1, p2, p3 = _patch(geo_exc=NoMatchError("no match"))
        with p1, p2, p3:
            resp = client.post("/report", json={"address": "zzz not an address"})
        assert resp.status_code == 404

    def test_geocoder_down_returns_503(self) -> None:
        p1, p2, p3 = _patch(geo_exc=GeocoderError("service down"))
        with p1, p2, p3:
            resp = client.post("/report", json={"address": "100 State St, Erie, PA"})
        assert resp.status_code == 503

    def test_blank_address_returns_422(self) -> None:
        resp = client.post("/report", json={"address": ""})
        assert resp.status_code == 422
