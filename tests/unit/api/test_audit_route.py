"""Tests for GET /v1/audit endpoint."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault(
    "JWT_SECRET", "test-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
)

from fastapi.testclient import TestClient

from src.api.auth import create_token
from src.safety.audit import AuditLogger


@pytest.fixture
def fake_redis():
    """Use connected_server so sync and async clients share the same data."""
    import fakeredis
    server = fakeredis.FakeServer()
    return fakeredis.aioredis.FakeRedis(server=server), server


@pytest.fixture
def audit_logger(fake_redis):
    async_redis, _ = fake_redis
    return AuditLogger(async_redis)


@pytest.fixture
def app(audit_logger, fake_redis, mock_ea_factory, mock_orchestrator, mock_whatsapp_manager, healthy_redis):
    from src.api.app import create_app
    from src.api.ea_registry import EARegistry

    registry = EARegistry(factory=mock_ea_factory, max_size=4)
    application = create_app(
        ea_registry=registry,
        orchestrator=mock_orchestrator,
        whatsapp_manager=mock_whatsapp_manager,
        redis_client=healthy_redis,
    )
    application.state.audit_logger = audit_logger
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def auth_headers():
    token = create_token("cust_test")
    return {"Authorization": f"Bearer {token}"}


class TestAuditEndpoint:
    def test_requires_auth(self, client):
        resp = client.get("/v1/audit")
        assert resp.status_code == 401

    def test_returns_empty_list(self, client, auth_headers):
        resp = client.get("/v1/audit", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["customer_id"] == "cust_test"
        assert body["events"] == []
        assert body["offset"] == 0

    def test_returns_logged_events(self, client, auth_headers, fake_redis):
        """Seed audit data via sync client sharing the same server."""
        import json
        import fakeredis as _fakeredis
        from datetime import datetime, timezone
        _, server = fake_redis
        sync_redis = _fakeredis.FakeRedis(server=server)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "injection_detected",
            "correlation_id": "req-1",
            "customer_id": "cust_test",
            "details": {"risk": 0.9},
        }
        sync_redis.rpush("audit:cust_test", json.dumps(event))
        resp = client.get("/v1/audit", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["events"]) == 1
        assert body["events"][0]["event_type"] == "injection_detected"

    def test_pagination_params(self, client, auth_headers):
        resp = client.get("/v1/audit?offset=10&limit=5", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["offset"] == 10
        assert body["limit"] == 5

    def test_invalid_offset_rejected(self, client, auth_headers):
        resp = client.get("/v1/audit?offset=-1", headers=auth_headers)
        assert resp.status_code == 422

    def test_invalid_limit_rejected(self, client, auth_headers):
        resp = client.get("/v1/audit?limit=0", headers=auth_headers)
        assert resp.status_code == 422

    def test_limit_max(self, client, auth_headers):
        resp = client.get("/v1/audit?limit=201", headers=auth_headers)
        assert resp.status_code == 422

    def test_customer_isolation(self, client, auth_headers, fake_redis):
        """Customer can only see their own audit events."""
        import json
        import fakeredis as _fakeredis
        from datetime import datetime, timezone
        _, server = fake_redis
        sync_redis = _fakeredis.FakeRedis(server=server)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "pii_redaction",
            "correlation_id": None,
            "customer_id": "cust_other",
            "details": {},
        }
        sync_redis.rpush("audit:cust_other", json.dumps(event))
        resp = client.get("/v1/audit", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["events"] == []
