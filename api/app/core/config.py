"""Application configuration.

All configuration comes from environment variables (or a local .env file in
development). Nothing sensitive is ever hardcoded. See .env.example for the
full list of variables.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
