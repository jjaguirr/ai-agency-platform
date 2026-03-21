"""Tests for RateLimitMiddleware — Redis-backed ASGI rate limiter."""
import os
import pytest

os.environ.setdefault(
    "JWT_SECRET", "test-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
)

import httpx
from httpx import ASGITransport

from src.api.auth import create_token
from src.safety.config import SafetyConfig


def _build_app(redis_client, *, config=None):
    """Build a minimal app with rate limiter middleware."""
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from src.safety.rate_limiter import RateLimitMiddleware

    cfg = config or SafetyConfig(per_customer_per_minute=5, per_customer_per_day=20, global_rps=10)

    app = FastAPI()
    app.state.redis_client = redis_client

    @app.post("/v1/conversations/message")
    async def message(request: Request):
        return JSONResponse({"response": "ok"})

    @app.get("/healthz")
    async def healthz():
        return JSONResponse({"status": "ok"})

    app.add_middleware(RateLimitMiddleware, redis_client=redis_client, config=cfg)
    return app


@pytest.fixture
def fake_redis():
    import fakeredis.aioredis
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def auth_headers():
    token = create_token("cust_test")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_other():
    token = create_token("cust_other")
    return {"Authorization": f"Bearer {token}"}


class TestPerCustomerMinuteLimit:
    async def test_under_limit_passes(self, fake_redis, auth_headers):
        app = _build_app(fake_redis)
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/v1/conversations/message", headers=auth_headers,
                               json={"message": "hi", "channel": "chat"})
            assert resp.status_code == 200

    async def test_at_limit_returns_429(self, fake_redis, auth_headers):
        app = _build_app(fake_redis)
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            for _ in range(5):
                resp = await c.post("/v1/conversations/message", headers=auth_headers,
                                   json={"message": "hi", "channel": "chat"})
                assert resp.status_code == 200

            resp = await c.post("/v1/conversations/message", headers=auth_headers,
                               json={"message": "hi", "channel": "chat"})
            assert resp.status_code == 429

    async def test_429_includes_retry_after(self, fake_redis, auth_headers):
        app = _build_app(fake_redis)
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            for _ in range(5):
                await c.post("/v1/conversations/message", headers=auth_headers,
                            json={"message": "hi", "channel": "chat"})

            resp = await c.post("/v1/conversations/message", headers=auth_headers,
                               json={"message": "hi", "channel": "chat"})
            assert resp.status_code == 429
            assert "retry-after" in resp.headers

    async def test_429_body_structure(self, fake_redis, auth_headers):
        app = _build_app(fake_redis)
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            for _ in range(5):
                await c.post("/v1/conversations/message", headers=auth_headers,
                            json={"message": "hi", "channel": "chat"})

            resp = await c.post("/v1/conversations/message", headers=auth_headers,
                               json={"message": "hi", "channel": "chat"})
            body = resp.json()
            assert body["type"] == "rate_limit_exceeded"
            assert "detail" in body

    async def test_different_customers_independent(self, fake_redis, auth_headers, auth_headers_other):
        app = _build_app(fake_redis)
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            for _ in range(5):
                await c.post("/v1/conversations/message", headers=auth_headers,
                            json={"message": "hi", "channel": "chat"})

            # cust_test is at limit
            resp = await c.post("/v1/conversations/message", headers=auth_headers,
                               json={"message": "hi", "channel": "chat"})
            assert resp.status_code == 429

            # cust_other still has capacity
            resp = await c.post("/v1/conversations/message", headers=auth_headers_other,
                               json={"message": "hi", "channel": "chat"})
            assert resp.status_code == 200


class TestPerCustomerDailyLimit:
    async def test_daily_limit_returns_429(self, fake_redis):
        cfg = SafetyConfig(per_customer_per_minute=100, per_customer_per_day=3, global_rps=100)
        app = _build_app(fake_redis, config=cfg)
        headers = {"Authorization": f"Bearer {create_token('cust_test')}"}

        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            for _ in range(3):
                resp = await c.post("/v1/conversations/message", headers=headers,
                                   json={"message": "hi", "channel": "chat"})
                assert resp.status_code == 200

            resp = await c.post("/v1/conversations/message", headers=headers,
                               json={"message": "hi", "channel": "chat"})
            assert resp.status_code == 429
            assert "daily" in resp.json()["detail"].lower()


class TestGlobalLimit:
    async def test_global_limit_returns_503(self, fake_redis):
        cfg = SafetyConfig(per_customer_per_minute=100, per_customer_per_day=1000, global_rps=2)
        app = _build_app(fake_redis, config=cfg)

        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # First 2 requests should pass (global_rps=2)
            for i in range(2):
                resp = await c.post("/v1/conversations/message",
                                   json={"message": "hi", "channel": "chat"})
                assert resp.status_code == 200, f"Request {i+1} should pass under limit"

            # 3rd request in the same second must be blocked
            resp = await c.post("/v1/conversations/message",
                               json={"message": "hi", "channel": "chat"})
            assert resp.status_code == 503
            assert resp.json()["type"] == "service_overloaded"

    async def test_503_includes_retry_after(self, fake_redis):
        cfg = SafetyConfig(per_customer_per_minute=100, per_customer_per_day=1000, global_rps=1)
        app = _build_app(fake_redis, config=cfg)

        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/v1/conversations/message", json={"message": "hi", "channel": "chat"})
            assert resp.status_code == 200

            resp = await c.post("/v1/conversations/message", json={"message": "hi", "channel": "chat"})
            assert resp.status_code == 503, "Second request must be blocked (global_rps=1)"
            assert "retry-after" in resp.headers
            assert resp.headers["retry-after"] == "1"


class TestNonConversationRoutes:
    async def test_health_not_rate_limited(self, fake_redis):
        app = _build_app(fake_redis)
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            for _ in range(20):
                resp = await c.get("/healthz")
                assert resp.status_code == 200
