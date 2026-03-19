"""Shared fixtures for proactive intelligence tests."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import fakeredis.aioredis


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


def fixed_clock(dt: datetime):
    """Return a callable that always returns the given datetime."""
    return lambda: dt


# Standard reference time for tests: Thursday 2026-03-19 10:00 UTC
REFERENCE_TIME = datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc)
