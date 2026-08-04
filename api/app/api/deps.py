"""Shared FastAPI dependencies.

`get_current_user` is the auth boundary for protected endpoints: it pulls the
bearer token off the request, verifies it (app.services.auth), and hands the
route a :class:`CurrentUser`. Verification failures never reach route code —
they are mapped to the right HTTP status here.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.auth import (
    AuthNotConfiguredError,
    CurrentUser,
    InvalidTokenError,
    verify_token,
)

# auto_error=False so we control the 401 body/headers instead of FastAPI's
# default 403 for missing credentials. Still advertises the scheme in OpenAPI
# (the Swagger "Authorize" button).
_bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Supabase access token (JWT)",
)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
) -> CurrentUser:
    """Resolve and verify the caller's Supabase access token.

    401 if the token is missing / invalid / expired; 503 if auth is not
    configured on the server.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # verify_token may do blocking JWKS I/O; keep it off the event loop.
        return await asyncio.to_thread(verify_token, credentials.credentials)
    except AuthNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
