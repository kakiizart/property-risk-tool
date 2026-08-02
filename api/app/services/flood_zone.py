"""
FEMA National Flood Hazard Layer (NFHL) service.

Queries the FEMA NFHL public ArcGIS MapServer to determine the authoritative
flood zone for a lat/lon point.  Returns the zone code (e.g. "AE", "X") and
maps it to a human-readable tier (High / Moderate / Low).

Endpoint:
  https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query
  Layer 28 = "S_FLD_HAZ_AR" (Flood Hazard Areas)

Free, no API key required.
Docs: https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer

Design choices:
  - Same timeout + retry pattern as the geocoder (R4 mitigation).
  - Returns geometry so the frontend can draw the containing flood polygon.
  - Flood tier is intentionally NOT blended into a composite score — insurers
    treat SFHA status as a hard fact, not a weighted input.
  - _parse_response is pure → unit-testable without HTTP.

Flood zone tier mapping (source: FEMA FIRM zone definitions):
  High   — Special Flood Hazard Area (SFHA); 1% annual chance (100-year flood)
           Zones: A, AE, AH, AO, AR, A99, V, VE
  Moderate — 0.2% annual chance (500-year flood); shaded Zone X
  Low    — Minimal / undetermined flood hazard; unshaded Zone X, Zone D
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# NFHL MapServer layer 28 = S_FLD_HAZ_AR (Flood Hazard Areas)
_LAYER_ID = 28

# SFHA zone prefixes — treated as High tier
_SFHA_PREFIXES = ("A", "V")

# Moderate-risk zone identifiers
_MODERATE_ZONES = {"X (SHADED)", "X500", "0.2 PCT ANNUAL CHANCE FLOOD HAZARD"}


@dataclass(frozen=True)
class FloodZoneResult:
    zone_code: str                          # e.g. "AE", "X", "VE"
    flood_tier: str                         # "High" | "Moderate" | "Low"
    description: str                        # human-readable zone description
    geometry: dict = field(default_factory=dict)  # GeoJSON polygon (may be empty)


class FloodZoneError(Exception):
    """Raised for caller-visible flood zone lookup failures."""


async def get_flood_zone(lat: float, lon: float) -> FloodZoneResult:
    """
    Return the authoritative FEMA flood zone for a lat/lon point.

    Applies the same timeout + retry policy as the geocoder service.
    Raises :class:`FloodZoneError` if the service is unreachable; returns a
    result with zone_code "UNKNOWN" if the point falls outside mapped areas.
    """
    settings = get_settings()
    url = f"{settings.nfhl_mapserver_url}/{_LAYER_ID}/query"
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }

    last_exc: Exception | None = None
    attempts = settings.http_max_retries + 1

    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return _parse_response(response.json(), lat, lon)
        except FloodZoneError:
            raise
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "NFHL attempt %d/%d failed for (%.5f, %.5f): %s",
                attempt + 1,
                attempts,
                lat,
                lon,
                exc,
            )

    raise FloodZoneError(
        f"FEMA NFHL service unavailable after {attempts} attempt(s)"
    ) from last_exc


# ---------------------------------------------------------------------------
# Internal helpers (pure functions — unit-testable without HTTP)
# ---------------------------------------------------------------------------

def _parse_response(data: dict, lat: float, lon: float) -> FloodZoneResult:
    """Extract zone code, tier, and geometry from a NFHL GeoJSON response."""
    features = data.get("features", [])

    if not features:
        # Point outside mapped flood areas — treated as minimal hazard.
        return FloodZoneResult(
            zone_code="UNMAPPED",
            flood_tier="Low",
            description="Area not mapped by FEMA; flood risk may exist but is undetermined.",
            geometry={},
        )

    # Use the first (highest-priority) feature.
    feature = features[0]
    props = feature.get("properties", {})
    geom = feature.get("geometry", {})

    zone_code = (props.get("FLD_ZONE") or "").strip().upper()
    subtype = (props.get("ZONE_SUBTY") or "").strip().upper()

    tier, description = _classify_zone(zone_code, subtype)

    return FloodZoneResult(
        zone_code=zone_code or "UNKNOWN",
        flood_tier=tier,
        description=description,
        geometry=geom,
    )


def _classify_zone(zone_code: str, subtype: str) -> tuple[str, str]:
    """Map a FEMA flood zone code to a (tier, description) pair."""

    if not zone_code or zone_code == "UNKNOWN":
        return "Low", "Flood zone unknown or unmapped."

    # Special Flood Hazard Area (SFHA) — 1% annual chance
    if zone_code.startswith("V") or zone_code in ("VE",):
        return (
            "High",
            f"Zone {zone_code}: Coastal high-hazard area, 1% annual chance flood "
            "(Special Flood Hazard Area). Flood insurance typically required "
            "for federally backed mortgages.",
        )

    if zone_code.startswith("A"):
        return (
            "High",
            f"Zone {zone_code}: Special Flood Hazard Area, 1% annual chance flood. "
            "Flood insurance typically required for federally backed mortgages.",
        )

    # Zone X — moderate or minimal depending on subtype
    if zone_code == "X":
        if subtype in ("0.2 PCT ANNUAL CHANCE FLOOD HAZARD", "SHADED"):
            return (
                "Moderate",
                "Zone X (shaded): 0.2% annual chance flood hazard (500-year flood). "
                "Flood insurance is not federally required but is recommended.",
            )
        return (
            "Low",
            "Zone X (unshaded): Minimal flood hazard, outside the 500-year floodplain. "
            "Flood insurance is not federally required.",
        )

    # Zone D — undetermined
    if zone_code == "D":
        return "Low", "Zone D: Undetermined flood hazard. Risk may exist but has not been studied."

    # Catch-all for less common zones
    return "Low", f"Zone {zone_code}: Refer to FEMA Flood Insurance Rate Map for details."
