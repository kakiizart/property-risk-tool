"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health
from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger("app")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Fail fast in production if required configuration is missing.
        if settings.is_production and not settings.database_url:
            raise RuntimeError("DATABASE_URL must be set in production")
        logger.info("startup", extra={"extra": {"environment": settings.environment}})
        yield
        logger.info("shutdown")

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

    return app


app = create_app()
