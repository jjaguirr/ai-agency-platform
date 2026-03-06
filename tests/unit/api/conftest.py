"""
Shared fixtures for API tests.

The root conftest imports ExecutiveAssistant which pulls in langchain, openai,
mem0 — heavy and not needed for API-layer tests. These fixtures inject mocks
at the `app.state` level so API tests never construct a real EA.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


# --- EA mocking ------------------------------------------------------------

def make_mock_ea(customer_id: str, response: str = "mock EA response") -> MagicMock:
    """Build a mock ExecutiveAssistant with async handle_customer_interaction."""
    ea = MagicMock()
    ea.customer_id = customer_id
    ea.handle_customer_interaction = AsyncMock(return_value=response)
    return ea


@pytest.fixture
def mock_ea_factory():
    """
    A factory that returns mock EAs and records what it created.

    Returned object has `.created` list of (customer_id, instance) tuples so
    tests can assert on instantiation count and identity.
    """
    created: list[tuple[str, MagicMock]] = []

    def factory(customer_id: str):
        ea = make_mock_ea(customer_id)
        created.append((customer_id, ea))
        return ea

    factory.created = created
    return factory


# --- Redis mocking ---------------------------------------------------------

@pytest.fixture
def mock_redis_up():
    """Async redis client whose ping succeeds."""
    r = MagicMock()
    r.ping = AsyncMock(return_value=True)
    return r


@pytest.fixture
def mock_redis_down():
    """Async redis client whose ping raises (simulates outage)."""
    r = MagicMock()
    r.ping = AsyncMock(side_effect=ConnectionError("redis unreachable"))
    return r


# --- Orchestrator mocking --------------------------------------------------

@pytest.fixture
def mock_orchestrator():
    """
    Infrastructure orchestrator stub.

    `provision_customer_environment` echoes back a CustomerEnvironment-shaped
    object carrying the customer_id and tier it was called with. Tests that
    need different behaviour (failure, status=failed, ID normalization) can
    override `.return_value` or `.side_effect`.
    """
    orch = MagicMock()

    async def _provision(*, customer_id: str, tier: str = "professional", **_):
        env = MagicMock()
        env.customer_id = customer_id
        env.tier = tier
        env.status = MagicMock(value="healthy")
        env.created_at = MagicMock(isoformat=MagicMock(return_value="2026-03-06T00:00:00"))
        return env

    orch.provision_customer_environment = AsyncMock(side_effect=_provision)
    return orch


# --- App + client ----------------------------------------------------------

@pytest.fixture
def jwt_secret() -> str:
    return "test-secret-do-not-use-in-production"


@pytest.fixture
def api_app(mock_ea_factory, mock_redis_up, mock_orchestrator, jwt_secret):
    """
    Fully-wired FastAPI app with all dependencies mocked.

    EA pool uses `mock_ea_factory`, redis is `mock_redis_up`, orchestrator
    is stubbed. Tests that need different behaviour (redis down, orchestrator
    failure) build their own app via `create_app` directly.
    """
    from src.api.app import create_app
    from src.api.dependencies import EAPool
    from src.communication.whatsapp_manager import WhatsAppManager

    app = create_app(
        ea_pool=EAPool(ea_factory=mock_ea_factory),
        redis_client=mock_redis_up,
        orchestrator=mock_orchestrator,
        whatsapp_manager=WhatsAppManager(),
        jwt_secret=jwt_secret,
    )
    return app


@pytest.fixture
def client(api_app) -> TestClient:
    return TestClient(api_app)


@pytest.fixture
def auth_header(jwt_secret):
    """Generate a valid Bearer header for a given customer_id."""
    from src.api.auth import create_token

    def _make(customer_id: str = "cust_test") -> dict[str, str]:
        token = create_token(customer_id, secret=jwt_secret)
        return {"Authorization": f"Bearer {token}"}

    return _make
