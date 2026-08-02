"""
FEMA National Risk Index (NRI) lookup service.

Looks up per-peril risk scores and Expected Annual Loss (EAL) for a census
tract from the local PostGIS database populated by the ETL script.

The NRI data provides 18-hazard composite + per-peril scores (0–100) and
estimated annual dollar losses at the census-tract level. This is the
authoritative source — we don't invent scores, we surface them.

Source: FEMA NRI v1.20 (https://hazards.fema.gov/nri/)
        Downloaded once by scripts/etl_nri.py and loaded into nri_tract.

Per-peril codes surfaced for Erie Insurance's market (PA + Great Lakes +
mid-Atlantic). The full 18-peril set is stored in the DB; these are the
most relevant for the target region:
  SWND  Strong Wind
  HAIL  Hail
  TRND  Tornado
  WNTW  Winter Weather
  ISTM  Ice Storm
  RFLD  Riverine Flooding
  HRCN  Hurricane
  LTNG  Lightning
  CFLD  Coastal Flooding
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.db import get_pool, pool_available

logger = logging.getLogger(__name__)

# Ordered list of perils shown in the UI panel.
# Maps display name → NRI hazard code (key in peril_scores JSONB).
DISPLAYED_PERILS: list[tuple[str, str]] = [
    ("Strong Wind", "SWND"),
    ("Hail", "HAIL"),
    ("Tornado", "TRND"),
    ("Winter Weather", "WNTW"),
    ("Ice Storm", "ISTM"),
    ("Riverine Flooding", "RFLD"),
    ("Hurricane", "HRCN"),
    ("Lightning", "LTNG"),
    ("Coastal Flooding", "CFLD"),
]


@dataclass(frozen=True)
class PerilScore:
    name: str
    code: str
    score: float | None       # 0–100 relative risk score (None if missing from tract data)
    eal_usd: float | None     # Expected annual loss in USD (None if missing)
    tier: str                 # "High" | "Moderate" | "Low" | "Unknown"


@dataclass(frozen=True)
class NriResult:
    tract_geoid: str
    composite_score: float | None   # NRI composite 0–100
    eal_total_usd: float | None     # Total EAL across all hazards
    perils: list[PerilScore] = field(default_factory=list)
    source: str = "FEMA National Risk Index v1.20"


class NriError(Exception):
    """Raised for caller-visible NRI lookup failures."""


async def get_nri_scores(tract_geoid: str) -> NriResult:
    """
    Look up NRI risk scores for a census tract from the local database.

    Returns an :class:`NriResult` with the composite score, total EAL, and
    per-peril breakdowns. Raises :class:`NriError` if the DB is not available
    or the tract GEOID has no NRI record.
    """
    if not pool_available():
        raise NriError(
            "NRI database is not configured. "
            "Set DATABASE_URL and run scripts/etl_nri.py to load the data."
        )

    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT tract_geoid, risk_score, eal_total, peril_scores
            FROM public.nri_tract
            WHERE tract_geoid = $1
            """,
            tract_geoid,
        )

    if row is None:
        raise NriError(
            f"No NRI record found for census tract {tract_geoid!r}. "
            "The ETL may not have loaded this tract, or the GEOID may be incorrect."
        )

    peril_scores_json: dict = row["peril_scores"] or {}
    perils = _build_peril_list(peril_scores_json)

    return NriResult(
        tract_geoid=tract_geoid,
        composite_score=float(row["risk_score"]) if row["risk_score"] is not None else None,
        eal_total_usd=float(row["eal_total"]) if row["eal_total"] is not None else None,
        perils=perils,
    )


# ---------------------------------------------------------------------------
# Internal helpers (pure functions — testable without a DB)
# ---------------------------------------------------------------------------

def score_to_tier(score: float | None) -> str:
    """Convert a 0–100 NRI score to a High/Moderate/Low tier."""
    if score is None:
        return "Unknown"
    if score >= 50:
        return "High"
    if score >= 25:
        return "Moderate"
    return "Low"


def _build_peril_list(peril_scores_json: dict) -> list[PerilScore]:
    """
    Build the displayed peril list from the JSONB column.

    The JSONB stores scores as: {"SWND": {"score": 45.2, "eal": 1234.56}, ...}
    Missing codes get None scores so the UI can show "No data".
    """
    result = []
    for display_name, code in DISPLAYED_PERILS:
        entry = peril_scores_json.get(code, {})
        score = entry.get("score")
        eal = entry.get("eal")
        score_f = float(score) if score is not None else None
        eal_f = float(eal) if eal is not None else None
        result.append(
            PerilScore(
                name=display_name,
                code=code,
                score=score_f,
                eal_usd=eal_f,
                tier=score_to_tier(score_f),
            )
        )
    return result
