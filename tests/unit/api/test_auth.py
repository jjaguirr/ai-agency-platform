"""
JWT auth: token issuance + bearer extraction.

Scope: middleware behaviour only. No user management, no login — we just
verify that a signed token round-trips and that bad tokens get rejected.
"""
import time

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from jose import jwt

from src.api.auth import (
    create_token,
    decode_token,
    get_current_customer,
    InvalidTokenError,
)


# --- create / decode ------------------------------------------------------

class TestTokenRoundTrip:
    def test_token_carries_customer_id(self):
        tok = create_token("cust_42")
        payload = decode_token(tok)
        assert payload["customer_id"] == "cust_42"

    def test_token_has_expiry_in_future(self):
        tok = create_token("cust_42", expires_in=3600)
        payload = decode_token(tok)
        assert payload["exp"] > time.time()

    def test_expired_token_rejected(self):
        tok = create_token("cust_42", expires_in=-1)
        with pytest.raises(InvalidTokenError):
            decode_token(tok)

    def test_tampered_token_rejected(self, jwt_secret):
        tok = create_token("cust_42")
        # Re-sign with wrong secret — decode should refuse.
        forged = jwt.encode({"customer_id": "cust_evil"}, "wrong-secret",
                            algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            decode_token(forged)

    def test_malformed_token_rejected(self):
        with pytest.raises(InvalidTokenError):
            decode_token("not.a.jwt")

    def test_token_missing_customer_id_rejected(self, jwt_secret):
        # Valid signature but payload doesn't carry customer_id
        bad = jwt.encode({"sub": "whatever", "exp": time.time() + 60},
                         jwt_secret, algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            decode_token(bad)


# --- FastAPI dependency ---------------------------------------------------

def _mini_app() -> FastAPI:
    """Tiny app with one protected endpoint to exercise the dependency."""
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(customer_id: str = Depends(get_current_customer)):
        return {"customer_id": customer_id}

    return app


class TestAuthDependency:
    def test_valid_bearer_token_extracts_customer(self):
        client = TestClient(_mini_app())
        tok = create_token("cust_abc")

        resp = client.get("/whoami", headers={"Authorization": f"Bearer {tok}"})

        assert resp.status_code == 200
        assert resp.json() == {"customer_id": "cust_abc"}

    def test_missing_auth_header_returns_401(self):
        client = TestClient(_mini_app())
        resp = client.get("/whoami")
        assert resp.status_code == 401

    def test_wrong_scheme_returns_401(self):
        client = TestClient(_mini_app())
        tok = create_token("cust_abc")
        resp = client.get("/whoami", headers={"Authorization": f"Basic {tok}"})
        assert resp.status_code == 401

    def test_expired_bearer_returns_401(self):
        client = TestClient(_mini_app())
        tok = create_token("cust_abc", expires_in=-1)
        resp = client.get("/whoami", headers={"Authorization": f"Bearer {tok}"})
        assert resp.status_code == 401

    def test_401_body_is_fixed_message(self):
        """
        Invalid tokens get a fixed detail string. We don't echo jose's
        JWTError message — it can include token fragments or algorithm
        hints. Exact-match beats substring-check for leak detection.
        """
        client = TestClient(_mini_app())
        resp = client.get("/whoami", headers={"Authorization": "Bearer garbage"})
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Invalid or expired token"}
