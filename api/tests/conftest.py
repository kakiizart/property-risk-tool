"""Shared test fixtures and helpers for auth-protected endpoints.

Provides a way to (a) configure a known JWT secret for the duration of a test
and (b) mint Supabase-style access tokens signed with it, so the auth boundary
can be exercised without a live Supabase project.
"""

from __future__ import annotations

import time

import jwt
import pytest

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
