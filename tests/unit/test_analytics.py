"""
Analytics endpoints — activity summary and specialist status.

Activity data comes from Redis counters incremented when events happen.
Specialist status comes from the EA's delegation registry.
"""
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch


# --- App fixture with auth bypass ------------------------------------------

def _make_app(*, redis_overrides=None, ea_instance=None, n8n_client=None):
    """Build a test app with mocked deps and auth bypass."""
    from src.api.app import create_app
    from src.api.ea_registry import EARegistry

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.hgetall = AsyncMock(return_value={})

    if redis_overrides:
        original_get = mock_redis.get

        async def _get(key):
            if key in redis_overrides:
                return redis_overrides[key]
            return await original_get(key)

        mock_redis.get = _get

    ea_registry = MagicMock(spec=EARegistry)
    if ea_instance:
        ea_registry.get = AsyncMock(return_value=ea_instance)

    app = create_app(
        ea_registry=ea_registry,
        orchestrator=MagicMock(),
        whatsapp_manager=MagicMock(),
        redis_client=mock_redis,
    )
    app.state.n8n_client = n8n_client

    # Bypass JWT auth
    from src.api.auth import get_current_customer
    app.dependency_overrides[get_current_customer] = lambda: "cust_test"

    return app, mock_redis


class TestActivitySummary:
    def test_returns_zeros_when_no_counters(self):
        app, _ = _make_app()
        client = TestClient(app)

        resp = client.get("/v1/analytics/activity")
        assert resp.status_code == 200
        body = resp.json()
        assert body["messages_processed"] == 0
        assert body["specialist_delegations"] == {}
        assert body["proactive_triggers_sent"] == 0

    def test_returns_counter_values(self):
        today = date.today().isoformat()
        overrides = {
            f"analytics:cust_test:{today}:messages": "42",
            f"analytics:cust_test:{today}:proactive": "3",
        }
        app, mock_redis = _make_app(redis_overrides=overrides)

        # HGETALL for delegation breakdown
        mock_redis.hgetall = AsyncMock(return_value={
            b"finance": b"5", b"scheduling": b"3",
        })

        client = TestClient(app)
        resp = client.get("/v1/analytics/activity")

        assert resp.status_code == 200
        body = resp.json()
        assert body["messages_processed"] == 42
        assert body["specialist_delegations"] == {"finance": 5, "scheduling": 3}
        assert body["proactive_triggers_sent"] == 3

    def test_redis_failure_returns_zeros(self):
        app, mock_redis = _make_app()
        mock_redis.get = AsyncMock(side_effect=Exception("Redis down"))
        mock_redis.hgetall = AsyncMock(side_effect=Exception("Redis down"))

        client = TestClient(app)
        resp = client.get("/v1/analytics/activity")

        assert resp.status_code == 200
        body = resp.json()
        # All three counters must degrade gracefully to zero/empty
        assert body["messages_processed"] == 0
        assert body["specialist_delegations"] == {}
        assert body["proactive_triggers_sent"] == 0


class TestSpecialistStatus:
    def test_returns_registered_specialists(self):
        # Build a mock EA with a real delegation registry
        from src.agents.base.specialist import DelegationRegistry

        registry = DelegationRegistry()
        for domain in ("finance", "scheduling", "social_media", "workflows"):
            spec = MagicMock()
            spec.domain = domain
            registry.register(spec)

        mock_ea = MagicMock()
        mock_ea.delegation_registry = registry

        app, _ = _make_app(ea_instance=mock_ea)
        client = TestClient(app)

        resp = client.get("/v1/analytics/specialists")
        assert resp.status_code == 200
        body = resp.json()

        domains = {s["domain"] for s in body["specialists"]}
        assert domains == {"finance", "scheduling", "social_media", "workflows"}
        for s in body["specialists"]:
            assert s["registered"] is True
            assert s["operational"] is True
            # Non-workflow specialists must not have n8n_connected
            if s["domain"] != "workflows":
                assert s["n8n_connected"] is None

    def test_ea_registry_failure_returns_empty(self):
        """When the EA registry raises, specialists endpoint degrades to empty."""
        app, _ = _make_app(ea_instance=None)
        # Override ea_registry.get to raise
        app.state.ea_registry.get = AsyncMock(side_effect=Exception("no EA"))
        client = TestClient(app)

        resp = client.get("/v1/analytics/specialists")
        assert resp.status_code == 200
        assert resp.json()["specialists"] == []

    def test_workflows_shows_n8n_health(self):
        from src.agents.base.specialist import DelegationRegistry

        registry = DelegationRegistry()
        spec = MagicMock()
        spec.domain = "workflows"
        registry.register(spec)

        mock_ea = MagicMock()
        mock_ea.delegation_registry = registry

        mock_n8n = AsyncMock()
        mock_n8n.list_workflows = AsyncMock(return_value=[])

        app, _ = _make_app(ea_instance=mock_ea, n8n_client=mock_n8n)
        client = TestClient(app)

        resp = client.get("/v1/analytics/specialists")
        body = resp.json()

        wf = next(s for s in body["specialists"] if s["domain"] == "workflows")
        assert wf["n8n_connected"] is True

    def test_workflows_n8n_down(self):
        from src.agents.base.specialist import DelegationRegistry
        from src.workflows.client import N8nError

        registry = DelegationRegistry()
        spec = MagicMock()
        spec.domain = "workflows"
        registry.register(spec)

        mock_ea = MagicMock()
        mock_ea.delegation_registry = registry

        mock_n8n = AsyncMock()
        mock_n8n.list_workflows = AsyncMock(side_effect=N8nError("down"))

        app, _ = _make_app(ea_instance=mock_ea, n8n_client=mock_n8n)
        client = TestClient(app)

        resp = client.get("/v1/analytics/specialists")
        body = resp.json()

        wf = next(s for s in body["specialists"] if s["domain"] == "workflows")
        assert wf["n8n_connected"] is False
