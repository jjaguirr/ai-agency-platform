"""
Shared fixtures for API unit tests.

All downstream services (EA, orchestrator, Redis, WhatsApp) are mocked.
The real imports still resolve — we monkeypatch at the dependency-injection
boundary, not at module load time.
"""
import os

import pytest
from unittest.mock import AsyncMock, MagicMock

# Ensure JWT_SECRET is set before any app module imports
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-prod")


@pytest.fixture
def jwt_secret():
    return os.environ["JWT_SECRET"]


@pytest.fixture
def mock_ea():
    """A fake EA that just echoes."""
    ea = AsyncMock()
    ea.customer_id = "cust_test"
    ea.handle_customer_interaction = AsyncMock(return_value="EA reply")
    return ea


@pytest.fixture
def mock_ea_factory(mock_ea):
    """Factory that returns the same mock EA regardless of customer_id."""
    # Track how many times it was called — for concurrency tests.
    factory = MagicMock(return_value=mock_ea)
    return factory


@pytest.fixture
def mock_orchestrator():
    """Stub InfrastructureOrchestrator — provision returns a minimal env."""
    orch = AsyncMock()

    async def _provision(customer_id, tier="professional", **_):
        env = MagicMock()
        env.customer_id = customer_id
        env.tier = tier
        env.status = MagicMock(value="healthy")
        env.to_dict = MagicMock(return_value={
            "customer_id": customer_id,
            "tier": tier,
            "status": "healthy",
            "services": {},
        })
        return env

    orch.provision_customer_environment = AsyncMock(side_effect=_provision)
    return orch


@pytest.fixture
def mock_whatsapp_manager():
    """Stub WhatsAppManager for webhook tests."""
    mgr = MagicMock()
    mgr.get_channel = AsyncMock(return_value=None)
    return mgr


@pytest.fixture
def healthy_redis():
    """Redis mock that responds to ping."""
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    return r


@pytest.fixture
def broken_redis():
    """Redis mock that raises on ping."""
    r = AsyncMock()
    r.ping = AsyncMock(side_effect=ConnectionError("redis unreachable"))
    return r
