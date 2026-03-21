"""
n8n health check in settings response.

GET /v1/settings should include live n8n connectivity in connected_services.
Calendar remains static False (no integration yet).
"""
import json

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.workflows.client import N8nError


def _make_app(*, n8n_client=None, settings_json=None):
    from src.api.app import create_app
    from src.api.ea_registry import EARegistry

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=settings_json)

    app = create_app(
        ea_registry=MagicMock(spec=EARegistry),
        orchestrator=MagicMock(),
        whatsapp_manager=MagicMock(),
        redis_client=mock_redis,
    )
    app.state.n8n_client = n8n_client

    from src.api.auth import get_current_customer
    app.dependency_overrides[get_current_customer] = lambda: "cust_test"

    return app


class TestN8nHealthInSettings:
    def test_n8n_true_when_healthy(self):
        mock_n8n = AsyncMock()
        mock_n8n.list_workflows = AsyncMock(return_value=[])

        app = _make_app(n8n_client=mock_n8n)
        client = TestClient(app)

        resp = client.get("/v1/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected_services"]["n8n"] is True

    def test_n8n_false_when_unreachable(self):
        mock_n8n = AsyncMock()
        mock_n8n.list_workflows = AsyncMock(side_effect=N8nError("down"))

        app = _make_app(n8n_client=mock_n8n)
        client = TestClient(app)

        resp = client.get("/v1/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected_services"]["n8n"] is False

    def test_n8n_false_when_no_client(self):
        app = _make_app(n8n_client=None)
        client = TestClient(app)

        resp = client.get("/v1/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected_services"]["n8n"] is False

    def test_calendar_always_false(self):
        app = _make_app(n8n_client=None)
        client = TestClient(app)

        resp = client.get("/v1/settings")
        body = resp.json()
        # No calendar integration yet
        assert body["connected_services"]["calendar"] is False

    def test_n8n_failure_does_not_break_settings(self):
        mock_n8n = AsyncMock()
        mock_n8n.list_workflows = AsyncMock(side_effect=Exception("unexpected"))

        app = _make_app(n8n_client=mock_n8n)
        client = TestClient(app)

        resp = client.get("/v1/settings")
        assert resp.status_code == 200
        body = resp.json()
        # All fields still present
        assert "working_hours" in body
        assert "personality" in body
        assert body["connected_services"]["n8n"] is False

    def test_n8n_health_overlays_stored_settings(self):
        """Even if stored settings say n8n=False, live check can override."""
        stored = json.dumps({
            "connected_services": {"calendar": False, "n8n": False},
            "personality": {"tone": "professional", "name": "Assistant", "language": "en"},
        })
        mock_n8n = AsyncMock()
        mock_n8n.list_workflows = AsyncMock(return_value=[])

        app = _make_app(n8n_client=mock_n8n, settings_json=stored)
        client = TestClient(app)

        resp = client.get("/v1/settings")
        body = resp.json()
        assert body["connected_services"]["n8n"] is True
