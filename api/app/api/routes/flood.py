"""GET /flood — returns the FEMA flood zone for a lat/lon point.

Sprint 2 endpoint. Takes the coordinates produced by POST /geocode and queries
the FEMA National Flood Hazard Layer to return:
  - zone_code   (authoritative FEMA designation, e.g. "AE", "X")
  - flood_tier  (High | Moderate | Low — mapped from the zone code)
  - description (human-readable zone explanation)
  - geometry    (GeoJSON polygon of the flood zone — drawn on the map)

Error contract:
  422  lat/lon out of range (Pydantic)
  503  NFHL service unreachable or timed out
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.services.flood_zone import FloodZoneError, get_flood_zone

router = APIRouter(prefix="/flood", tags=["flood"])


class FloodZoneResponse(BaseModel):
    zone_code: str = Field(
        description="FEMA flood zone designation (e.g. AE, X, VE)",
        examples=["AE"],
    )
    flood_tier: str = Field(
        description="Risk tier: High (SFHA), Moderate (0.2%), or Low (minimal)",
        examples=["High"],
    )
    description: str = Field(
        description="Human-readable explanation of the flood zone",
    )
    geometry: dict = Field(
        description="GeoJSON geometry of the flood zone polygon (may be empty for unmapped areas)",
        default_factory=dict,
    )


@router.get(
    "",
    response_model=FloodZoneResponse,
    status_code=status.HTTP_200_OK,
    summary="Look up FEMA flood zone for a coordinate",
)
async def flood_zone(
    lat: float = Query(..., ge=-90, le=90, description="Latitude (WGS-84)"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude (WGS-84)"),
) -> FloodZoneResponse:
    """
    Return the authoritative FEMA flood zone for a lat/lon point.

    Queries the FEMA National Flood Hazard Layer (NFHL) ArcGIS MapServer
    using a point-in-polygon spatial query and maps the result to a risk tier.

    Use the **lat** and **lon** returned by `POST /geocode`.

    Flood tier values:
    - **High** — Special Flood Hazard Area (SFHA); 1% annual chance of flooding
    - **Moderate** — 0.2% annual chance (500-year flood); shaded Zone X
    - **Low** — Minimal flood hazard; outside the 500-year floodplain or unmapped
    """
    try:
        result = await get_flood_zone(lat, lon)
    except FloodZoneError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return FloodZoneResponse(
        zone_code=result.zone_code,
        flood_tier=result.flood_tier,
        description=result.description,
        geometry=result.geometry,
    )
