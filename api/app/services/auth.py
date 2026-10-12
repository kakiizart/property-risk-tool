"""
Supabase Auth — access-token (JWT) verification.

Supabase issues signed JWTs to signed-in users. This module verifies those
tokens on the API side so protected endpoints can trust the caller's identity.

Two signing schemes are supported, chosen by the token's ``alg`` header:

- **Asymmetric (ES256 / RS256 / EdDSA)** — the default for Supabase projects
  created since October 2025. The public key is fetched from the project's
  JWKS endpoint (``<SUPABASE_URL>/auth/v1/.well-known/jwks.json``) and cached,
  so verification needs no shared secret at all.
- **HS256 legacy shared secret** — for older projects that still sign with the
  "Legacy JWT Secret". Only accepted when ``SUPABASE_JWT_SECRET`` is set.

Either way the check covers:
  - signature   (rejects forged / tampered tokens)
  - expiry      (`exp`)
  - audience    (`aud`, default "authenticated")
  - presence of `sub` (the user id)

Algorithm-confusion guard: the allowed algorithm comes from the *key* (the
JWK's own algorithm, or HS256 for the configured secret), never from the token
header alone, and ``alg: none`` is always rejected.

The verified `sub` is the user's UUID — the same value the `saved_report`
RLS policies compare against ``auth.uid()`` (see app.db.acquire_as_user).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import jwt

from app.core.config import get_settings

ASYMMETRIC_ALGORITHMS = frozenset({"ES256", "RS256", "EdDSA"})
JWKS_CACHE_SECONDS = 600  # matches Supabase's own edge cache window
JWKS_TIMEOUT_SECONDS = 5


class AuthError(Exception):
    """Base class for authentication failures."""


class AuthNotConfiguredError(AuthError):
    """Neither SUPABASE_URL nor SUPABASE_JWT_SECRET is set (503)."""


class AuthUnavailableError(AuthError):
    """The project's JWKS endpoint could not be reached to verify a token (503)."""


class InvalidTokenError(AuthError):
    """Token is missing, malformed, expired, or failed verification (401)."""


@dataclass(frozen=True)
class CurrentUser:
    """An authenticated caller, resolved from a verified Supabase access token."""

    id: str            # Supabase user UUID (JWT `sub`); matches auth.uid() in RLS
    email: str | None
    token: str         # raw access token (retained only within the request)


@lru_cache(maxsize=4)
def get_jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    """One cached JWKS client per URL, so keys are fetched once per cache window."""
    return jwt.PyJWKClient(
        jwks_url,
        cache_jwk_set=True,
        lifespan=JWKS_CACHE_SECONDS,
        timeout=JWKS_TIMEOUT_SECONDS,
    )


def _resolve_key(token: str, alg: str | None) -> tuple[object, list[str]]:
    """Pick the verification key and the single algorithm it may be used with."""
    settings = get_settings()

    if alg == "HS256":
        if not settings.supabase_jwt_secret:
            raise InvalidTokenError("Invalid authentication token.")
        return settings.supabase_jwt_secret, ["HS256"]

    if alg in ASYMMETRIC_ALGORITHMS:
        if not settings.supabase_jwks_url:
            raise InvalidTokenError("Invalid authentication token.")
        try:
            signing_key = get_jwks_client(settings.supabase_jwks_url).get_signing_key_from_jwt(
                token
            )
        except jwt.PyJWKClientConnectionError as exc:
            raise AuthUnavailableError(
                "Could not reach the auth key server to verify the token."
            ) from exc
        except (jwt.PyJWKClientError, jwt.InvalidTokenError) as exc:
            # Unknown `kid`, malformed JWKS, or a key type we cannot use.
            raise InvalidTokenError("Invalid authentication token.") from exc

        key_alg = signing_key.algorithm_name
        if key_alg not in ASYMMETRIC_ALGORITHMS or key_alg != alg:
            raise InvalidTokenError("Invalid authentication token.")
        return signing_key.key, [key_alg]

    # Includes `none` and anything we do not explicitly support.
    raise InvalidTokenError("Invalid authentication token.")


def verify_token(token: str) -> CurrentUser:
    """Verify a Supabase access token and return the authenticated user.

    May perform a (cached) network fetch of the project's JWKS, so async callers
    should run it in a worker thread.

    Raises:
        AuthNotConfiguredError: no verification method is configured (maps to 503).
        AuthUnavailableError: the JWKS endpoint is unreachable (maps to 503).
        InvalidTokenError: token missing / expired / forged / wrong audience (401).
    """
    settings = get_settings()
    if not settings.auth_configured:
        raise AuthNotConfiguredError(
            "Auth is not configured. Set SUPABASE_URL (or the legacy "
            "SUPABASE_JWT_SECRET) to enable saved reports."
        )
    if not token:
        raise InvalidTokenError("Missing bearer token.")

    try:
        alg = jwt.get_unverified_header(token).get("alg")
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("Invalid authentication token.") from exc

    key, algorithms = _resolve_key(token, alg)

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=algorithms,
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
