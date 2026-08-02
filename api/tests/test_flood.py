"""Tests for the /flood endpoint and flood zone service.

The NFHL ArcGIS REST service is mocked at the httpx.AsyncClient level.
_classify_zone and _parse_response are tested directly as pure functions
so that the tier-mapping logic is fully covered without HTTP.

Golden addresses for manual verification against FEMA MSC
(https://msc.fema.gov/portal/search):
  - 1600 Pennsylvania Ave NW, DC → Zone X (Low)
  - 145 Pier Ave, Hermosa Beach, CA → Zone AE or VE (High)
  - 500 Canal St, New Orleans, LA → Zone AE (High)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.flood_zone import (
    _classify_zone,
    _parse_response,
)

client = TestClient(app)

# ---------------------------------------------------------------------------
# Sample NFHL GeoJSON payloads
# ---------------------------------------------------------------------------

_AE_RESPONSE = {
    "features": [
        {
            "properties": {
                "FLD_ZONE": "AE",
                "ZONE_SUBTY": None,
                "SFHA_TF": "T",
            },
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [[[-90.0, 29.9], [-90.1, 29.9], [-90.1, 30.0], [-90.0, 30.0], [-90.0, 29.9]]]
                ],
            },
        }
    ]
}

_X_UNSHADED_RESPONSE = {
    "features": [
        {
            "properties": {
                "FLD_ZONE": "X",
                "ZONE_SUBTY": None,
                "SFHA_TF": "F",
            },
            "geometry": {"type": "MultiPolygon", "coordinates": []},
        }
    ]
}

_X_SHADED_RESPONSE = {
    "features": [
        {
            "properties": {
                "FLD_ZONE": "X",
                "ZONE_SUBTY": "0.2 PCT ANNUAL CHANCE FLOOD HAZARD",
                "SFHA_TF": "F",
            },
            "geometry": {"type": "MultiPolygon", "coordinates": []},
        }
    ]
}

_VE_RESPONSE = {
    "features": [
        {
            "properties": {
                "FLD_ZONE": "VE",
                "ZONE_SUBTY": None,
                "SFHA_TF": "T",
            },
            "geometry": {"type": "MultiPolygon", "coordinates": []},
        }
    ]
}

_EMPTY_RESPONSE: dict = {"features": []}


def _mock_nfhl(payload: dict) -> MagicMock:
    """Build an httpx.AsyncClient mock returning *payload* as JSON."""
    mock_response = MagicMock()
    mock_response.json.return_value = payload
    mock_response.raise_for_status = MagicMock()

    mock_async_client = AsyncMock()
    mock_async_client.get = AsyncMock(return_value=mock_response)
    mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
    mock_async_client.__aexit__ = AsyncMock(return_value=None)

    return MagicMock(return_value=mock_async_client)


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestFloodEndpoint:
    def test_ae_zone_returns_high_tier(self) -> None:
        with patch("app.services.flood_zone.httpx.AsyncClient", _mock_nfhl(_AE_RESPONSE)):
            resp = client.get("/flood", params={"lat": 29.95, "lon": -90.07})

        assert resp.status_code == 200
        body = resp.json()
        assert body["zone_code"] == "AE"
        assert body["flood_tier"] == "High"
        assert "Special Flood Hazard" in body["description"]

    def test_x_unshaded_returns_low_tier(self) -> None:
        with patch("app.services.flood_zone.httpx.AsyncClient", _mock_nfhl(_X_UNSHADED_RESPONSE)):
            resp = client.get("/flood", params={"lat": 38.90, "lon": -77.04})

        assert resp.status_code == 200
        body = resp.json()
        assert body["zone_code"] == "X"
        assert body["flood_tier"] == "Low"

    def test_x_shaded_returns_moderate_tier(self) -> None:
        with patch("app.services.flood_zone.httpx.AsyncClient", _mock_nfhl(_X_SHADED_RESPONSE)):
            resp = client.get("/flood", params={"lat": 38.90, "lon": -77.04})

        assert resp.status_code == 200
        assert resp.json()["flood_tier"] == "Moderate"

    def test_ve_zone_returns_high_tier(self) -> None:
        with patch("app.services.flood_zone.httpx.AsyncClient", _mock_nfhl(_VE_RESPONSE)):
            resp = client.get("/flood", params={"lat": 33.75, "lon": -118.40})

        assert resp.status_code == 200
        assert resp.json()["flood_tier"] == "High"

    def test_unmapped_point_returns_low_tier(self) -> None:
        with patch("app.services.flood_zone.httpx.AsyncClient", _mock_nfhl(_EMPTY_RESPONSE)):
            resp = client.get("/flood", params={"lat": 40.0, "lon": -100.0})

        assert resp.status_code == 200
        body = resp.json()
        assert body["zone_code"] == "UNMAPPED"
        assert body["flood_tier"] == "Low"

    def test_lat_out_of_range_returns_422(self) -> None:
        resp = client.get("/flood", params={"lat": 91.0, "lon": -77.0})
        assert resp.status_code == 422

    def test_lon_out_of_range_returns_422(self) -> None:
        resp = client.get("/flood", params={"lat": 38.9, "lon": 200.0})
        assert resp.status_code == 422

    def test_missing_lat_returns_422(self) -> None:
        resp = client.get("/flood", params={"lon": -77.0})
        assert resp.status_code == 422

    def test_service_unavailable_returns_503(self) -> None:
        failing = AsyncMock()
        failing.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
        failing.__aexit__ = AsyncMock(return_value=None)
        mock_cls = MagicMock(return_value=failing)

        with patch("app.services.flood_zone.httpx.AsyncClient", mock_cls):
            resp = client.get("/flood", params={"lat": 38.9, "lon": -77.0})

        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# _classify_zone unit tests (pure function, no HTTP)
# ---------------------------------------------------------------------------


class TestClassifyZone:
    @pytest.mark.parametrize("zone", ["A", "AE", "AH", "AO", "A99"])
    def test_a_zones_are_high(self, zone: str) -> None:
        tier, desc = _classify_zone(zone, "")
        assert tier == "High"
        assert "Special Flood Hazard" in desc

    @pytest.mark.parametrize("zone", ["V", "VE"])
    def test_v_zones_are_high(self, zone: str) -> None:
        tier, _ = _classify_zone(zone, "")
        assert tier == "High"

    def test_x_unshaded_is_low(self) -> None:
        tier, _ = _classify_zone("X", "")
        assert tier == "Low"

    def test_x_shaded_is_moderate(self) -> None:
        tier, _ = _classify_zone("X", "0.2 PCT ANNUAL CHANCE FLOOD HAZARD")
        assert tier == "Moderate"

    def test_zone_d_is_low(self) -> None:
        tier, _ = _classify_zone("D", "")
        assert tier == "Low"

    def test_empty_zone_is_low(self) -> None:
        tier, _ = _classify_zone("", "")
        assert tier == "Low"


# ---------------------------------------------------------------------------
# _parse_response unit tests
# ---------------------------------------------------------------------------


class TestParseResponse:
    def test_ae_feature_parsed_correctly(self) -> None:
        result = _parse_response(_AE_RESPONSE, 29.95, -90.07)
        assert result.zone_code == "AE"
        assert result.flood_tier == "High"
        assert result.geometry != {}

    def test_empty_features_returns_unmapped(self) -> None:
        result = _parse_response(_EMPTY_RESPONSE, 40.0, -100.0)
        assert result.zone_code == "UNMAPPED"
        assert result.flood_tier == "Low"
        assert result.geometry == {}
