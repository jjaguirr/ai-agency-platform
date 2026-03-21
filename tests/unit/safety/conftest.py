"""Shared fixtures for safety-layer tests."""
import pytest

import fakeredis.aioredis


@pytest.fixture
def fake_redis():
    """In-process Redis — same pattern as tests/unit/proactive/conftest.py."""
    return fakeredis.aioredis.FakeRedis()
