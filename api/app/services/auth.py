"""
Supabase Auth — access-token (JWT) verification.

Supabase issues signed JWTs to signed-in users. This module verifies those
tokens on the API side so protected endpoints can trust the caller's identity
without a round-trip to Supabase.

Algorithms
----------
Modern Supabase projects sign **user access tokens with asymmetric keys
(ES256)**, published at the project's JWKS endpoint
(``<SUPABASE_URL>/auth/v1/.well-known/jwks.json``). Older projects (and the
anon/service keys) use the **HS256 shared secret**. We support both, selected by
the token's ``alg`` header:

  * ES256 / RS256 / …  -> verified against the project JWKS (fetched + cached)
  * HS256              -> verified against SUPABASE_JWT_SECRET (fallback)

Either configuration alone is sufficient (see Settings.auth_configured).

Every token is additionally checked for expiry (``exp``), audience (``aud``,
default "authenticated"), and a subject (``sub``) — the user's UUID, the same
value the ``saved_report`` RLS policies compare against ``auth.uid()``.

Note: JWKS retrieval does blocking network I/O, so callers on the async path
should invoke :func:`verify_token` via a worker thread (see app.api.deps).
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from app.core.config import get_settings

# Asymmetric algorithms verified via the project JWKS.
_ASYMMETRIC_ALGS = ("ES256", "ES384", "ES512", "RS256", "RS384", "RS512", "EdDSA")

# One cached PyJWKClient per JWKS URL (it caches keys and refreshes on kid miss).
_jwk_clients: dict[str, PyJWKClient] = {}


class AuthError(Exception):
    """Base class for authentication failures."""


class AuthNotConfiguredError(AuthError):
    """No verification source is configured (no JWKS URL and no secret). 503."""


class InvalidTokenError(AuthError):
    """Token is missing, malformed, expired, or failed verification. 401."""


@dataclass(frozen=True)
class CurrentUser:
    """An authenticated caller, resolved from a verified Supabase access token."""

    id: str            # Supabase user UUID (JWT `sub`); matches auth.uid() in RLS
    email: str | None
    token: str         # raw access token (retained only within the request)


def _signing_key_for(token: str, jwks_url: str) -> object:
    """Return the public key that signed *token*, from the project JWKS (cached).

    Factored out so tests can inject a key without hitting the network.
    """
    client = _jwk_clients.get(jwks_url)
    if client is None:
        client = PyJWKClient(jwks_url, cache_keys=True, lifespan=600)
        _jwk_clients[jwks_url] = client
    return client.get_signing_key_from_jwt(token).key


def verify_token(token: str) -> CurrentUser:
    """Verify a Supabase access token and return the authenticated user.

    Raises:
        AuthNotConfiguredError: no JWKS URL and no secret configured (503).
        InvalidTokenError: token missing / expired / forged / wrong audience /
            unsupported algorithm / signing key unavailable (401).
    """
    settings = get_settings()
    if not settings.auth_configured:
        raise AuthNotConfiguredError(
            "Auth is not configured. Set SUPABASE_URL (JWKS) or SUPABASE_JWT_SECRET."
        )
    if not token:
        raise InvalidTokenError("Missing bearer token.")

    try:
        alg = jwt.get_unverified_header(token).get("alg")
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("Invalid authentication token.") from exc

    # Resolve the verification key by algorithm family (config checked first, so
    # our own errors are never swallowed by the decode except-handlers below).
    if alg == "HS256":
        if not settings.supabase_jwt_secret:
            raise InvalidTokenError("HS256 token received but no shared secret is configured.")
        key: object = settings.supabase_jwt_secret
    elif alg in _ASYMMETRIC_ALGS:
        if not settings.supabase_jwks_url:
            raise InvalidTokenError("Asymmetric token received but no JWKS URL is configured.")
        try:
            key = _signing_key_for(token, settings.supabase_jwks_url)
        except Exception as exc:  # PyJWKClientError, kid miss, network failure
            raise InvalidTokenError("Could not resolve the token signing key.") from exc
    else:
        raise InvalidTokenError(f"Unsupported token algorithm: {alg!r}.")

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=[alg],
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
