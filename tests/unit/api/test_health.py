"""
Health + readiness probes.

/healthz — liveness. "Is the process up?" Always 200. No dependency checks.
/readyz  — readiness. "Should I get traffic?" Checks Redis + EA importable.

The distinction matters: a load balancer uses /healthz to decide whether
to restart the pod; an orchestrator uses /readyz to decide whether to
route requests. Conflating them causes cascading restarts when Redis blips.
"""
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app


@pytest.fixture
def app_healthy(mock_orchestrator, mock_whatsapp_manager, healthy_redis):
    from src.api.ea_registry import EARegistry
    from unittest.mock import MagicMock
    return create_app(
        ea_registry=EARegistry(factory=MagicMock()),
        orchestrator=mock_orchestrator,
        whatsapp_manager=mock_whatsapp_manager,
        redis_client=healthy_redis,
    )


@pytest.fixture
def app_redis_down(mock_orchestrator, mock_whatsapp_manager, broken_redis):
    from src.api.ea_registry import EARegistry
    from unittest.mock import MagicMock
    return create_app(
        ea_registry=EARegistry(factory=MagicMock()),
        orchestrator=mock_orchestrator,
        whatsapp_manager=mock_whatsapp_manager,
        redis_client=broken_redis,
    )


class TestHealthz:
    def test_returns_200_unconditionally(self, app_healthy):
        client = TestClient(app_healthy)
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_returns_200_even_when_redis_down(self, app_redis_down):
        client = TestClient(app_redis_down)
        resp = client.get("/healthz")
        assert resp.status_code == 200


class TestReadyz:
    def test_returns_200_when_all_deps_healthy(self, app_healthy):
        client = TestClient(app_healthy)
        resp = client.get("/readyz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["checks"]["redis"] == "ok"
        assert body["checks"]["ea"] == "ok"

    def test_returns_503_when_redis_down(self, app_redis_down):
        client = TestClient(app_redis_down)
        resp = client.get("/readyz")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["redis"] != "ok"

    def test_503_response_is_json_not_html(self, app_redis_down):
        client = TestClient(app_redis_down)
        resp = client.get("/readyz")
        assert resp.headers["content-type"].startswith("application/json")

    def test_readiness_reports_ea_importable(self, app_healthy):
        # EA check = "can we import ExecutiveAssistant". We always can in
        # tests because conftest imports it. This asserts the check field
        # exists rather than that it can ever fail.
        client = TestClient(app_healthy)
        resp = client.get("/readyz")
        assert "ea" in resp.json()["checks"]
