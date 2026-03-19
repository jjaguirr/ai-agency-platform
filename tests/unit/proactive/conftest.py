"""
Shared fixtures for proactive-system unit tests.

All Redis is fakeredis (async). All time is injected via a `clock` callable
so tests can pin "now" without freezegun. Matches the pattern used by the
scheduling specialist tests.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio


@pytest.fixture
def tz_utc():
    return ZoneInfo("UTC")


@pytest.fixture
def tz_ny():
    return ZoneInfo("America/New_York")


@pytest.fixture
def fixed_now(tz_utc):
    """Wednesday 2026-03-18 14:30 UTC."""
    return datetime(2026, 3, 18, 14, 30, tzinfo=tz_utc)


@pytest.fixture
def clock(fixed_now):
    """Mutable clock: call .set(dt) to move time, call() to read."""
    class _Clock:
        def __init__(self, t):
            self._t = t
        def __call__(self):
            return self._t
        def set(self, t):
            self._t = t
        def advance(self, delta):
            self._t = self._t + delta
    return _Clock(fixed_now)


@pytest_asyncio.fixture
async def fake_redis():
    """Async fakeredis — clean slate per test."""
    import fakeredis.aioredis
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


@pytest_asyncio.fixture
async def state_store(fake_redis, clock):
    from src.agents.proactive.state import ProactiveStateStore
    return ProactiveStateStore(redis=fake_redis, clock=clock)
