"""
ETL script: Download FEMA NRI census-tract data and load into PostGIS.

Usage:
  cd api
  DATABASE_URL=postgresql://... python -m scripts.etl_nri

What this does:
  1. Downloads the NRI census-tract CSV ZIP from FEMA (or uses a local copy).
  2. Extracts the relevant columns: tract GEOID, composite score, EAL, per-peril scores.
  3. Upserts into public.nri_tract (schema in db/migrations/0001_init.sql).
  4. Verifies with a quick EXPLAIN that the GEOID index is used.

The target table stores per-peril scores as JSONB:
  {"SWND": {"score": 45.2, "eal": 1234.56}, "HAIL": {...}, ...}

This makes it easy to add new perils without schema changes, and lets the
scoring service pull only the perils it needs in one query.

NRI data source:
  https://hazards.fema.gov/nri/Content/StaticDocuments/DataDownload/
  NRI_Table_CensusTracts/NRI_Table_CensusTracts.zip

Last verified working with NRI v1.20 (released 2023-11).
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

import asyncpg

logger = logging.getLogger(__name__)

NRI_ZIP_URL = (
    "https://hazards.fema.gov/nri/Content/StaticDocuments/DataDownload/"
    "NRI_Table_CensusTracts/NRI_Table_CensusTracts.zip"
)
NRI_CSV_NAME = "NRI_Table_CensusTracts.csv"

# All 18 NRI hazard codes. Each maps to a pair of CSV columns:
#   {CODE}_RISKS → relative risk score (0–100)
#   {CODE}_EAL_VALA → expected annual loss (annualised $ value)
ALL_PERIL_CODES = [
    "AVLN", "CFLD", "CWAV", "DRGT", "ERQK",
    "HAIL", "HWAV", "HRCN", "ISTM", "LNDS",
    "LTNG", "RFLD", "SWND", "TRND", "TSUN",
    "VLCN", "WFIR", "WNTW",
]


def _safe_float(value: str) -> float | None:
    """Return float or None for empty / non-numeric CSV cells."""
    v = value.strip()
    if not v or v in ("-999", "-999.0", ""):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def download_nri_csv(local_dir: Path) -> Path:
    """Download the NRI ZIP if not already cached; return path to the CSV."""
    local_zip = local_dir / "NRI_Table_CensusTracts.zip"
    csv_path = local_dir / NRI_CSV_NAME

    if csv_path.exists():
        logger.info("Using cached NRI CSV: %s", csv_path)
        return csv_path

    if not local_zip.exists():
        logger.info("Downloading NRI ZIP from FEMA (~500 MB)…")
        urlretrieve(NRI_ZIP_URL, local_zip)
        logger.info("Download complete: %s", local_zip)

    logger.info("Extracting NRI CSV…")
    with zipfile.ZipFile(local_zip) as zf:
        names = [n for n in zf.namelist() if n.endswith(".csv")]
        if not names:
            raise RuntimeError("No CSV found in NRI ZIP")
        zf.extract(names[0], local_dir)
        # Rename to canonical name if needed
        extracted = local_dir / names[0]
        if extracted != csv_path:
            extracted.rename(csv_path)

    logger.info("Extracted: %s", csv_path)
    return csv_path


def parse_nri_csv(csv_path: Path):
    """
    Yield (tract_geoid, risk_score, eal_total, peril_scores_json) rows.

    peril_scores_json is a dict like {"SWND": {"score": 45.2, "eal": 1234.56}, ...}
    Only perils with at least one non-None value are included.
    """
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            geoid = row.get("TRACTFIPS", "").strip()
            if not geoid or len(geoid) != 11:
                continue

            risk_score = _safe_float(row.get("RISK_SCORE", ""))
            eal_total = _safe_float(row.get("EAL_VALT", ""))

            peril_scores: dict[str, dict] = {}
            for code in ALL_PERIL_CODES:
                score = _safe_float(row.get(f"{code}_RISKS", ""))
                eal = _safe_float(row.get(f"{code}_EAL_VALA", ""))
                if score is not None or eal is not None:
                    peril_scores[code] = {
                        k: v
                        for k, v in {"score": score, "eal": eal}.items()
                        if v is not None
                    }

            yield geoid, risk_score, eal_total, peril_scores


async def load_to_db(database_url: str, csv_path: Path, batch_size: int = 500) -> int:
    """
    Upsert NRI rows into public.nri_tract.

    Returns the number of rows processed.
    """
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=4)
    count = 0
    batch: list[tuple] = []

    async with pool.acquire() as conn:
        # Prepare the upsert once
        stmt = await conn.prepare(
            """
            INSERT INTO public.nri_tract (tract_geoid, risk_score, eal_total, peril_scores)
            VALUES ($1, $2, $3, $4::jsonb)
            ON CONFLICT (tract_geoid) DO UPDATE
                SET risk_score   = EXCLUDED.risk_score,
                    eal_total    = EXCLUDED.eal_total,
                    peril_scores = EXCLUDED.peril_scores,
                    updated_at   = now()
            """
        )

        for geoid, risk_score, eal_total, peril_scores in parse_nri_csv(csv_path):
            batch.append((geoid, risk_score, eal_total, json.dumps(peril_scores)))
            count += 1

            if len(batch) >= batch_size:
                await stmt.executemany(batch)
                logger.info("Upserted %d rows…", count)
                batch.clear()

        if batch:
            await stmt.executemany(batch)

    await pool.close()
    logger.info("ETL complete — %d census tracts loaded.", count)
    return count


async def verify_index(database_url: str) -> None:
    """Run EXPLAIN to confirm the GEOID index is used on a point lookup."""
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=1)
    async with pool.acquire() as conn:
        plan = await conn.fetchval(
            "EXPLAIN SELECT tract_geoid FROM public.nri_tract WHERE tract_geoid = $1",
            "11001006202",
        )
    await pool.close()

    if "Index" in (plan or ""):
        logger.info("Index check PASS — query uses index scan: %s", plan)
    else:
        logger.warning("Index check — unexpected plan (full scan?): %s", plan)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        sys.exit("ERROR: DATABASE_URL environment variable is not set.")

    # Store downloaded files next to this script
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(exist_ok=True)

    csv_path = download_nri_csv(data_dir)
    await load_to_db(database_url, csv_path)
    await verify_index(database_url)


if __name__ == "__main__":
    asyncio.run(main())
