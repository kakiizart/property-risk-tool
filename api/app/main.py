"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import flood, geocode, health, nri, report
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import close_pool, init_pool

logger = logging.getLogger("app")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Fail fast in production if required configuration is missing.
        if settings.is_production and not settings.database_url:
            raise RuntimeError("DATABASE_URL must be set in production")

        # Initialise DB pool if DATABASE_URL is configured.
        # In early dev / CI without a database, the pool is skipped and NRI
        # endpoints degrade gracefully to 503.
        if settings.database_url:
            await init_pool(settings.database_url)

        logger.info("startup", extra={"extra": {"environment": settings.environment}})
        yield
        logger.info("shutdown")

        if settings.database_url:
            await close_pool()

    app = FastAPI(
        lifespan=lifespan,
        title="Property Risk & Hazard Exposure API",
        version="0.1.0",
        description=(
            "Geocodes a US address and returns a transparent, source-traceable "
            "multi-peril risk profile from FEMA NRI and NFHL data."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(geocode.router)
    app.include_router(flood.router)
    app.include_router(nri.router)
    app.include_router(report.router)

    return app


app = create_app()
