"""
Health and readiness probe tests.

/health: liveness — process is up. No dependency checks. Load balancers hit
this; if it ever returns non-200, the container gets killed.

/ready: readiness — can we serve traffic? Checks downstream services (Redis).
Orchestrators use this to gate rollouts and pull unhealthy pods from rotation.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.health import router


def _app_with_redis(redis_client) -> TestClient:
    app = FastAPI()
    app.state.redis = redis_client
    app.include_router(router)
    return TestClient(app)


# --- /health ---------------------------------------------------------------

class TestHealth:
    def test_returns_200_unconditionally(self):
        # No redis on app.state — health must not touch it
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_returns_200_even_when_redis_is_down(self):
        down = MagicMock()
        down.ping = AsyncMock(side_effect=ConnectionError("redis dead"))
        client = _app_with_redis(down)

        resp = client.get("/health")
        assert resp.status_code == 200
        down.ping.assert_not_called()

    def test_requires_no_auth(self):
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        # No Authorization header
        resp = client.get("/health")
        assert resp.status_code == 200


# --- /ready ----------------------------------------------------------------

class TestReadiness:
    def test_returns_200_when_redis_responds(self):
        up = MagicMock()
        up.ping = AsyncMock(return_value=True)
        client = _app_with_redis(up)

        resp = client.get("/ready")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        up.ping.assert_awaited_once()

    def test_returns_503_when_redis_ping_raises(self):
        down = MagicMock()
        down.ping = AsyncMock(side_effect=ConnectionError("connection refused"))
        client = _app_with_redis(down)

        resp = client.get("/ready")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "not_ready"
        assert "redis" in body["failed"]

    def test_returns_503_when_redis_ping_times_out(self):
        down = MagicMock()
        down.ping = AsyncMock(side_effect=TimeoutError("ping timeout"))
        client = _app_with_redis(down)

        resp = client.get("/ready")
        assert resp.status_code == 503

    def test_returns_503_when_redis_not_configured(self):
        # App never set up redis — can't serve traffic
        app = FastAPI()
        app.state.redis = None
        app.include_router(router)
        client = TestClient(app)

        resp = client.get("/ready")
        assert resp.status_code == 503
        assert "redis" in resp.json()["failed"]

    def test_failure_detail_does_not_leak_internals(self):
        # The 503 body should name the failed component, not echo the
        # exception message (which might contain hostnames/ports).
        down = MagicMock()
        down.ping = AsyncMock(
            side_effect=ConnectionError("redis://internal-host:6379 refused")
        )
        client = _app_with_redis(down)

        resp = client.get("/ready")
        assert resp.status_code == 503
        body_text = resp.text
        assert "internal-host" not in body_text
        assert "6379" not in body_text

    def test_requires_no_auth(self):
        up = MagicMock()
        up.ping = AsyncMock(return_value=True)
        client = _app_with_redis(up)
        resp = client.get("/ready")
        assert resp.status_code == 200
