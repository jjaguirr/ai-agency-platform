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
    def test_404_has_json_body(self):
        client = TestClient(_app())
        resp = client.get("/v1/not-a-route")
        assert resp.status_code == 404
        # FastAPI's default 404 is JSON with detail — that's sufficient
        assert resp.headers["content-type"].startswith("application/json")

    def test_no_stack_trace_in_500(self):
        """
        When an EA factory explodes on first request, the caller should
        get a clean 503, not a Python traceback serialised into the body.
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

        assert resp.status_code in (500, 503)
        body_text = resp.text
        assert "Traceback" not in body_text
        assert "line 42" not in body_text
        assert "mem0" not in body_text  # no internal detail leakage

    def test_structured_error_has_type_field(self):
        """APIError subclasses should render with {type, detail}."""
        orch = AsyncMock()
        orch.provision_customer_environment = AsyncMock(
            side_effect=ValueError("bad tier"))
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
        assert set(body.keys()) >= {"type", "detail"}
