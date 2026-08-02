"""Unit tests for the composite scoring function (pure, no I/O)."""

from __future__ import annotations

import pytest

from app.core.config import DEFAULT_PERIL_WEIGHTS
from app.services.scoring import REGIONAL_PERILS, compute_composite

# A simple two-peril weight set makes the arithmetic easy to verify by hand.
_SIMPLE_WEIGHTS = {"HAIL": 0.5, "SWND": 0.5}


class TestCompositeMath:
    def test_weighted_average_of_available_perils(self) -> None:
        result = compute_composite({"HAIL": 80.0, "SWND": 40.0}, "Low", _SIMPLE_WEIGHTS)
        assert result.composite_score == pytest.approx(60.0)  # 80*.5 + 40*.5
        assert result.composite_tier == "High"

    def test_missing_peril_is_renormalised_not_zero(self) -> None:
        # SWND has no data → composite should be 80 (HAIL alone), not 40.
        result = compute_composite({"HAIL": 80.0, "SWND": None}, "Low", _SIMPLE_WEIGHTS)
        assert result.composite_score == pytest.approx(80.0)

    def test_contributions_sum_to_composite(self) -> None:
        result = compute_composite(
            {"HAIL": 70.0, "SWND": 30.0, "RFLD": 50.0}, "Low", DEFAULT_PERIL_WEIGHTS
        )
        total = sum(c.contribution for c in result.contributions if c.contribution is not None)
        assert total == pytest.approx(result.composite_score, abs=0.05)

    def test_no_data_gives_none_and_unknown(self) -> None:
        empty = {code: None for code, _ in REGIONAL_PERILS}
        result = compute_composite(empty, "Low", DEFAULT_PERIL_WEIGHTS)
        assert result.composite_score is None
        assert result.composite_tier == "Unknown"

    def test_all_regional_perils_present_in_contributions(self) -> None:
        result = compute_composite({"HAIL": 50.0}, "Low", DEFAULT_PERIL_WEIGHTS)
        assert len(result.contributions) == len(REGIONAL_PERILS)


class TestFloodModifier:
    def test_flood_high_lifts_overall_above_low_composite(self) -> None:
        # Low composite but the property is in an SFHA → overall must be High.
        result = compute_composite({"HAIL": 5.0, "SWND": 5.0}, "High", _SIMPLE_WEIGHTS)
        assert result.composite_tier == "Low"
        assert result.overall_tier == "High"
        assert result.flood_is_sfha is True

    def test_high_composite_low_flood_stays_high(self) -> None:
        result = compute_composite({"HAIL": 90.0, "SWND": 90.0}, "Low", _SIMPLE_WEIGHTS)
        assert result.overall_tier == "High"
        assert result.flood_is_sfha is False

    def test_flood_not_blended_into_composite_score(self) -> None:
        # The composite number itself must be identical regardless of flood tier.
        low = compute_composite({"HAIL": 40.0, "SWND": 40.0}, "Low", _SIMPLE_WEIGHTS)
        high = compute_composite({"HAIL": 40.0, "SWND": 40.0}, "High", _SIMPLE_WEIGHTS)
        assert low.composite_score == high.composite_score

    def test_unknown_flood_tier_is_handled(self) -> None:
        result = compute_composite({"HAIL": 60.0, "SWND": 60.0}, "Unknown", _SIMPLE_WEIGHTS)
        assert result.overall_tier == "High"  # driven by composite; flood unknown
        assert result.flood_is_sfha is False


class TestWeightsEchoed:
    def test_weights_returned_for_all_regional_perils(self) -> None:
        result = compute_composite({"HAIL": 50.0}, "Low", DEFAULT_PERIL_WEIGHTS)
        for code, _ in REGIONAL_PERILS:
            assert code in result.weights
