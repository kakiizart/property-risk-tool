"""
Composite risk scoring — the documented scoring function.

This is the one place the app *derives* a number rather than surfacing an
authoritative one, so it is deliberately transparent (see docs/methodology.md):

  - The composite is a **weighted average of the region-relevant NRI peril
    scores** (0-100). Weights live in config and are region-tunable.
  - Weights are **normalised over the perils that actually have data** for a
    tract, so a missing peril doesn't silently drag the score toward zero.
  - **Flood is never blended in.** FEMA Special-Flood-Hazard-Area status is a
    hard fact for insurers, so it is carried as a separate tier and only used
    as a *called-out modifier* on the overall assessment.
  - Every input, weight, and per-peril contribution is returned so the number
    can be traced end to end.

Pure functions only — no I/O — so the whole thing is unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.nri import score_to_tier

# Region-relevant perils and their display names, in the order shown to users.
# Codes are FEMA NRI hazard codes (keys in the nri_tract.peril_scores JSONB).
REGIONAL_PERILS: list[tuple[str, str]] = [
    ("RFLD", "Riverine Flooding"),
    ("SWND", "Strong Wind"),
    ("HAIL", "Hail"),
    ("TRND", "Tornado"),
    ("WNTW", "Winter Weather"),
    ("ISTM", "Ice Storm"),
]

# Severity ranking so we can take the more-severe of two tiers.
_TIER_RANK = {"Low": 1, "Moderate": 2, "High": 3}


@dataclass(frozen=True)
class PerilContribution:
    code: str
    name: str
    score: float | None          # raw 0-100 NRI score (None if no data)
    weight: float                # configured (raw) weight for this peril
    contribution: float | None   # score * normalised weight; sums to composite


@dataclass(frozen=True)
class CompositeResult:
    composite_score: float | None   # 0-100 weighted average of regional perils
    composite_tier: str             # High / Moderate / Low / Unknown
    overall_tier: str               # more severe of composite_tier and flood_tier
    flood_tier: str                 # echoed FEMA flood tier (the hard fact)
    flood_is_sfha: bool             # True if in a Special Flood Hazard Area
    weights: dict[str, float] = field(default_factory=dict)
    contributions: list[PerilContribution] = field(default_factory=list)
    methodology: str = (
        "Weighted average of region-relevant FEMA NRI peril scores (weights "
        "normalised over available perils); FEMA flood tier carried separately "
        "as a called-out modifier. See docs/methodology.md."
    )


def _more_severe(a: str, b: str) -> str:
    """Return the more severe of two tiers (High > Moderate > Low)."""
    return a if _TIER_RANK.get(a, 0) >= _TIER_RANK.get(b, 0) else b


def compute_composite(
    peril_scores: dict[str, float | None],
    flood_tier: str,
    weights: dict[str, float],
) -> CompositeResult:
    """
    Compute the composite risk result from NRI peril scores and the flood tier.

    Args:
        peril_scores: mapping of NRI hazard code -> 0-100 score (or None).
        flood_tier:   FEMA flood tier ("High" | "Moderate" | "Low" | anything
                      else, treated as unknown severity).
        weights:      configured raw weights per peril code.

    Weights are normalised over the perils that both appear in `weights` and
    have a non-None score, so the composite is a true weighted average of the
    available data.
    """
    # Perils that have data AND a configured weight drive the composite.
    available = {
        code: score
        for code, score in peril_scores.items()
        if score is not None and weights.get(code, 0) > 0
    }
    total_weight = sum(weights[code] for code in available)

    composite: float | None = None
    if total_weight > 0:
        composite = round(
            sum(score * (weights[code] / total_weight) for code, score in available.items()),
            1,
        )

    contributions: list[PerilContribution] = []
    for code, name in REGIONAL_PERILS:
        score = peril_scores.get(code)
        weight = weights.get(code, 0.0)
        contribution: float | None = None
        if score is not None and code in available and total_weight > 0:
            contribution = round(score * (weight / total_weight), 2)
        contributions.append(
            PerilContribution(
                code=code,
                name=name,
                score=score,
                weight=weight,
                contribution=contribution,
            )
        )

    composite_tier = score_to_tier(composite)
    normalised_flood_tier = flood_tier if flood_tier in _TIER_RANK else "Unknown"
    overall_tier = _more_severe(composite_tier, normalised_flood_tier)

    return CompositeResult(
        composite_score=composite,
        composite_tier=composite_tier,
        overall_tier=overall_tier,
        flood_tier=flood_tier,
        flood_is_sfha=(flood_tier == "High"),
        weights={code: weights.get(code, 0.0) for code, _ in REGIONAL_PERILS},
        contributions=contributions,
    )
