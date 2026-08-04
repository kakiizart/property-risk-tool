"""Shared test fixtures and helpers for auth-protected endpoints.

Provides a way to (a) configure a known JWT secret for the duration of a test
and (b) mint Supabase-style access tokens signed with it, so the auth boundary
can be exercised without a live Supabase project.
"""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.config import get_settings

# A ≥32-byte secret so PyJWT doesn't emit InsecureKeyLengthWarning in tests.
AUTH_SECRET = "test-jwt-secret-at-least-32-bytes-long-000"
USER_ID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def auth_configured(monkeypatch: pytest.MonkeyPatch):
    """Configure a known Supabase JWT secret for the duration of one test.

    Settings are cached with ``lru_cache``; we clear it around the test so
    ``get_settings()`` re-reads the patched environment and restores the real
    (unset) value afterwards.
    """
    monkeypatch.setenv("SUPABASE_JWT_SECRET", AUTH_SECRET)
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def make_token(
    *,
    secret: str = AUTH_SECRET,
    sub: str = USER_ID,
    aud: str = "authenticated",
    email: str | None = "user@example.com",
    exp_delta: int = 3600,
    **extra: object,
) -> str:
    """Mint an HS256 access token shaped like a Supabase one."""
    claims: dict[str, object] = {
        "sub": sub,
        "aud": aud,
        "exp": int(time.time()) + exp_delta,
    }
    if email is not None:
        claims["email"] = email
    claims.update(extra)
    return jwt.encode(claims, secret, algorithm="HS256")


def auth_header(token: str | None = None) -> dict[str, str]:
    """Build an Authorization header, minting a default valid token if needed."""
    return {"Authorization": f"Bearer {token or make_token()}"}


# ---------------------------------------------------------------------------
# ES256 (asymmetric) helpers — mirrors how modern Supabase signs access tokens.
# ---------------------------------------------------------------------------
def make_es256_token(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    sub: str = USER_ID,
    aud: str = "authenticated",
    email: str | None = "user@example.com",
    exp_delta: int = 3600,
    kid: str = "test-kid",
) -> str:
    """Mint an ES256 access token signed with *private_key*."""
    claims: dict[str, object] = {
        "sub": sub,
        "aud": aud,
        "exp": int(time.time()) + exp_delta,
    }
    if email is not None:
        claims["email"] = email
    return jwt.encode(claims, private_key, algorithm="ES256", headers={"kid": kid})


@pytest.fixture
def es256_auth(monkeypatch: pytest.MonkeyPatch):
    """Configure asymmetric (JWKS) verification with a locally-generated EC key.

    Sets SUPABASE_URL (so a JWKS URL is derived and auth is 'configured'), clears
    any HS256 secret, and patches the JWKS key resolver to return our public key —
    so the asymmetric path is exercised end to end without any network I/O.

    Yields the private key; use :func:`make_es256_token` to sign tokens with it.
    """
    from app.services import auth as auth_mod

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    monkeypatch.setenv("SUPABASE_URL", "https://test-project.supabase.co")
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    get_settings.cache_clear()
    monkeypatch.setattr(auth_mod, "_signing_key_for", lambda token, jwks_url: public_key)

    yield private_key
    get_settings.cache_clear()
