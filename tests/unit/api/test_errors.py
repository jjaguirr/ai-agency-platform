"""
Exception-handler tests.

Structured JSON on every error, no stack traces in responses. HTTPException
keeps its status and detail; unhandled exceptions become generic 500s.

The EA's own fallback behavior isn't tested here — the conversation tests
already cover that the EA returns a degraded string (200) rather than raising.
These tests cover the residual case: something outside the EA blows up.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api.errors import register_exception_handlers


def _app_with_broken_route() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise-http")
    async def raise_http():
        raise HTTPException(status_code=418, detail="I'm a teapot")

    @app.get("/raise-unhandled")
    async def raise_unhandled():
        raise RuntimeError("internal path /etc/secrets leaked oh no")

    @app.get("/raise-value")
    async def raise_value():
        raise ValueError("something went wrong at line 42")

    # raise_server_exceptions=False → let our handlers run instead of TestClient
    # re-raising the exception in the test process.
    return TestClient(app, raise_server_exceptions=False)


# --- HTTPException passthrough ---------------------------------------------

class TestHTTPExceptionHandler:
    def test_preserves_status_code(self):
        client = _app_with_broken_route()
        resp = client.get("/raise-http")
        assert resp.status_code == 418

    def test_wraps_detail_in_structured_envelope(self):
        client = _app_with_broken_route()
        resp = client.get("/raise-http")
        body = resp.json()
        assert body == {"error": "I'm a teapot"}

    def test_content_type_is_json(self):
        client = _app_with_broken_route()
        resp = client.get("/raise-http")
        assert resp.headers["content-type"].startswith("application/json")


# --- Unhandled exceptions --------------------------------------------------

class TestUnhandledExceptionHandler:
    def test_returns_500(self):
        client = _app_with_broken_route()
        resp = client.get("/raise-unhandled")
        assert resp.status_code == 500

    def test_body_is_structured_json(self):
        client = _app_with_broken_route()
        resp = client.get("/raise-unhandled")
        body = resp.json()
        assert "error" in body
        assert body["error"]  # non-empty

    def test_does_not_leak_exception_message(self):
        client = _app_with_broken_route()
        resp = client.get("/raise-unhandled")
        assert "/etc/secrets" not in resp.text
        assert "RuntimeError" not in resp.text

    def test_does_not_leak_stack_trace(self):
        client = _app_with_broken_route()
        resp = client.get("/raise-unhandled")
        assert "Traceback" not in resp.text
        assert "File " not in resp.text
        assert ".py" not in resp.text

    def test_different_exception_types_same_generic_response(self):
        """The client shouldn't be able to distinguish exception types."""
        client = _app_with_broken_route()
        r1 = client.get("/raise-unhandled")  # RuntimeError
        r2 = client.get("/raise-value")       # ValueError
        assert r1.json() == r2.json()


# --- Integration with the real app -----------------------------------------

class TestRealAppErrorHandling:
    def test_404_on_unknown_route_is_structured(self, client):
        resp = client.get("/v1/nonexistent")
        assert resp.status_code == 404
        # FastAPI's built-in 404 for missing routes — our handler wraps it
        assert "error" in resp.json()

    def test_422_validation_error_still_useful(self, client, auth_header):
        """
        Pydantic validation errors carry field-level detail. We should NOT
        collapse those into a generic message — they're safe and helpful.
        """
        resp = client.post(
            "/v1/conversations/message",
            json={"channel": "chat"},  # missing required 'message'
            headers=auth_header(),
        )
        assert resp.status_code == 422
        # FastAPI's default: {"detail": [{"loc": [...], "msg": ..., "type": ...}]}.
        # Substring-matching "message" against resp.text would also match
        # e.g. the word "message" in an unrelated msg field. Check the
        # structure: the missing field is named in a loc path.
        detail = resp.json()["detail"]
        assert isinstance(detail, list) and len(detail) > 0
        locs = [tuple(err["loc"]) for err in detail]
        assert any("message" in loc for loc in locs), locs
