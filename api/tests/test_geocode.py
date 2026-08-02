"""Tests for the /geocode endpoint and geocoder service.

Integration-style tests use FastAPI's TestClient (sync) to exercise the full
request/response cycle. The Census Geocoder is mocked at the httpx.AsyncClient
level so tests run offline and deterministically.

Unit tests for _parse_response exercise the parsing logic directly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.geocoder import GeocoderError, NoMatchError, _parse_response

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixtures: realistic Census Geocoder payloads
# ---------------------------------------------------------------------------

_MATCH_RESPONSE = {
    "result": {
        "addressMatches": [
            {
                "matchedAddress": "1600 PENNSYLVANIA AVE NW, WASHINGTON, DC, 20500",
                "coordinates": {"x": -77.0366, "y": 38.8971},
                "geographies": {
                    "Census Tracts": [
                        {
                            "GEOID": "11001006202",
                            "NAME": "Census Tract 62.02",
                        }
                    ]
                },
            }
        ]
    }
}

_NO_MATCH_RESPONSE: dict = {"result": {"addressMatches": []}}

_NO_TRACT_RESPONSE = {
    "result": {
        "addressMatches": [
            {
                "matchedAddress": "SOME ROAD, SOMEWHERE, XX, 00000",
                "coordinates": {"x": -100.0, "y": 40.0},
                "geographies": {},  # Census Tracts key missing
            }
        ]
    }
}


def _mock_client(payload: dict) -> MagicMock:
    """Build an httpx.AsyncClient mock that returns *payload* as JSON."""
    mock_response = MagicMock()
    mock_response.json.return_value = payload
    mock_response.raise_for_status = MagicMock()

    mock_async_client = AsyncMock()
    mock_async_client.get = AsyncMock(return_value=mock_response)
    mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
    mock_async_client.__aexit__ = AsyncMock(return_value=None)

    mock_cls = MagicMock(return_value=mock_async_client)
    return mock_cls


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestGeocodeEndpoint:
    def test_valid_address_returns_200_with_coordinates_and_geoid(self) -> None:
        with patch("app.services.geocoder.httpx.AsyncClient", _mock_client(_MATCH_RESPONSE)):
            resp = client.post(
                "/geocode",
                json={"address": "1600 Pennsylvania Ave NW, Washington, DC"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["lat"] == pytest.approx(38.8971, abs=1e-4)
        assert body["lon"] == pytest.approx(-77.0366, abs=1e-4)
        assert body["tract_geoid"] == "11001006202"
        assert "PENNSYLVANIA" in body["matched_address"].upper()

    def test_no_match_returns_404(self) -> None:
        with patch("app.services.geocoder.httpx.AsyncClient", _mock_client(_NO_MATCH_RESPONSE)):
            resp = client.post("/geocode", json={"address": "zzz garbage address nobody"})

        assert resp.status_code == 404
        assert "No address match" in resp.json()["detail"]

    def test_blank_address_returns_422(self) -> None:
        resp = client.post("/geocode", json={"address": ""})
        assert resp.status_code == 422

    def test_missing_address_field_returns_422(self) -> None:
        resp = client.post("/geocode", json={})
        assert resp.status_code == 422

    def test_address_too_short_returns_422(self) -> None:
        # min_length is 5
        resp = client.post("/geocode", json={"address": "123"})
        assert resp.status_code == 422

    def test_address_too_long_returns_422(self) -> None:
        resp = client.post("/geocode", json={"address": "x" * 501})
        assert resp.status_code == 422

    def test_geocoder_unavailable_returns_503(self) -> None:
        # Simulate a connection error on every attempt
        failing_client = AsyncMock()
        failing_client.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
        failing_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls = MagicMock(return_value=failing_client)

        with patch("app.services.geocoder.httpx.AsyncClient", mock_cls):
            resp = client.post("/geocode", json={"address": "123 Main St, Springfield, IL"})

        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Parser unit tests (no HTTP involved)
# ---------------------------------------------------------------------------


class TestParseResponse:
    def test_extracts_coordinates_and_geoid(self) -> None:
        result = _parse_response(_MATCH_RESPONSE, "test address")
        assert result.lat == pytest.approx(38.8971, abs=1e-4)
        assert result.lon == pytest.approx(-77.0366, abs=1e-4)
        assert result.tract_geoid == "11001006202"
        assert result.matched_address == "1600 PENNSYLVANIA AVE NW, WASHINGTON, DC, 20500"

    def test_empty_matches_raises_no_match_error(self) -> None:
        with pytest.raises(NoMatchError):
            _parse_response(_NO_MATCH_RESPONSE, "garbage")

    def test_missing_census_tracts_raises_geocoder_error(self) -> None:
        with pytest.raises(GeocoderError):
            _parse_response(_NO_TRACT_RESPONSE, "some road")
