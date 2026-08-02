"""Golden-address validation for the flood pipeline (see docs/methodology.md).

Two layers:
  * an offline consistency check that the recorded zone classifies to the
    recorded tier (runs in CI, no network), and
  * an opt-in integration test that geocodes each address live and asserts the
    pipeline reproduces the expected flood tier. It hits FEMA/Census, so it is
    skipped unless RUN_GOLDEN=1 to keep the default suite deterministic.

Run the live check with:
  RUN_GOLDEN=1 SSL_CERT_FILE=/path/to/ca-bundle.crt pytest tests/test_golden.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.flood_zone import _classify_zone

client = TestClient(app)

_GOLDEN = json.loads(
    (Path(__file__).parent / "golden_addresses.json").read_text(encoding="utf-8")
)["addresses"]
_VALID_TIERS = {"High", "Moderate", "Low"}


def test_golden_file_is_valid_and_self_consistent() -> None:
    """Offline: every recorded zone must classify to its recorded tier."""
    assert len(_GOLDEN) >= 6, "expected a meaningful golden set"
    for entry in _GOLDEN:
        assert entry["expected_flood_tier"] in _VALID_TIERS
        tier, _ = _classify_zone(entry["zone_observed"], "")
        assert tier == entry["expected_flood_tier"], (
            f"{entry['address']}: zone {entry['zone_observed']!r} classifies to "
            f"{tier!r}, not the recorded {entry['expected_flood_tier']!r}"
        )


@pytest.mark.skipif(
    not os.getenv("RUN_GOLDEN"),
    reason="set RUN_GOLDEN=1 to run the live FEMA/Census integration check",
)
@pytest.mark.parametrize("entry", _GOLDEN, ids=[e["address"] for e in _GOLDEN])
def test_golden_pipeline_reproduces_flood_tier(entry: dict) -> None:
    """Live: geocode the address and assert the flood tier reproduces."""
    g = client.post("/geocode", json={"address": entry["address"]})
    assert g.status_code == 200, g.text
    body = g.json()

    f = client.get("/flood", params={"lat": body["lat"], "lon": body["lon"]})
    assert f.status_code == 200, f.text
    assert f.json()["flood_tier"] == entry["expected_flood_tier"]
