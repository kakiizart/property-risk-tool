"""Application configuration.

All configuration comes from environment variables (or a local .env file in
development). Nothing sensitive is ever hardcoded. See .env.example for the
full list of variables.
"""

from __future__ import annotations

import json
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default composite weights for the region-relevant NRI perils (Erie's book:
# PA / Great Lakes / mid-Atlantic). Region-tunable via the PERIL_WEIGHTS_JSON
# env var. Weights are relative; the scoring function normalises over whichever
# perils actually have data for a tract. See docs/methodology.md.
DEFAULT_PERIL_WEIGHTS: dict[str, float] = {
    "WNTW": 0.22,  # Winter Weather
    "ISTM": 0.18,  # Ice Storm
    "HAIL": 0.18,  # Hail
    "SWND": 0.17,  # Strong Wind
    "RFLD": 0.15,  # Riverine (inland) Flooding
    "TRND": 0.10,  # Tornado
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "property-risk-api"
    environment: str = Field(default="development")  # development | staging | production
    log_level: str = Field(default="INFO")

    # --- CORS ---
    # Comma-separated list of allowed origins for the browser frontend.
    cors_origins: str = Field(default="http://localhost:3000")

    # --- Database (Supabase Postgres / PostGIS) ---
    # Populated per-environment; empty in Sprint 0 until the Supabase project exists.
    database_url: str = Field(default="")

    # --- Auth (Supabase Auth / JWT verification) ---
    # Project URL, e.g. https://<ref>.supabase.co. Used to fetch the JWKS that
    # verifies modern (asymmetric, ES256) Supabase access tokens.
    supabase_url: str = Field(default="")
    # Legacy HS256 shared secret (Project Settings > API > JWT Settings). Optional
    # fallback for projects/tokens still signed with HS256.
    supabase_jwt_secret: str = Field(default="")
    # Expected `aud` claim on Supabase access tokens (default for signed-in users).
    supabase_jwt_audience: str = Field(default="authenticated")

    # --- External data services (no keys required, kept configurable) ---
    census_geocoder_url: str = Field(
        default="https://geocoding.geo.census.gov/geocoder"
    )
    nfhl_mapserver_url: str = Field(
        default="https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
    )

    # --- Outbound HTTP behavior ---
    http_timeout_seconds: float = Field(default=8.0)
    http_max_retries: int = Field(default=1)

    # --- Scoring ---
    # Optional JSON object overriding the default composite peril weights, e.g.
    # '{"HAIL": 0.3, "SWND": 0.2, ...}'. Empty = use DEFAULT_PERIL_WEIGHTS.
    peril_weights_json: str = Field(default="")

    @property
    def peril_weights(self) -> dict[str, float]:
        """Composite peril weights, from the env override or documented defaults."""
        if self.peril_weights_json.strip():
            return json.loads(self.peril_weights_json)
        return dict(DEFAULT_PERIL_WEIGHTS)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def supabase_jwks_url(self) -> str:
        """JWKS endpoint for verifying asymmetric access tokens (derived from URL)."""
        if not self.supabase_url:
            return ""
        return self.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"

    @property
    def auth_configured(self) -> bool:
        """True if token verification is possible: a JWKS source or an HS256 secret."""
        return bool(self.supabase_url or self.supabase_jwt_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
