"""Tests for app lifespan heartbeat integration."""
import os
import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault(
    "JWT_SECRET", "test-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
)

from fastapi import FastAPI
from asgi_lifespan import LifespanManager

from src.api.app import create_app
from src.api.ea_registry import EARegistry
from src.proactive.heartbeat import HeartbeatDaemon
from src.proactive.state import ProactiveStateStore
from src.proactive.gate import NoiseGate

import fakeredis.aioredis


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def mock_ea():
    ea = AsyncMock()
    ea.customer_id = "cust_test"
    ea.handle_customer_interaction = AsyncMock(return_value="reply")
    return ea


class TestAppLifespanWithHeartbeat:
    async def test_heartbeat_starts_and_stops(self, mock_ea, fake_redis):
        store = ProactiveStateStore(fake_redis)
        gate = NoiseGate(store)
        dispatcher = AsyncMock()
        dispatcher.dispatch = AsyncMock()
        factory = MagicMock(return_value=mock_ea)
        registry = EARegistry(factory=factory, max_size=10)

        heartbeat = HeartbeatDaemon(
            registry, store, gate, dispatcher, tick_interval=60.0,
        )

        @asynccontextmanager
        async def lifespan(_app: FastAPI):
            await heartbeat.start()
            _app.state.heartbeat = heartbeat
            yield
            await heartbeat.stop()

        app = create_app(
            ea_registry=registry,
            orchestrator=AsyncMock(),
            whatsapp_manager=MagicMock(),
            redis_client=fake_redis,
            proactive_state_store=store,
            lifespan=lifespan,
        )

        async with LifespanManager(app):
            assert heartbeat.is_running
            assert app.state.heartbeat is heartbeat

        assert not heartbeat.is_running

    async def test_app_works_without_heartbeat(self, mock_ea, fake_redis):
        """App runs fine when no heartbeat/proactive_state_store is configured."""
        factory = MagicMock(return_value=mock_ea)
        app = create_app(
            ea_registry=EARegistry(factory=factory, max_size=10),
            orchestrator=AsyncMock(),
            whatsapp_manager=MagicMock(),
            redis_client=fake_redis,
        )
        # No lifespan — just verify it doesn't crash
        import httpx
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/healthz")
            assert resp.status_code == 200
