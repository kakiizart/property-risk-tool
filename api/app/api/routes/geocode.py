"""POST /geocode — resolves a US address to coordinates + census tract GEOID.

Sprint 1 endpoint. This is the entry point into the risk pipeline:
  address → coordinates + tract_geoid → (Sprint 2) flood zone
                                      → (Sprint 3) NRI per-peril scores

Error contract:
  422  address field fails Pydantic validation (blank, too short/long)
  404  Census Geocoder returned no address matches
  503  Census Geocoder unreachable or timed out
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.geocoder import GeocoderError, NoMatchError, geocode_address

router = APIRouter(prefix="/geocode", tags=["geocode"])


class GeocodeRequest(BaseModel):
    address: str = Field(
        min_length=5,
        max_length=500,
        examples=["1600 Pennsylvania Ave NW, Washington, DC"],
        description="A US street address, ideally including city and state.",
    )


class GeocodeResponse(BaseModel):
    lat: float = Field(description="Latitude (WGS-84)", examples=[38.8971])
    lon: float = Field(description="Longitude (WGS-84)", examples=[-77.0366])
    tract_geoid: str = Field(
        description="11-digit census tract GEOID used for NRI score lookup",
        examples=["11001006202"],
    )
    matched_address: str = Field(
        description="The standardised address returned by the Census Geocoder",
        examples=["1600 PENNSYLVANIA AVE NW, WASHINGTON, DC, 20500"],
    )


@router.post(
    "",
    response_model=GeocodeResponse,
    status_code=status.HTTP_200_OK,
    summary="Geocode a US address",
)
async def geocode(body: GeocodeRequest) -> GeocodeResponse:
    """
    Resolve a US address to WGS-84 coordinates and a census tract GEOID.

    The GEOID identifies the census tract whose FEMA NRI scores (Expected Annual
    Loss, per-peril 0–100 scores) are returned in Sprint 3. This endpoint is
    the first step of the full risk pipeline.

    - **address**: any reasonably formatted US street address with city/state.
    """
    try:
        result = await geocode_address(body.address)
    except NoMatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except GeocoderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return GeocodeResponse(
        lat=result.lat,
        lon=result.lon,
        tract_geoid=result.tract_geoid,
        matched_address=result.matched_address,
    )
