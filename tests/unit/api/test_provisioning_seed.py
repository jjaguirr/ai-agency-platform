"""
Provisioning enhancement — seed defaults so a freshly provisioned
customer can message the EA AND log into the dashboard with zero
manual steps.

Added behaviour on POST /v1/customers/provision:
  - settings:{customer_id}      — default Settings written to Redis
  - onboarding:{customer_id}    — initialized to not_started
  - auth:{customer_id}:secret   — random dashboard secret, returned
                                  in response body

Demo mode (demo=true in request):
  - runs seed_demo_account instead
  - onboarding marked completed
  - sample notifications + activity + settings populated

FakeServer note: TestClient runs the app in its own event loop (anyio
portal). Verification runs in pytest-asyncio's loop. A FakeRedis
instance binds its queue to whichever loop first awaits it, so the app
and the verification step need separate clients backed by the same
FakeServer — shared data, no loop crossing.
"""
import json

import pytest
import fakeredis
import fakeredis.aioredis
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.api.app import create_app
from src.api.ea_registry import EARegistry


@pytest.fixture
def fake_server():
    return fakeredis.FakeServer()


def _app(orchestrator, server, conversation_repo=None):
    # Fresh client for the app — binds to TestClient's event loop.
    redis = fakeredis.aioredis.FakeRedis(server=server)
    return create_app(
        ea_registry=EARegistry(factory=MagicMock()),
        orchestrator=orchestrator,
        whatsapp_manager=MagicMock(),
        redis_client=redis,
        conversation_repo=conversation_repo,
    )


async def _read(server, key, *, hash=False):
    """Read from the shared FakeServer on the test body's loop."""
    r = fakeredis.aioredis.FakeRedis(server=server)
    return await (r.hgetall(key) if hash else r.get(key))


class TestDefaultSeeding:
    async def test_seeds_default_settings(self, mock_orchestrator, fake_server):
        client = TestClient(_app(mock_orchestrator, fake_server))

        resp = client.post("/v1/customers/provision",
                           json={"customer_id": "cust_fresh", "tier": "basic"})

        assert resp.status_code == 201
        raw = await _read(fake_server, "settings:cust_fresh")
        settings = json.loads(raw)
        assert settings["working_hours"]["start"] == "09:00"
        assert settings["personality"]["name"] == "Assistant"

    async def test_initializes_onboarding_state(self, mock_orchestrator, fake_server):
        client = TestClient(_app(mock_orchestrator, fake_server))

        client.post("/v1/customers/provision",
                    json={"customer_id": "cust_fresh", "tier": "basic"})

        raw = await _read(fake_server, "onboarding:cust_fresh")
        state = json.loads(raw)
        assert state["status"] == "not_started"

    async def test_creates_dashboard_auth_secret(self, mock_orchestrator, fake_server):
        client = TestClient(_app(mock_orchestrator, fake_server))

        resp = client.post("/v1/customers/provision",
                           json={"customer_id": "cust_fresh", "tier": "basic"})

        body = resp.json()
        assert body["dashboard_secret"]
        assert len(body["dashboard_secret"]) >= 20

        stored = await _read(fake_server, "auth:cust_fresh:secret")
        assert stored.decode() == body["dashboard_secret"]

    def test_seeding_failure_does_not_block_provision(self, mock_orchestrator):
        """Redis down during seeding → customer still gets their token.
        Seeding is best-effort; infra provisioning is the critical path."""
        broken = AsyncMock()
        broken.set = AsyncMock(side_effect=ConnectionError("redis down"))
        broken.get = AsyncMock(side_effect=ConnectionError("redis down"))
        app = create_app(
            ea_registry=EARegistry(factory=MagicMock()),
            orchestrator=mock_orchestrator,
            whatsapp_manager=MagicMock(),
            redis_client=broken,
        )
        client = TestClient(app)

        resp = client.post("/v1/customers/provision", json={"tier": "basic"})

        assert resp.status_code == 201
        assert resp.json()["token"]
        assert resp.json()["dashboard_secret"] is None


class TestDemoMode:
    async def test_demo_flag_marks_onboarding_complete(
        self, mock_orchestrator, fake_server
    ):
        client = TestClient(_app(mock_orchestrator, fake_server))

        client.post("/v1/customers/provision",
                    json={"customer_id": "demo_acme", "tier": "basic",
                          "demo": True})

        raw = await _read(fake_server, "onboarding:demo_acme")
        state = json.loads(raw)
        assert state["status"] == "completed"

    async def test_demo_seeds_notifications(self, mock_orchestrator, fake_server):
        client = TestClient(_app(mock_orchestrator, fake_server))

        client.post("/v1/customers/provision",
                    json={"customer_id": "demo_acme", "demo": True})

        notifs = await _read(fake_server, "proactive:demo_acme:notifications",
                             hash=True)
        assert len(notifs) >= 3

    async def test_demo_seeds_friendly_settings(self, mock_orchestrator, fake_server):
        client = TestClient(_app(mock_orchestrator, fake_server))

        client.post("/v1/customers/provision",
                    json={"customer_id": "demo_acme", "demo": True})

        raw = await _read(fake_server, "settings:demo_acme")
        settings = json.loads(raw)
        assert settings["personality"]["tone"] == "friendly"
        assert settings["briefing"]["enabled"] is True

    async def test_demo_false_uses_normal_seeding(
        self, mock_orchestrator, fake_server
    ):
        client = TestClient(_app(mock_orchestrator, fake_server))

        client.post("/v1/customers/provision",
                    json={"customer_id": "cust_real", "demo": False})

        raw = await _read(fake_server, "onboarding:cust_real")
        state = json.loads(raw)
        assert state["status"] == "not_started"  # not demo-completed

    def test_demo_seeds_conversations_when_repo_available(
        self, mock_orchestrator, fake_server
    ):
        created = []

        class FakeRepo:
            async def create_conversation(self, **kw):
                created.append(kw)
                return kw["conversation_id"]

            async def append_message(self, **kw):
                pass

        client = TestClient(_app(mock_orchestrator, fake_server,
                                 conversation_repo=FakeRepo()))
        client.post("/v1/customers/provision",
                    json={"customer_id": "demo_acme", "demo": True})

        assert len(created) >= 3
        assert all(c["customer_id"] == "demo_acme" for c in created)
