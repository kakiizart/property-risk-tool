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
A documented weighted combination of the regional peril scores, with weights held
in config (region-tunable), plus the flood tier as a called-out modifier. The
composite is never shown without its component breakdown and the weights.

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
