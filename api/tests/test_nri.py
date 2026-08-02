"""Tests for the /nri endpoint and NRI service.

The database pool is mocked at the app.db module level so tests run
without a real Postgres connection. The pure helpers (score_to_tier,
_build_peril_list) are tested directly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.nri import _build_peril_list, score_to_tier

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fake DB row (asyncpg Record-like mapping)
# ---------------------------------------------------------------------------

_FAKE_ROW = {
    "tract_geoid": "11001006202",
    "risk_score": 38.4,
    "eal_total": 52381.0,
    "peril_scores": {
        "SWND": {"score": 45.2, "eal": 12000.0},
        "HAIL": {"score": 67.8, "eal": 25000.0},
        "TRND": {"score": 12.1, "eal": 500.0},
        "WNTW": {"score": 55.0, "eal": 9000.0},
        "ISTM": {"score": 30.0, "eal": 3000.0},
        "RFLD": {"score": 8.0, "eal": 200.0},
        "HRCN": {"score": 0.0, "eal": 0.0},
        "LTNG": {"score": 22.0, "eal": 800.0},
        "CFLD": {"score": 5.0, "eal": 100.0},
    },
}


def _mock_db_with_row(row: dict | None):
    """
    Patch app.db so pool_available() returns True and get_pool() returns
    a mock pool whose acquire() context yields a conn with fetchrow returning *row*.
    """
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=row)

    mock_acquire = AsyncMock()
    mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire.__aexit__ = AsyncMock(return_value=None)

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_acquire)

    return (
        patch("app.services.nri.pool_available", return_value=True),
        patch("app.services.nri.get_pool", return_value=mock_pool),
    )


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestNriEndpoint:
    def test_valid_geoid_returns_scores(self) -> None:
        p1, p2 = _mock_db_with_row(_FAKE_ROW)
        with p1, p2:
            resp = client.get("/nri", params={"tract_geoid": "11001006202"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["tract_geoid"] == "11001006202"
        assert body["composite_score"] == pytest.approx(38.4, abs=0.01)
        assert body["eal_total_usd"] == pytest.approx(52381.0, abs=0.01)
        assert len(body["perils"]) == 9  # DISPLAYED_PERILS count

    def test_hail_score_is_high_tier(self) -> None:
        p1, p2 = _mock_db_with_row(_FAKE_ROW)
        with p1, p2:
            body = client.get("/nri", params={"tract_geoid": "11001006202"}).json()

        hail = next(p for p in body["perils"] if p["code"] == "HAIL")
        assert hail["score"] == pytest.approx(67.8, abs=0.01)
        assert hail["tier"] == "High"

    def test_rfld_score_is_low_tier(self) -> None:
        p1, p2 = _mock_db_with_row(_FAKE_ROW)
        with p1, p2:
            body = client.get("/nri", params={"tract_geoid": "11001006202"}).json()

        rfld = next(p for p in body["perils"] if p["code"] == "RFLD")
        assert rfld["tier"] == "Low"

    def test_tract_not_found_returns_404(self) -> None:
        p1, p2 = _mock_db_with_row(None)
        with p1, p2:
            resp = client.get("/nri", params={"tract_geoid": "99999999999"})

        assert resp.status_code == 404
        assert "No NRI record" in resp.json()["detail"]

    def test_db_not_configured_returns_503(self) -> None:
        with patch("app.services.nri.pool_available", return_value=False):
            resp = client.get("/nri", params={"tract_geoid": "11001006202"})

        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"].lower()

    def test_geoid_too_short_returns_422(self) -> None:
        resp = client.get("/nri", params={"tract_geoid": "1234567890"})
        assert resp.status_code == 422

    def test_geoid_wrong_format_returns_422(self) -> None:
        resp = client.get("/nri", params={"tract_geoid": "1100100620X"})
        assert resp.status_code == 422

    def test_missing_geoid_returns_422(self) -> None:
        resp = client.get("/nri")
        assert resp.status_code == 422

    def test_source_field_present(self) -> None:
        p1, p2 = _mock_db_with_row(_FAKE_ROW)
        with p1, p2:
            body = client.get("/nri", params={"tract_geoid": "11001006202"}).json()
        assert "FEMA" in body["source"]


# ---------------------------------------------------------------------------
# score_to_tier unit tests
# ---------------------------------------------------------------------------


class TestScoreToTier:
    @pytest.mark.parametrize("score,expected", [
        (50.0, "High"),
        (75.0, "High"),
        (100.0, "High"),
        (49.9, "Moderate"),
        (25.0, "Moderate"),
        (24.9, "Low"),
        (0.0, "Low"),
    ])
    def test_tier_boundaries(self, score: float, expected: str) -> None:
        assert score_to_tier(score) == expected

    def test_none_returns_unknown(self) -> None:
        assert score_to_tier(None) == "Unknown"


# ---------------------------------------------------------------------------
# _build_peril_list unit tests
# ---------------------------------------------------------------------------


class TestBuildPerilList:
    def test_known_codes_parsed(self) -> None:
        perils = _build_peril_list(_FAKE_ROW["peril_scores"])
        names = {p.code for p in perils}
        assert "SWND" in names
        assert "HAIL" in names

    def test_missing_code_returns_none_scores(self) -> None:
        perils = _build_peril_list({})  # empty — all perils missing
        for p in perils:
            assert p.score is None
            assert p.eal_usd is None
            assert p.tier == "Unknown"

    def test_all_displayed_perils_present(self) -> None:
        perils = _build_peril_list({})
        # Should still return all 9 displayed perils even with no data
        assert len(perils) == 9
