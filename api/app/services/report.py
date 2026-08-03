"""
Report assembly — orchestrates the full risk pipeline for one address.

Flow:
  address
    -> geocode                (US Census; required — failure aborts the report)
    -> flood zone + NRI       (FEMA NFHL + local DB; run concurrently, and each
                               degrades gracefully to None if unavailable)
    -> composite score        (documented scoring function over the NRI perils,
                               with the flood tier as a called-out modifier)

Geocoding is the only hard dependency: without coordinates + a tract GEOID there
is nothing to look up, so a GeocoderError propagates to the route (404/503).
Flood and NRI are best-effort so a partial report is still useful (mirrors how
the frontend already degrades).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.core.config import get_settings
from app.services.flood_zone import FloodZoneResult, get_flood_zone
from app.services.geocoder import GeocodeResult, geocode_address
from app.services.nri import NriResult, get_nri_scores
from app.services.scoring import CompositeResult, compute_composite

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportResult:
    geocode: GeocodeResult
    flood: FloodZoneResult | None
    nri: NriResult | None
    composite: CompositeResult | None


async def build_report(address: str) -> ReportResult:
    """Assemble the full risk report for *address*.

    Raises whatever :func:`geocode_address` raises (GeocoderError / NoMatchError)
    so the route can map it to the right status code. Flood and NRI failures are
    swallowed to None and logged.
    """
    geo = await geocode_address(address)

    flood_res, nri_res = await asyncio.gather(
        get_flood_zone(geo.lat, geo.lon),
        get_nri_scores(geo.tract_geoid),
        return_exceptions=True,
    )

    flood: FloodZoneResult | None = None
    if isinstance(flood_res, FloodZoneResult):
        flood = flood_res
    elif isinstance(flood_res, Exception):
        logger.warning("Flood lookup failed for %s: %s", address, flood_res)

    nri: NriResult | None = None
    if isinstance(nri_res, NriResult):
        nri = nri_res
    elif isinstance(nri_res, Exception):
        logger.warning("NRI lookup failed for %s: %s", address, nri_res)

    composite: CompositeResult | None = None
    if nri is not None:
        peril_scores = {p.code: p.score for p in nri.perils}
        flood_tier = flood.flood_tier if flood is not None else "Unknown"
        composite = compute_composite(
            peril_scores, flood_tier, get_settings().peril_weights
        )

    return ReportResult(geocode=geo, flood=flood, nri=nri, composite=composite)
