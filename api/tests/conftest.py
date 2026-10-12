"""Shared test fixtures and helpers for auth-protected endpoints.

Provides a way to (a) configure a known JWT secret (legacy HS256) or a fake
JWKS endpoint (asymmetric ES256, the default for new Supabase projects) for the
duration of a test and (b) mint Supabase-style access tokens for either, so the
auth boundary can be exercised without a live Supabase project.
"""

from __future__ import annotations

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from app.core.config import get_settings

# A ≥32-byte secret so PyJWT doesn't emit InsecureKeyLengthWarning in tests.
AUTH_SECRET = "test-jwt-secret-at-least-32-bytes-long-000"
USER_ID = "11111111-2222-3333-4444-555555555555"
SUPABASE_TEST_URL = "https://testproject.supabase.co"
EC_KID = "test-ec-key"


@pytest.fixture(autouse=True)
def _isolate_auth_settings(monkeypatch: pytest.MonkeyPatch):
    """Keep tests independent of a developer's local api/.env.

    Real environment variables take priority over the .env file in
    pydantic-settings, so blanking these makes "auth not configured" the
    default in every test, even on a machine with a filled-in .env. Fixtures
    below opt back in explicitly.
    """
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
# Asymmetric (ES256 + JWKS) — the default signing scheme for new projects
# ---------------------------------------------------------------------------

EC_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_EC_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())


def public_jwk(private_key: ec.EllipticCurvePrivateKey = EC_PRIVATE_KEY, kid: str = EC_KID) -> dict:
    """The JWKS entry Supabase would publish for *private_key*."""
    jwk = json.loads(ECAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": kid, "alg": "ES256", "use": "sig"})
    return jwk


class FakeJWKSClient:
    """Stands in for jwt.PyJWKClient so tests never touch the network."""

    def __init__(self, keys: list[dict] | None = None, error: Exception | None = None):
        self.keys = keys if keys is not None else [public_jwk()]
        self.error = error
        self.calls = 0

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
        self.calls += 1
        if self.error is not None:
            raise self.error
        kid = jwt.get_unverified_header(token).get("kid")
        for key in self.keys:
            if key.get("kid") == kid:
                return jwt.PyJWK(key)
        raise jwt.PyJWKClientError(f'Unable to find a signing key that matches: "{kid}"')


@pytest.fixture
def jwks_client(monkeypatch: pytest.MonkeyPatch) -> FakeJWKSClient:
    """Configure SUPABASE_URL (no legacy secret) and a fake JWKS client."""
    fake = FakeJWKSClient()
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_TEST_URL)
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    monkeypatch.setattr("app.services.auth.get_jwks_client", lambda url: fake)
    get_settings.cache_clear()
    yield fake
    get_settings.cache_clear()


def make_es256_token(
    *,
    private_key: ec.EllipticCurvePrivateKey = EC_PRIVATE_KEY,
    kid: str = EC_KID,
    sub: str = USER_ID,
    aud: str = "authenticated",
    email: str | None = "user@example.com",
    exp_delta: int = 3600,
) -> str:
    """Mint an ES256 access token shaped like a new-project Supabase one."""
    claims: dict[str, object] = {"sub": sub, "aud": aud, "exp": int(time.time()) + exp_delta}
    if email is not None:
        claims["email"] = email
    return jwt.encode(claims, private_key, algorithm="ES256", headers={"kid": kid})
