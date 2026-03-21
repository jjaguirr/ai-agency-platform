"""
GET /v1/analytics/activity    — today's message/delegation/proactive counts
GET /v1/analytics/specialists — which specialist modules exist + are operational

Both dashboard backend endpoints. Neither writes anything. Both require auth.

Activity reads three Redis sources: our own activity:* counters (messages,
delegations-by-domain), and ProactiveStateStore.get_daily_count for the
proactive number. All zero when no traffic yet.

Specialist status iterates the fixed four-domain list. "Registered" means
the module imports cleanly; "operational" additionally checks external
deps (only workflows → n8n for now; the others have no external service
to probe so operational == registered).
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


def _app(*, redis, proactive_store=None, n8n_client=None):
    return create_app(
        ea_registry=EARegistry(factory=MagicMock(), max_size=10),
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=redis,
        proactive_state_store=proactive_store,
        n8n_client=n8n_client,
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
        # date in the body so the dashboard can label the card.
        assert "date" in body

    @pytest.mark.asyncio
    async def test_reflects_seeded_counters(self, fake_redis, auth_headers):
        """Pre-seed via the counter helpers → endpoint reads them back.

        Uses ASGITransport, not TestClient — TestClient runs the app in
        a worker-thread event loop, and fakeredis's internal queue is
        bound to whichever loop created it (this one). Crossing loops
        gets "Queue bound to a different event loop" swallowed silently
        by the endpoint's failure-→-zeros fallback.
        """
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
        """Customer B's traffic doesn't show in A's activity."""
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
        """proactive_state_store=None (test configs, early startup) →
        proactive count is 0, endpoint still works."""
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
        """finance, scheduling, social_media, workflows — the full set,
        regardless of which ones are healthy. Dashboard needs to render
        four tiles."""
        client = TestClient(_app(redis=fake_redis))
        resp = client.get("/v1/analytics/specialists", headers=auth_headers)

        assert resp.status_code == 200
        domains = {s["domain"] for s in resp.json()["specialists"]}
        assert domains == {"finance", "scheduling", "social_media", "workflows"}

    def test_specialists_registered_when_modules_import(self, fake_redis, auth_headers):
        """The four specialist modules exist in this repo → all
        registered=True. If one ever grows a broken import (optional
        dep missing, say) this flips and the dashboard shows it red."""
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
        """N8nError → operational=False with the error message in detail
        so the dashboard can show WHY, not just a red dot."""
        from src.workflows.client import N8nError
        n8n = MagicMock()
        n8n.list_workflows = AsyncMock(side_effect=N8nError("502 bad gateway"))
        client = TestClient(_app(redis=fake_redis, n8n_client=n8n))

        resp = client.get("/v1/analytics/specialists", headers=auth_headers)

        wf = next(s for s in resp.json()["specialists"] if s["domain"] == "workflows")
        assert wf["operational"] is False
        assert "502" in wf["detail"]

    def test_workflows_not_operational_without_n8n_client(self, fake_redis, auth_headers):
        """n8n_client=None → registered but not operational. Module
        imports fine; there's just nothing to talk to."""
        client = TestClient(_app(redis=fake_redis, n8n_client=None))
        resp = client.get("/v1/analytics/specialists", headers=auth_headers)

        wf = next(s for s in resp.json()["specialists"] if s["domain"] == "workflows")
        assert wf["registered"] is True
        assert wf["operational"] is False
        assert "not configured" in wf["detail"].lower()

    def test_non_workflow_specialists_operational_equals_registered(
            self, fake_redis, auth_headers):
        """finance/scheduling/social_media have no external service to
        probe yet. operational mirrors registered until they do."""
        client = TestClient(_app(redis=fake_redis))
        resp = client.get("/v1/analytics/specialists", headers=auth_headers)

        for s in resp.json()["specialists"]:
            if s["domain"] != "workflows":
                assert s["operational"] == s["registered"]

    def test_n8n_probe_failure_does_not_500(self, fake_redis, auth_headers):
        """Same contract as the settings probe — this is a status page,
        it reports the failure, it doesn't become the failure."""
        n8n = MagicMock()
        n8n.list_workflows = AsyncMock(side_effect=RuntimeError("weird"))
        client = TestClient(_app(redis=fake_redis, n8n_client=n8n))

        resp = client.get("/v1/analytics/specialists", headers=auth_headers)
        assert resp.status_code == 200


# --- Counter bumps from the conversations route -----------------------------
# The /v1/conversations/message POST should bump the message counter
# after a successful EA interaction, and the delegation counter if
# ea.last_specialist_domain is set. Fire-and-forget — a counter failure
# doesn't 500 the reply.

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
        # ASGITransport so the route and the assertion below share one
        # event loop — fakeredis's connection queue is loop-bound.
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
        """Counter increment raises → still 200 with the EA reply.
        The customer sees their answer; ops loses one data point."""
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
