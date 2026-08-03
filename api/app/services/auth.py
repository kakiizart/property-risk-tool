"""
Supabase Auth — access-token (JWT) verification.

Supabase issues signed JWTs to signed-in users. This module verifies those
tokens on the API side so protected endpoints can trust the caller's identity
without a round-trip to Supabase.

Verification (HS256, the shared "JWT Secret" from the Supabase project) checks:
  - signature   (rejects forged / tampered tokens)
  - expiry      (`exp`)
  - audience    (`aud`, default "authenticated")
  - presence of `sub` (the user id)

The verified `sub` is the user's UUID — the same value the `saved_report`
RLS policies compare against ``auth.uid()`` (see app.db.acquire_as_user).

Design note
-----------
Newer Supabase projects can also sign with asymmetric keys (ES256/RS256) served
from a JWKS endpoint. We deliberately support only the HS256 shared secret here:
it is available on every project, needs no network fetch, and keeps the trust
boundary to a single documented secret. The trade-off is recorded in
docs/security.md.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt

from app.core.config import get_settings


class AuthError(Exception):
    """Base class for authentication failures."""


class AuthNotConfiguredError(AuthError):
    """SUPABASE_JWT_SECRET is not set — the server cannot verify tokens (503)."""


class InvalidTokenError(AuthError):
    """Token is missing, malformed, expired, or failed verification (401)."""


@dataclass(frozen=True)
class CurrentUser:
    """An authenticated caller, resolved from a verified Supabase access token."""

    id: str            # Supabase user UUID (JWT `sub`); matches auth.uid() in RLS
    email: str | None
    token: str         # raw access token (retained only within the request)


def verify_token(token: str) -> CurrentUser:
    """Verify a Supabase access token and return the authenticated user.

    Raises:
        AuthNotConfiguredError: no signing secret is configured (maps to 503).
        InvalidTokenError: token missing / expired / forged / wrong audience (401).
    """
    settings = get_settings()
    if not settings.auth_configured:
        raise AuthNotConfiguredError(
            "Auth is not configured. Set SUPABASE_JWT_SECRET to enable saved reports."
        )
    if not token:
        raise InvalidTokenError("Missing bearer token.")

    try:
        claims = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.supabase_jwt_audience,
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        # Bad signature, wrong audience, malformed token, or missing required claim.
        raise InvalidTokenError("Invalid authentication token.") from exc

    sub = claims.get("sub")
    if not sub:
        raise InvalidTokenError("Token is missing the subject (sub) claim.")

    return CurrentUser(id=str(sub), email=claims.get("email"), token=token)
