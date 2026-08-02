"""GET /nri — returns FEMA NRI risk scores for a census tract GEOID.

Sprint 3 endpoint. Takes the tract_geoid from POST /geocode and returns
per-peril 0–100 risk scores and Expected Annual Loss from the local PostGIS
database populated by scripts/etl_nri.py.

Error contract:
  422  tract_geoid fails validation (Pydantic)
  404  no NRI record found for this GEOID (tract may be outside NRI coverage)
  503  database not configured (DATABASE_URL not set / pool not initialised)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.services.nri import NriError, get_nri_scores

router = APIRouter(prefix="/nri", tags=["nri"])


class PerilScoreOut(BaseModel):
    name: str = Field(description="Human-readable peril name", examples=["Strong Wind"])
    code: str = Field(description="NRI hazard code", examples=["SWND"])
    score: float | None = Field(
        description="NRI relative risk score 0–100 (null if no data for this tract)",
        examples=[45.2],
    )
    eal_usd: float | None = Field(
        description="Expected Annual Loss in USD (null if no data)",
        examples=[1234.56],
    )
    tier: str = Field(
        description="Risk tier: High (≥50), Moderate (25–49), Low (<25), Unknown",
        examples=["Moderate"],
    )


class NriResponse(BaseModel):
    tract_geoid: str = Field(
        description="11-digit census tract GEOID",
        examples=["11001006202"],
    )
    composite_score: float | None = Field(
        description="NRI composite risk score 0–100 across all hazards",
        examples=[38.4],
    )
    eal_total_usd: float | None = Field(
        description="Total Expected Annual Loss across all hazards, in USD",
        examples=[52381.00],
    )
    perils: list[PerilScoreOut] = Field(
        description="Per-peril breakdown for the region-relevant hazard set"
    )
    source: str = Field(
        description="Data source citation",
        examples=["FEMA National Risk Index v1.20"],
    )


@router.get(
    "",
    response_model=NriResponse,
    status_code=status.HTTP_200_OK,
    summary="Get FEMA NRI scores for a census tract",
)
async def nri_scores(
    tract_geoid: str = Query(
        ...,
        min_length=11,
        max_length=11,
        pattern=r"^\d{11}$",
        description="11-digit census tract GEOID (from POST /geocode)",
        examples=["11001006202"],
    ),
) -> NriResponse:
    """
    Return FEMA National Risk Index scores for a census tract.

    The tract GEOID comes from `POST /geocode`. Scores are loaded from
    the local PostGIS database by `scripts/etl_nri.py`.

    Each peril score is a 0–100 relative index where higher = greater risk.
    The Expected Annual Loss (EAL) is FEMA's annualised dollar estimate for
    that hazard type in the census tract — this is the number that maps most
    directly to how underwriters think about expected losses.

    **Methodology:** scores are sourced directly from FEMA NRI and are not
    invented or blended by this API. See `docs/methodology.md`.
    """
    try:
        result = await get_nri_scores(tract_geoid)
    except NriError as exc:
        msg = str(exc)
        if "No NRI record" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=msg
        ) from exc

    return NriResponse(
        tract_geoid=result.tract_geoid,
        composite_score=result.composite_score,
        eal_total_usd=result.eal_total_usd,
        perils=[
            PerilScoreOut(
                name=p.name,
                code=p.code,
                score=p.score,
                eal_usd=p.eal_usd,
                tier=p.tier,
            )
            for p in result.perils
        ],
        source=result.source,
    )
