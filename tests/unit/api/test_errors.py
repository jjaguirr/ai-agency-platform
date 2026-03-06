"""
Structured error responses.

The API must never leak stack traces. Every non-2xx carries a JSON body
with {type, detail}. Unhandled exceptions get caught by a global handler
and mapped to a generic 500 without internals.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry
from src.api.errors import APIError, ServiceUnavailableError, BadRequestError


def _app():
    return create_app(
        ea_registry=EARegistry(factory=MagicMock()),
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=AsyncMock(),
    )


class TestErrorClasses:
    def test_api_error_carries_type_and_detail(self):
        err = APIError(status_code=418, error_type="teapot", detail="short and stout")
        assert err.status_code == 418
        assert err.error_type == "teapot"
        assert err.detail == "short and stout"

    def test_service_unavailable_is_503(self):
        err = ServiceUnavailableError(detail="redis down")
        assert err.status_code == 503
        assert err.error_type == "service_unavailable"

    def test_bad_request_is_400(self):
        err = BadRequestError(detail="bad tier")
        assert err.status_code == 400
        assert err.error_type == "bad_request"


class TestErrorResponses:
    def test_unhandled_exception_body_is_exactly_generic(self):
        """
        The catch-all handler must emit a FIXED body — not "no traceback"
        (weak; leaks can slip past substring checks), but "exactly this
        and nothing else". Any deviation means something leaked.
        """
        def bad_factory(cid):
            raise RuntimeError("mem0 connection refused; at line 42 in foo.py")

        app = create_app(
            ea_registry=EARegistry(factory=bad_factory),
            orchestrator=AsyncMock(),
            whatsapp_manager=MagicMock(),
            redis_client=AsyncMock(),
        )
        # Don't let TestClient re-raise; we want to see the rendered error.
        client = TestClient(app, raise_server_exceptions=False)
        tok = create_token("cust_err")

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat"},
            headers={"Authorization": f"Bearer {tok}"},
        )

        # Conversations route catches and wraps → 503 with our structured body.
        # If the wrap is removed, the global handler catches → 500 generic.
        # Either path must produce a body with NO internal detail.
        assert resp.status_code in (500, 503)
        body = resp.json()
        assert set(body.keys()) == {"type", "detail"}, \
            f"unexpected keys in error body: {body.keys()}"
        # The detail must be a known-safe message, never echo the exception
        assert body["detail"] in {
            "Assistant temporarily unavailable.",   # 503 from route wrapper
            "An internal error occurred.",           # 500 from global handler
        }, f"error detail leaked internal info: {body['detail']!r}"

    def test_api_error_subclasses_render_type_and_detail(self):
        """Intentionally-raised APIError → {type, detail} shape."""
        orch = AsyncMock()
        # Orchestrator's ValueError message could contain internals
        # (image tags, paths). We must NOT echo it.
        orch.provision_customer_environment = AsyncMock(
            side_effect=ValueError("docker image /internal/path:v3 bad"))
        app = create_app(
            ea_registry=EARegistry(factory=MagicMock()),
            orchestrator=orch,
            whatsapp_manager=MagicMock(),
            redis_client=AsyncMock(),
        )
        client = TestClient(app)

        resp = client.post("/v1/customers/provision", json={"tier": "basic"})

        assert resp.status_code == 400
        body = resp.json()
        assert body["type"] == "bad_request"
        # Fixed safe message — orchestrator internals don't leak
        assert body["detail"] == "Provisioning request rejected. Check tier and parameters."
        assert "/internal/path" not in str(body)

    def test_global_handler_does_not_swallow_http_exception(self):
        """
        Regression guard: our catch-all Exception handler must NOT
        intercept FastAPI's own HTTPException (404, 405, etc.). If it
        does, every missing route becomes a 500 "internal error".
        """
        client = TestClient(_app(), raise_server_exceptions=False)

        resp = client.get("/v1/definitely-not-a-route")

        # If our Exception handler caught HTTPException, this would be 500.
        assert resp.status_code == 404
        # And the body would be our generic "internal error" — it shouldn't be.
        assert resp.json().get("type") != "internal_error"
