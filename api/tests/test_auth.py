"""Tests for Supabase JWT verification and the auth dependency.

Split into two levels:
  - verify_token unit tests (signature / expiry / audience / claims)
  - the get_current_user dependency as exercised through a protected endpoint
    (/reports), covering missing/invalid tokens and the not-configured path.
"""

from __future__ import annotations

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services.auth import (
    AuthNotConfiguredError,
    InvalidTokenError,
    verify_token,
)
from tests.conftest import AUTH_SECRET, USER_ID, auth_header, make_token

client = TestClient(app)


class TestVerifyToken:
    def test_valid_token_returns_user(self, auth_configured) -> None:
        user = verify_token(make_token())
        assert user.id == USER_ID
        assert user.email == "user@example.com"

    def test_expired_token_rejected(self, auth_configured) -> None:
        with pytest.raises(InvalidTokenError):
            verify_token(make_token(exp_delta=-10))

    def test_forged_signature_rejected(self, auth_configured) -> None:
        forged = make_token(secret="a-totally-different-secret-32-bytes-xx")
        with pytest.raises(InvalidTokenError):
            verify_token(forged)

    def test_wrong_audience_rejected(self, auth_configured) -> None:
        with pytest.raises(InvalidTokenError):
            verify_token(make_token(aud="anon"))

    def test_missing_sub_rejected(self, auth_configured) -> None:
        tok = jwt.encode(
            {"aud": "authenticated", "exp": int(time.time()) + 60},
            AUTH_SECRET,
            algorithm="HS256",
        )
        with pytest.raises(InvalidTokenError):
            verify_token(tok)

    def test_empty_token_rejected(self, auth_configured) -> None:
        with pytest.raises(InvalidTokenError):
            verify_token("")

    def test_not_configured_raises(self) -> None:
        # No auth_configured fixture → secret is unset.
        get_settings.cache_clear()
        with pytest.raises(AuthNotConfiguredError):
            verify_token(make_token())


class TestAuthDependency:
    """The dependency mapped onto HTTP status codes via a protected route."""

    def test_missing_token_returns_401(self) -> None:
        assert client.get("/reports").status_code == 401

    def test_malformed_authorization_header_returns_401(self) -> None:
        resp = client.get("/reports", headers={"Authorization": "NotBearer xyz"})
        assert resp.status_code == 401

    def test_token_but_auth_not_configured_returns_503(self) -> None:
        get_settings.cache_clear()  # ensure secret is unset
        resp = client.get("/reports", headers=auth_header())
        assert resp.status_code == 503
        assert "Auth is not configured" in resp.json()["detail"]

    def test_valid_token_passes_auth_then_503_without_db(self, auth_configured) -> None:
        # Auth succeeds; the service layer then reports no database is configured.
        resp = client.get("/reports", headers=auth_header())
        assert resp.status_code == 503
        assert "database" in resp.json()["detail"].lower()

    def test_invalid_token_returns_401(self, auth_configured) -> None:
        resp = client.get("/reports", headers=auth_header(make_token(exp_delta=-10)))
        assert resp.status_code == 401
