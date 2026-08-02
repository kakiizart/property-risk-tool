"""Health and readiness endpoints.

- /health   liveness: the process is up. Never touches dependencies.
- /health/ready  readiness: checks that required config is present. As the app
  grows this will also ping the database.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, bool]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.environment,
    )


@router.get("/health/ready", response_model=ReadyResponse)
def ready() -> ReadyResponse:
    settings = get_settings()
    checks = {
        # In production the database must be configured; in dev it may be blank
        # during early sprints, so we only require it when running in production.
        "database_configured": bool(settings.database_url) or not settings.is_production,
        "geocoder_configured": bool(settings.census_geocoder_url),
        "nfhl_configured": bool(settings.nfhl_mapserver_url),
    }
    status = "ok" if all(checks.values()) else "degraded"
    return ReadyResponse(status=status, checks=checks)
