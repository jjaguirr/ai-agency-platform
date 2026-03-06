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


class TestValidationErrorShape:
    """
    Schema validation failures (Pydantic → FastAPI's RequestValidationError)
    must conform to the same {type, detail} shape as every other error the
    API returns — and must NOT leak the regex pattern or echo the input
    value. Without a custom handler, FastAPI's default 422 body exposes
    both (plus a `ctx` dict with the raw pattern).
    """

    @pytest.fixture
    def client(self):
        return TestClient(_app())

    def test_422_body_has_type_and_detail_shape(self, client):
        """Missing required field → 422 in our standard shape."""
        resp = client.post(
            "/v1/customers/provision",
            json={"tier": "not-a-real-tier"},  # Literal violation
        )
        assert resp.status_code == 422
        body = resp.json()
        # Exact keys — not FastAPI's default {"detail": [{...}]} with
        # nested loc/msg/input/ctx. Our shape or nothing.
        assert set(body.keys()) == {"type", "detail"}
        assert body["type"] == "validation_error"
        assert isinstance(body["detail"], str)

    def test_422_does_not_leak_regex_pattern(self, client):
        """
        Injection attempt hits the customer_id pattern constraint.
        FastAPI's default would include `"pattern": "^[a-z0-9]..."`
        in the response — tells an attacker exactly what to craft next.
        Our handler must strip that.
        """
        resp = client.post(
            "/v1/customers/provision",
            json={"tier": "basic", "customer_id": "../../etc/passwd"},
        )
        assert resp.status_code == 422
        body_str = str(resp.json())
        # No fragment of the pattern should appear
        assert "[a-z0-9]" not in body_str
        assert "pattern" not in body_str.lower()
        assert "{2,47}" not in body_str

    def test_422_does_not_echo_input_value(self, client):
        """
        Pydantic v2 defaults include `"input": <rejected-value>` in the
        error. That means our "injection blocked" test would pass the
        422 status check while the response still contains the attack
        payload. Not a leak per se (client sent it), but it violates
        the "fixed, controlled error messages" policy.

        Test input needs to FAIL the regex (so 422 fires) while being
        distinctive enough to grep for in the response. Uppercase fails
        the pattern; the marker string is unlikely to collide with any
        legitimate error text.
        """
        marker = "MarkerXYZ9q7w-unlikely-collision"
        resp = client.post(
            "/v1/customers/provision",
            json={"tier": "basic", "customer_id": marker},
        )
        assert resp.status_code == 422
        assert marker not in str(resp.json())

    def test_422_still_tells_client_which_field(self, client):
        """
        Not leaking internals doesn't mean being unhelpfully opaque.
        The client should learn WHICH field failed so they can fix
        their request — just not the regex or their own echoed input.
        """
        resp = client.post(
            "/v1/customers/provision",
            json={"tier": "basic", "customer_id": "../../etc/passwd"},
        )
        assert resp.status_code == 422
        assert "customer_id" in resp.json()["detail"]

    @pytest.fixture
    def auth_headers(self):
        return {"Authorization": f"Bearer {create_token('cust_val')}"}

    def test_422_shape_consistent_across_routes(self, client, auth_headers):
        """
        Conversations route has its own schema (MessageRequest). Its
        validation errors must have the same shape — the handler is
        global, not per-route.
        """
        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "smoke-signals"},
            headers=auth_headers,
        )
        assert resp.status_code == 422
        body = resp.json()
        assert set(body.keys()) == {"type", "detail"}
        assert body["type"] == "validation_error"
        assert "channel" in body["detail"]
