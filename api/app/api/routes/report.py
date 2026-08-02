"""POST /report — the full source-traceable risk report for an address.

Sprint 4 endpoint. Assembles the whole pipeline in one call:
  geocode -> flood zone + NRI per-peril scores -> documented composite score.

This is the single call the frontend uses to render the risk report, and the
shape Sprint 5 will persist as a saved report.

Error contract:
  422  address fails validation (Pydantic)
  404  address could not be geocoded (no match)
  503  geocoder unreachable/timed out
Flood and NRI are best-effort: if either is unavailable those sections are
returned as null rather than failing the whole report.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.geocoder import GeocoderError, NoMatchError
from app.services.report import build_report

router = APIRouter(prefix="/report", tags=["report"])


class ReportRequest(BaseModel):
    address: str = Field(
        min_length=5,
        max_length=500,
        examples=["1600 Pennsylvania Ave NW, Washington, DC"],
        description="A US street address, ideally including city and state.",
    )


class GeocodePart(BaseModel):
    lat: float
    lon: float
    tract_geoid: str
    matched_address: str


class FloodPart(BaseModel):
    zone_code: str
    flood_tier: str
    description: str
    geometry: dict = Field(default_factory=dict)


class PerilPart(BaseModel):
    name: str
    code: str
    score: float | None
    eal_usd: float | None
    tier: str


class NriPart(BaseModel):
    composite_score: float | None
    eal_total_usd: float | None
    perils: list[PerilPart]
    source: str


class ContributionPart(BaseModel):
    code: str
    name: str
    score: float | None
    weight: float
    contribution: float | None = Field(
        description="score * normalised weight; contributions sum to composite_score"
    )


class CompositePart(BaseModel):
    composite_score: float | None = Field(
        description="0-100 weighted average of region-relevant NRI perils"
    )
    composite_tier: str
    overall_tier: str = Field(
        description="More severe of composite_tier and flood_tier"
    )
    flood_tier: str
    flood_is_sfha: bool = Field(
        description="True if the point is in a FEMA Special Flood Hazard Area"
    )
    weights: dict[str, float] = Field(description="Peril weights used (raw, pre-normalisation)")
    contributions: list[ContributionPart]
    methodology: str


class ReportResponse(BaseModel):
    address: str = Field(description="The address as submitted")
    geocode: GeocodePart
    flood: FloodPart | None = Field(default=None, description="Null if NFHL was unavailable")
    nri: NriPart | None = Field(default=None, description="Null if the NRI DB was unavailable")
    composite: CompositePart | None = Field(
        default=None, description="Null when NRI data is unavailable (nothing to score)"
    )


@router.post(
    "",
    response_model=ReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Full risk report for a US address",
)
async def report(body: ReportRequest) -> ReportResponse:
    """
    Return the complete, source-traceable risk report for a US address.

    Runs geocode -> (flood + NRI) -> composite scoring. Flood and NRI sections
    degrade to null if their upstream is unavailable; the composite is included
    only when NRI data exists. Every number carries its source and, for the
    composite, its per-peril weight and contribution.
    """
    try:
        result = await build_report(body.address)
    except NoMatchError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GeocoderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    geo = result.geocode
    flood = None
    if result.flood is not None:
        flood = FloodPart(
            zone_code=result.flood.zone_code,
            flood_tier=result.flood.flood_tier,
            description=result.flood.description,
            geometry=result.flood.geometry,
        )

    nri = None
    if result.nri is not None:
        nri = NriPart(
            composite_score=result.nri.composite_score,
            eal_total_usd=result.nri.eal_total_usd,
            perils=[
                PerilPart(
                    name=p.name, code=p.code, score=p.score, eal_usd=p.eal_usd, tier=p.tier
                )
                for p in result.nri.perils
            ],
            source=result.nri.source,
        )

    composite = None
    if result.composite is not None:
        c = result.composite
        composite = CompositePart(
            composite_score=c.composite_score,
            composite_tier=c.composite_tier,
            overall_tier=c.overall_tier,
            flood_tier=c.flood_tier,
            flood_is_sfha=c.flood_is_sfha,
            weights=c.weights,
            contributions=[
                ContributionPart(
                    code=pc.code,
                    name=pc.name,
                    score=pc.score,
                    weight=pc.weight,
                    contribution=pc.contribution,
                )
                for pc in c.contributions
            ],
            methodology=c.methodology,
        )

    return ReportResponse(
        address=body.address,
        geocode=GeocodePart(
            lat=geo.lat, lon=geo.lon, tract_geoid=geo.tract_geoid,
            matched_address=geo.matched_address,
        ),
        flood=flood,
        nri=nri,
        composite=composite,
    )
