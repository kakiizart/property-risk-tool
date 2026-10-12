"""Tests for Supabase JWT verification and the auth dependency.

Split into two levels:
  - verify_token unit tests (signature / expiry / audience / claims)
  - the get_current_user dependency as exercised through a protected endpoint
    (/reports), covering missing/invalid tokens and the not-configured path.
"""

from __future__ import annotations

import base64
import json
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services.auth import (
    AuthNotConfiguredError,
    AuthUnavailableError,
    InvalidTokenError,
    verify_token,
)
from tests.conftest import (
    AUTH_SECRET,
    OTHER_EC_PRIVATE_KEY,
    USER_ID,
    auth_header,
    make_es256_token,
    make_token,
    public_jwk,
)

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


class TestAsymmetricVerification:
    """ES256 tokens verified via the project's JWKS (new Supabase projects)."""

    def test_valid_es256_token_returns_user(self, jwks_client) -> None:
        user = verify_token(make_es256_token())
        assert user.id == USER_ID
        assert user.email == "user@example.com"
        assert jwks_client.calls == 1

    def test_es256_signed_by_other_key_rejected(self, jwks_client) -> None:
        with pytest.raises(InvalidTokenError):
            verify_token(make_es256_token(private_key=OTHER_EC_PRIVATE_KEY))

    def test_unknown_kid_rejected(self, jwks_client) -> None:
        with pytest.raises(InvalidTokenError):
            verify_token(make_es256_token(kid="rotated-away"))

    def test_expired_es256_token_rejected(self, jwks_client) -> None:
        with pytest.raises(InvalidTokenError, match="expired"):
            verify_token(make_es256_token(exp_delta=-10))

    def test_es256_wrong_audience_rejected(self, jwks_client) -> None:
        with pytest.raises(InvalidTokenError):
            verify_token(make_es256_token(aud="anon"))

    def test_rotated_keys_both_accepted(self, jwks_client) -> None:
        # During a key rotation the JWKS publishes old and new keys side by side.
        jwks_client.keys = [public_jwk(), public_jwk(OTHER_EC_PRIVATE_KEY, kid="next")]
        assert verify_token(make_es256_token()).id == USER_ID
        token = make_es256_token(private_key=OTHER_EC_PRIVATE_KEY, kid="next")
        assert verify_token(token).id == USER_ID

    def test_hs256_rejected_when_only_jwks_configured(self, jwks_client) -> None:
        # No legacy secret configured -> HS256 tokens are never accepted.
        with pytest.raises(InvalidTokenError):
            verify_token(make_token())
        assert jwks_client.calls == 0

    def test_alg_none_rejected(self, jwks_client) -> None:
        tok = jwt.encode(
            {"sub": USER_ID, "aud": "authenticated", "exp": int(time.time()) + 60},
            None,
            algorithm="none",
        )
        with pytest.raises(InvalidTokenError):
            verify_token(tok)

    def test_header_alg_must_match_key_alg(self, jwks_client) -> None:
        # Token claims RS256 but the published key for its kid is ES256.
        header_says_rs256 = make_es256_token().split(".")
        hdr = {"alg": "RS256", "kid": "test-ec-key", "typ": "JWT"}
        header_says_rs256[0] = (
            base64.urlsafe_b64encode(json.dumps(hdr).encode()).rstrip(b"=").decode()
        )
        with pytest.raises(InvalidTokenError):
            verify_token(".".join(header_says_rs256))

    def test_jwks_unreachable_raises_unavailable(self, jwks_client) -> None:
        jwks_client.error = jwt.PyJWKClientConnectionError("connection refused")
        with pytest.raises(AuthUnavailableError):
            verify_token(make_es256_token())

    def test_garbage_token_rejected(self, jwks_client) -> None:
        with pytest.raises(InvalidTokenError):
            verify_token("not-a-jwt")

    def test_es256_token_passes_dependency_then_503_without_db(self, jwks_client) -> None:
        resp = client.get("/reports", headers=auth_header(make_es256_token()))
        assert resp.status_code == 503
        assert "database" in resp.json()["detail"].lower()

    def test_jwks_unreachable_returns_503(self, jwks_client) -> None:
        jwks_client.error = jwt.PyJWKClientConnectionError("timeout")
        resp = client.get("/reports", headers=auth_header(make_es256_token()))
        assert resp.status_code == 503


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
