"""
Auth middleware tests.

Covers: token generation, decode, expiry, signature tampering, and the
FastAPI dependency that extracts the customer from the Authorization header.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from src.api.auth import (
    AuthError,
    create_token,
    decode_token,
    require_auth,
)

SECRET = "unit-test-secret"


# --- Token round-trip ------------------------------------------------------

class TestCreateToken:
    def test_encodes_customer_id_as_subject(self):
        token = create_token("cust_abc", secret=SECRET)
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        assert payload["sub"] == "cust_abc"

    def test_includes_expiry_claim(self):
        token = create_token("cust_abc", secret=SECRET)
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        assert "exp" in payload

    def test_respects_expires_delta(self):
        short = create_token("c", secret=SECRET, expires_delta=timedelta(seconds=1))
        long = create_token("c", secret=SECRET, expires_delta=timedelta(hours=24))
        p_short = jwt.decode(short, SECRET, algorithms=["HS256"])
        p_long = jwt.decode(long, SECRET, algorithms=["HS256"])
        assert p_long["exp"] > p_short["exp"]

    def test_different_secrets_produce_different_signatures(self):
        t1 = create_token("cust_x", secret="secret-a")
        t2 = create_token("cust_x", secret="secret-b")
        # Same payload, different sig → tail differs
        assert t1.rsplit(".", 1)[1] != t2.rsplit(".", 1)[1]


class TestDecodeToken:
    def test_returns_customer_id_for_valid_token(self):
        token = create_token("cust_valid", secret=SECRET)
        assert decode_token(token, secret=SECRET) == "cust_valid"

    def test_rejects_expired_token(self):
        token = create_token(
            "cust_old",
            secret=SECRET,
            expires_delta=timedelta(seconds=-10),  # already expired
        )
        with pytest.raises(AuthError, match="expired"):
            decode_token(token, secret=SECRET)

    def test_rejects_wrong_signature(self):
        token = create_token("cust_x", secret="real-secret")
        with pytest.raises(AuthError):
            decode_token(token, secret="attacker-guess")

    def test_rejects_tampered_payload(self):
        token = create_token("cust_x", secret=SECRET)
        header, payload, sig = token.split(".")
        # Flip one char in the payload; signature no longer matches
        tampered = f"{header}.{payload[:-1]}X.{sig}"
        with pytest.raises(AuthError):
            decode_token(tampered, secret=SECRET)

    def test_rejects_token_without_subject(self):
        # Craft a token that's validly signed but missing 'sub'
        bad = jwt.encode({"exp": 9999999999}, SECRET, algorithm="HS256")
        with pytest.raises(AuthError, match="subject"):
            decode_token(bad, secret=SECRET)

    def test_rejects_garbage(self):
        with pytest.raises(AuthError):
            decode_token("not-a-jwt", secret=SECRET)


# --- FastAPI dependency ----------------------------------------------------

def _mini_app() -> FastAPI:
    """Tiny app exposing a single protected route for dependency testing."""
    app = FastAPI()
    app.state.jwt_secret = SECRET

    @app.get("/protected")
    async def protected(customer_id: str = Depends(require_auth)):
        return {"customer_id": customer_id}

    return app


class TestRequireAuthDependency:
    def test_valid_bearer_token_extracts_customer_id(self):
        client = TestClient(_mini_app())
        token = create_token("cust_dep", secret=SECRET)
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json() == {"customer_id": "cust_dep"}

    def test_missing_header_returns_401(self):
        client = TestClient(_mini_app())
        resp = client.get("/protected")
        assert resp.status_code == 401

    def test_non_bearer_scheme_returns_401(self):
        client = TestClient(_mini_app())
        token = create_token("cust_x", secret=SECRET)
        resp = client.get("/protected", headers={"Authorization": f"Basic {token}"})
        assert resp.status_code == 401

    def test_malformed_header_returns_401(self):
        client = TestClient(_mini_app())
        resp = client.get("/protected", headers={"Authorization": "Bearer"})
        assert resp.status_code == 401

    def test_expired_token_returns_401(self):
        client = TestClient(_mini_app())
        token = create_token("cust_x", secret=SECRET, expires_delta=timedelta(seconds=-1))
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_wrong_secret_returns_401(self):
        client = TestClient(_mini_app())
        token = create_token("cust_x", secret="wrong-secret")
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_401_includes_www_authenticate_header(self):
        # RFC 6750 — Bearer token failures should advertise the scheme
        client = TestClient(_mini_app())
        resp = client.get("/protected")
        assert resp.headers.get("WWW-Authenticate") == "Bearer"
