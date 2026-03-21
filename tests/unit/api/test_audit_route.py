"""
GET /v1/audit — customer's own audit trail, newest-first, paginated.

"Admin-scoped, same auth" means: same JWT dependency as conversations,
customer sees their own events. No new claim. Tenant isolation is the
Redis key prefix — AuditLogger keys on customer_id.

pipeline=None → empty list, not 500, so unrelated tests that omit the
pipeline keep passing.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

import fakeredis
import fakeredis.aioredis

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry
from src.safety.audit import AuditLogger
from src.safety.config import SafetyConfig
from src.safety.models import AuditEvent, AuditEventType
from src.safety.pipeline import SafetyPipeline


# TestClient runs the app in its own event loop (anyio portal). The
# async test body runs in pytest-asyncio's loop. FakeRedis binds its
# internal asyncio.Queue to whichever loop first awaits it — so seeding
# in the test loop and then reading via the route (TestClient's loop)
# trips "bound to a different event loop".
#
# FakeServer is the shared in-memory store; each FakeRedis(server=...)
# is a separate connection that binds to its own loop. The pipeline's
# client binds to TestClient's loop on first route call; _seed uses a
# fresh client that binds to the test's loop. Same data, no crossing.

@pytest.fixture
def fake_server():
    return fakeredis.FakeServer()


@pytest.fixture
def pipeline(fake_server):
    redis = fakeredis.aioredis.FakeRedis(server=fake_server)
    return SafetyPipeline(SafetyConfig(), AuditLogger(redis))


def _app(*, safety_pipeline=None):
    registry = EARegistry(factory=lambda cid: AsyncMock())
    return create_app(
        ea_registry=registry,
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=AsyncMock(),
        conversation_repo=None,
        safety_pipeline=safety_pipeline,
    )


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {create_token('cust_audit')}"}


async def _seed(server: fakeredis.FakeServer, customer_id: str, n: int):
    # Fresh client — binds to the caller's (test body's) event loop.
    logger = AuditLogger(fakeredis.aioredis.FakeRedis(server=server))
    for i in range(n):
        await logger.log(customer_id, AuditEvent(
            timestamp=f"2026-03-20T10:00:{i:02d}Z",
            event_type=AuditEventType.PROMPT_INJECTION_DETECTED,
            correlation_id=f"corr-{i}",
            details={"seq": i},
        ))


# --- Auth --------------------------------------------------------------------

class TestAuth:
    def test_no_token_401(self, pipeline):
        client = TestClient(_app(safety_pipeline=pipeline))
        resp = client.get("/v1/audit")
        assert resp.status_code == 401

    def test_bad_token_401(self, pipeline):
        client = TestClient(_app(safety_pipeline=pipeline))
        resp = client.get(
            "/v1/audit",
            headers={"Authorization": "Bearer garbage.token.here"},
        )
        assert resp.status_code == 401


# --- Listing -----------------------------------------------------------------

class TestListing:
    @pytest.mark.asyncio
    async def test_returns_events_newest_first(
        self, pipeline, fake_server, auth_headers,
    ):
        await _seed(fake_server, "cust_audit", 3)
        client = TestClient(_app(safety_pipeline=pipeline))

        resp = client.get("/v1/audit", headers=auth_headers)

        assert resp.status_code == 200
        events = resp.json()["events"]
        assert len(events) == 3
        # Newest first — seq 2, 1, 0
        assert [e["details"]["seq"] for e in events] == [2, 1, 0]
        assert events[0]["event_type"] == "prompt_injection_detected"
        assert events[0]["correlation_id"] == "corr-2"

    @pytest.mark.asyncio
    async def test_empty_when_no_events(self, pipeline, auth_headers):
        client = TestClient(_app(safety_pipeline=pipeline))
        resp = client.get("/v1/audit", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["events"] == []

    @pytest.mark.asyncio
    async def test_pagination_limit(self, pipeline, fake_server, auth_headers):
        await _seed(fake_server, "cust_audit", 10)
        client = TestClient(_app(safety_pipeline=pipeline))

        resp = client.get("/v1/audit?limit=3", headers=auth_headers)
        events = resp.json()["events"]
        assert len(events) == 3
        assert [e["details"]["seq"] for e in events] == [9, 8, 7]

    @pytest.mark.asyncio
    async def test_pagination_offset(self, pipeline, fake_server, auth_headers):
        await _seed(fake_server, "cust_audit", 10)
        client = TestClient(_app(safety_pipeline=pipeline))

        resp = client.get("/v1/audit?limit=3&offset=3", headers=auth_headers)
        events = resp.json()["events"]
        assert [e["details"]["seq"] for e in events] == [6, 5, 4]

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, pipeline, fake_server):
        """cust_other's events must not appear in cust_audit's trail."""
        await _seed(fake_server, "cust_audit", 2)
        await _seed(fake_server, "cust_other", 5)

        client = TestClient(_app(safety_pipeline=pipeline))
        resp = client.get(
            "/v1/audit",
            headers={"Authorization": f"Bearer {create_token('cust_audit')}"},
        )
        assert len(resp.json()["events"]) == 2


# --- Degradation -------------------------------------------------------------

class TestDegradation:
    def test_no_pipeline_returns_empty_not_500(self, auth_headers):
        client = TestClient(_app(safety_pipeline=None))
        resp = client.get("/v1/audit", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["events"] == []

    def test_limit_validation(self, pipeline, auth_headers):
        client = TestClient(_app(safety_pipeline=pipeline))
        # Over the max
        assert client.get("/v1/audit?limit=500",
                          headers=auth_headers).status_code == 422
        # Negative offset
        assert client.get("/v1/audit?offset=-1",
                          headers=auth_headers).status_code == 422
