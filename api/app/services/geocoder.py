"""
US Census Geocoder service.

Resolves a US address string to:
  - latitude / longitude (WGS-84)
  - 11-digit census tract GEOID — used to look up FEMA NRI scores in Sprint 3

Free, no API key required.
Docs: https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html

Design choices:
  - httpx.AsyncClient for async-native I/O; caller stays non-blocking.
  - Configurable timeout + one bounded retry (Settings.http_max_retries) to
    satisfy risk R4 (external-service resilience) without unbounded waits.
  - GeocoderError distinguishes "no match" from "service down" so the route
    can return 404 vs 503 respectively.
  - _parse_response is a pure function — easy to unit-test without HTTP.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_BENCHMARK = "Public_AR_Current"
_VINTAGE = "Current_Current"
_LAYERS = "Census Tracts"


@dataclass(frozen=True)
class GeocodeResult:
    lat: float
    lon: float
    tract_geoid: str
    matched_address: str


class GeocoderError(Exception):
    """Raised for caller-visible geocoding failures (no match, service down)."""


class NoMatchError(GeocoderError):
    """The address produced no results from the Census Geocoder."""


async def geocode_address(address: str) -> GeocodeResult:
    """
    Geocode *address* using the US Census Bureau's Geography API.

    Returns a :class:`GeocodeResult` with coordinates and census tract GEOID.
    Applies a configurable timeout and one retry before raising
    :class:`GeocoderError` with a descriptive message.
    """
    settings = get_settings()
    url = f"{settings.census_geocoder_url}/geographies/onelineaddress"
    params = {
        "address": address,
        "benchmark": _BENCHMARK,
        "vintage": _VINTAGE,
        "layers": _LAYERS,
        "format": "json",
    }

    last_exc: Exception | None = None
    attempts = settings.http_max_retries + 1

    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return _parse_response(response.json(), address)
        except (NoMatchError, GeocoderError):
            # No-match is not a transient error — do not retry.
            raise
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Census Geocoder attempt %d/%d failed for %r: %s",
                attempt + 1,
                attempts,
                address,
                exc,
            )

    raise GeocoderError(
        f"Census Geocoder unavailable after {attempts} attempt(s)"
    ) from last_exc


# ---------------------------------------------------------------------------
# Internal parser (pure function, separately testable)
# ---------------------------------------------------------------------------

def _parse_response(data: dict, original_address: str) -> GeocodeResult:
    """Extract coordinates and census tract GEOID from a Census Geocoder response."""
    matches = data.get("result", {}).get("addressMatches", [])

    if not matches:
        raise NoMatchError(
            f"No address match found for: {original_address!r}. "
            "Check the address format — try including city and state."
        )

    match = matches[0]
    coords = match["coordinates"]

    tracts = match.get("geographies", {}).get("Census Tracts", [])
    if not tracts:
        raise GeocoderError(
            f"Address matched but census tract unavailable for: {original_address!r}"
        )

    return GeocodeResult(
        lat=float(coords["y"]),
        lon=float(coords["x"]),
        tract_geoid=tracts[0]["GEOID"],
        matched_address=match.get("matchedAddress", original_address),
    )
