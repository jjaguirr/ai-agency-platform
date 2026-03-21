"""
GET /v1/analytics/activity    — today's message/delegation/proactive counts
GET /v1/analytics/specialists — which specialist modules exist + are operational
GET /v1/analytics             — conversation intelligence analytics
"""
import json
import os

import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault(
    "JWT_SECRET", "test-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
)

import fakeredis.aioredis
import httpx
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def auth_headers():
    token = create_token("cust_analytics")
    return {"Authorization": f"Bearer {token}"}


def _app(*, redis=None, proactive_store=None, n8n_client=None, analytics_service=None):
    return create_app(
        ea_registry=EARegistry(factory=MagicMock(), max_size=10),
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=redis or AsyncMock(),
        proactive_state_store=proactive_store,
        n8n_client=n8n_client,
        analytics_service=analytics_service,
    )


# --- /v1/analytics/activity -------------------------------------------------

class TestActivityEndpoint:
    def test_requires_auth(self, fake_redis):
        client = TestClient(_app(redis=fake_redis))
        assert client.get("/v1/analytics/activity").status_code == 401

    @pytest.mark.asyncio
    async def test_returns_zeros_for_fresh_customer(self, fake_redis, auth_headers):
        from src.proactive.state import ProactiveStateStore
        store = ProactiveStateStore(fake_redis)
        client = TestClient(_app(redis=fake_redis, proactive_store=store))

        resp = client.get("/v1/analytics/activity", headers=auth_headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["messages_processed"] == 0
        assert body["delegations_by_domain"] == {}
        assert body["proactive_triggers_sent"] == 0
        assert "date" in body

    @pytest.mark.asyncio
    async def test_reflects_seeded_counters(self, fake_redis, auth_headers):
        from src.api.activity_counters import incr_messages, incr_delegation
        from src.proactive.state import ProactiveStateStore

        for _ in range(3):
            await incr_messages(fake_redis, "cust_analytics")
        await incr_delegation(fake_redis, "cust_analytics", "finance")
        await incr_delegation(fake_redis, "cust_analytics", "finance")
        await incr_delegation(fake_redis, "cust_analytics", "scheduling")

        store = ProactiveStateStore(fake_redis)
        await store.increment_daily_count("cust_analytics")

        app = _app(redis=fake_redis, proactive_store=store)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            resp = await c.get("/v1/analytics/activity", headers=auth_headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["messages_processed"] == 3
        assert body["delegations_by_domain"] == {"finance": 2, "scheduling": 1}
        assert body["proactive_triggers_sent"] == 1

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, fake_redis):
        from src.api.activity_counters import incr_messages
        from src.proactive.state import ProactiveStateStore

        await incr_messages(fake_redis, "cust_other")
        await incr_messages(fake_redis, "cust_other")

        store = ProactiveStateStore(fake_redis)
        client = TestClient(_app(redis=fake_redis, proactive_store=store))

        tok_a = create_token("cust_target")
        resp = client.get("/v1/analytics/activity",
                          headers={"Authorization": f"Bearer {tok_a}"})

        assert resp.json()["messages_processed"] == 0

    def test_no_proactive_store_reports_zero(self, fake_redis, auth_headers):
        client = TestClient(_app(redis=fake_redis, proactive_store=None))
        resp = client.get("/v1/analytics/activity", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["proactive_triggers_sent"] == 0


# --- /v1/analytics/specialists ----------------------------------------------

class TestSpecialistStatusEndpoint:
    def test_requires_auth(self, fake_redis):
        client = TestClient(_app(redis=fake_redis))
        assert client.get("/v1/analytics/specialists").status_code == 401

    def test_lists_all_four_domains(self, fake_redis, auth_headers):
        client = TestClient(_app(redis=fake_redis))
        resp = client.get("/v1/analytics/specialists", headers=auth_headers)

        assert resp.status_code == 200
        domains = {s["domain"] for s in resp.json()["specialists"]}
        assert domains == {"finance", "scheduling", "social_media", "workflows"}

    def test_specialists_registered_when_modules_import(self, fake_redis, auth_headers):
        client = TestClient(_app(redis=fake_redis))
        resp = client.get("/v1/analytics/specialists", headers=auth_headers)

        for s in resp.json()["specialists"]:
            assert s["registered"] is True, f"{s['domain']} failed to import"

    def test_workflows_operational_when_n8n_healthy(self, fake_redis, auth_headers):
        n8n = MagicMock()
        n8n.list_workflows = AsyncMock(return_value=[{"id": "wf_1"}])
        client = TestClient(_app(redis=fake_redis, n8n_client=n8n))

        resp = client.get("/v1/analytics/specialists", headers=auth_headers)

        wf = next(s for s in resp.json()["specialists"] if s["domain"] == "workflows")
        assert wf["operational"] is True
        assert wf["detail"] is None

    def test_workflows_not_operational_when_n8n_raises(self, fake_redis, auth_headers):
        from src.workflows.client import N8nError
        n8n = MagicMock()
        n8n.list_workflows = AsyncMock(side_effect=N8nError("502 bad gateway"))
        client = TestClient(_app(redis=fake_redis, n8n_client=n8n))

        resp = client.get("/v1/analytics/specialists", headers=auth_headers)

        wf = next(s for s in resp.json()["specialists"] if s["domain"] == "workflows")
        assert wf["operational"] is False
        assert "502" in wf["detail"]

    def test_workflows_not_operational_without_n8n_client(self, fake_redis, auth_headers):
        client = TestClient(_app(redis=fake_redis, n8n_client=None))
        resp = client.get("/v1/analytics/specialists", headers=auth_headers)

        wf = next(s for s in resp.json()["specialists"] if s["domain"] == "workflows")
        assert wf["registered"] is True
        assert wf["operational"] is False
        assert "not configured" in wf["detail"].lower()

    def test_non_workflow_specialists_operational_equals_registered(
            self, fake_redis, auth_headers):
        client = TestClient(_app(redis=fake_redis))
        resp = client.get("/v1/analytics/specialists", headers=auth_headers)

        for s in resp.json()["specialists"]:
            if s["domain"] != "workflows":
                assert s["operational"] == s["registered"]

    def test_n8n_probe_failure_does_not_500(self, fake_redis, auth_headers):
        n8n = MagicMock()
        n8n.list_workflows = AsyncMock(side_effect=RuntimeError("weird"))
        client = TestClient(_app(redis=fake_redis, n8n_client=n8n))

        resp = client.get("/v1/analytics/specialists", headers=auth_headers)
        assert resp.status_code == 200


# --- Counter bumps from the conversations route -----------------------------

class TestConversationsRouteBumpsCounters:
    @pytest.mark.asyncio
    async def test_post_message_increments_message_counter(
            self, fake_redis, auth_headers):
        from src.api.activity_counters import get_today

        ea = AsyncMock()
        ea.handle_customer_interaction = AsyncMock(return_value="reply")
        ea.last_specialist_domain = None

        app = create_app(
            ea_registry=EARegistry(factory=lambda cid: ea),
            orchestrator=AsyncMock(),
            whatsapp_manager=MagicMock(),
            redis_client=fake_redis,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            resp = await c.post("/v1/conversations/message",
                                json={"message": "hi", "channel": "chat"},
                                headers=auth_headers)
        assert resp.status_code == 200

        today = await get_today(fake_redis, "cust_analytics")
        assert today["messages"] == 1

    @pytest.mark.asyncio
    async def test_post_message_increments_delegation_when_specialist_engaged(
            self, fake_redis, auth_headers):
        from src.api.activity_counters import get_today

        ea = AsyncMock()
        ea.handle_customer_interaction = AsyncMock(return_value="Booked for 3pm")
        ea.last_specialist_domain = "scheduling"

        app = create_app(
            ea_registry=EARegistry(factory=lambda cid: ea),
            orchestrator=AsyncMock(),
            whatsapp_manager=MagicMock(),
            redis_client=fake_redis,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            await c.post("/v1/conversations/message",
                         json={"message": "book meeting", "channel": "chat"},
                         headers=auth_headers)

        today = await get_today(fake_redis, "cust_analytics")
        assert today["messages"] == 1
        assert today["delegations"].get("scheduling") == 1

    @pytest.mark.asyncio
    async def test_counter_failure_does_not_break_response(
            self, auth_headers):
        ea = AsyncMock()
        ea.handle_customer_interaction = AsyncMock(return_value="important reply")
        ea.last_specialist_domain = None

        broken_redis = AsyncMock()
        broken_redis.incr = AsyncMock(side_effect=ConnectionError("gone"))

        app = create_app(
            ea_registry=EARegistry(factory=lambda cid: ea),
            orchestrator=AsyncMock(),
            whatsapp_manager=MagicMock(),
            redis_client=broken_redis,
        )
        client = TestClient(app)

        resp = client.post("/v1/conversations/message",
                           json={"message": "hi", "channel": "chat"},
                           headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["response"] == "important reply"


# --- GET /v1/analytics (conversation intelligence) --------------------------

class TestAnalyticsAuth:
    def test_401_without_token(self):
        client = TestClient(_app())
        resp = client.get("/v1/analytics")
        assert resp.status_code == 401

    def test_401_with_expired_token(self):
        client = TestClient(_app())
        tok = create_token("cust_a", expires_in=-1)
        resp = client.get(
            "/v1/analytics",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 401


class TestAnalyticsParams:
    def test_default_period_is_7d(self):
        svc = AsyncMock()
        svc.get_analytics = AsyncMock(return_value={
            "period": {"start": "2026-03-14T00:00:00Z", "end": "2026-03-21T00:00:00Z"},
            "overview": {
                "total_conversations": 0,
                "total_delegations": 0,
                "avg_messages_per_conversation": 0.0,
                "escalation_rate": 0.0,
                "unresolved_rate": 0.0,
            },
            "topics": {"breakdown": []},
            "specialist_performance": [],
            "trends": {"conversations_by_day": [], "delegations_by_day": []},
        })
        client = TestClient(_app(analytics_service=svc))
        tok = create_token("cust_a")

        resp = client.get(
            "/v1/analytics",
            headers={"Authorization": f"Bearer {tok}"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "overview" in body
        assert "topics" in body
        assert "specialist_performance" in body
        assert "trends" in body

    def test_invalid_period_returns_422(self):
        client = TestClient(_app())
        tok = create_token("cust_a")

        resp = client.get(
            "/v1/analytics?period=invalid",
            headers={"Authorization": f"Bearer {tok}"},
        )

        assert resp.status_code == 422

    def test_custom_period_requires_dates(self):
        svc = AsyncMock()
        svc.get_analytics = AsyncMock(side_effect=ValueError("start and end required"))
        client = TestClient(_app(analytics_service=svc))
        tok = create_token("cust_a")

        resp = client.get(
            "/v1/analytics?period=custom",
            headers={"Authorization": f"Bearer {tok}"},
        )

        assert resp.status_code == 400


class TestAnalyticsNoService:
    def test_returns_503_when_service_unavailable(self):
        client = TestClient(_app(analytics_service=None))
        tok = create_token("cust_a")

        resp = client.get(
            "/v1/analytics",
            headers={"Authorization": f"Bearer {tok}"},
        )

        assert resp.status_code == 503
