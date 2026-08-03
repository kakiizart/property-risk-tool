# Scoring methodology

The score is **derived from authoritative FEMA data through a documented formula**,
never invented. The UI and API expose every component so any number can be traced
to its source.

## Inputs
1. **Flood zone (parcel-level, authoritative)** — from the FEMA National Flood
   Hazard Layer at the geocoded point.
2. **Per-peril scores + Expected Annual Loss (tract-level)** — from the FEMA
   National Risk Index for the containing census tract.

## Flood tier mapping
| NFHL zone | Tier |
|-----------|------|
| `V`, `VE`, `A`, `AE`, `AO`, `AH` (Special Flood Hazard Area, 1% annual) | High |
| `X` (shaded) / 0.2% annual chance | Moderate |
| `X` (unshaded) / minimal | Low |

Flood is shown as its own authoritative tier and is not blended away — insurers
treat Special-Flood-Hazard-Area status as a hard fact.

## Regional perils (from NRI)
For Erie's book (PA / Great Lakes / mid-Atlantic), the relevant perils are
**inland flooding, strong wind, hail, tornado, winter weather, and ice storm**.
Each is already a 0–100 relative NRI score; the app surfaces them rather than
reinventing them.

## Composite score
A documented **weighted average** of the regional peril scores, with weights held
in config (`DEFAULT_PERIL_WEIGHTS`; override via `PERIL_WEIGHTS_JSON`) and
**normalised over whichever perils have data** for the tract, so missing data
doesn't drag the score toward zero. Default weights (Erie's book):

| Peril | Weight |
|-------|--------|
| Winter Weather (WNTW) | 0.22 |
| Ice Storm (ISTM) | 0.18 |
| Hail (HAIL) | 0.18 |
| Strong Wind (SWND) | 0.17 |
| Riverine Flooding (RFLD) | 0.15 |
| Tornado (TRND) | 0.10 |

Flood is a **called-out modifier, never blended in**: the overall tier is the
more severe of the composite tier and the flood tier, so Special-Flood-Hazard-Area
status is never hidden. The composite is always returned with its per-peril
weights and contributions (which sum to the score). Implemented in
`app/services/scoring.py`; served by `POST /report`.

## Expected Annual Loss
The app surfaces NRI's building-level EAL (USD) for the tract. This is the number
that maps to how underwriters actually think, and it is the honest bridge toward
catastrophe-modeling *concepts* — without claiming to be a catastrophe model.

## Validation
`golden_addresses.json` holds ~8–10 addresses with hand-verified flood zones
(checked against the FEMA Map Service Center) and expected tiers. A test asserts
the pipeline reproduces them.

## Honest claims
**Say:** "transparent, source-traceable multi-peril risk scoring from FEMA NRI and
NFHL data."
**Do not say:** "catastrophe model" or "ML loss prediction" — neither is what this
is, and an insurer will know the difference.
