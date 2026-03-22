"""Shared fixtures for end-to-end integration tests.

All tests use httpx.ASGITransport + AsyncClient so the test body and the
request handler share the same event loop — critical for fakeredis
visibility.  No live services required: Redis is fakeredis, Postgres
repos are AsyncMock, LLM calls are canned responses.

The safety pipeline is REAL (PromptGuard + OutputScanner + AuditLogger)
backed by fakeredis — we're testing that the wiring actually works.
"""
import os

# JWT_SECRET must be set before any import that touches src.api.auth.
os.environ.setdefault(
    "JWT_SECRET", "test-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
)

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import fakeredis
import fakeredis.aioredis
import httpx
import pytest

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry
from src.proactive.state import ProactiveStateStore
from src.safety.audit import AuditLogger
from src.safety.config import SafetyConfig
from src.safety.pipeline import SafetyPipeline


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_server():
    """Shared fakeredis server — all FakeRedis instances see the same keys."""
    return fakeredis.FakeServer()


@pytest.fixture
def fake_redis(fake_server):
    return fakeredis.aioredis.FakeRedis(server=fake_server)


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

@pytest.fixture
def safety_config():
    return SafetyConfig()


@pytest.fixture
def audit_logger(fake_redis):
    return AuditLogger(fake_redis)


@pytest.fixture
def safety_pipeline(safety_config, audit_logger):
    return SafetyPipeline(safety_config, audit_logger)


# ---------------------------------------------------------------------------
# Proactive state
# ---------------------------------------------------------------------------

@pytest.fixture
def proactive_store(fake_redis):
    return ProactiveStateStore(fake_redis)


# ---------------------------------------------------------------------------
# Mock EA
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_ea():
    """An AsyncMock EA whose handle_customer_interaction returns a canned reply.

    Tests can override the return_value or side_effect per-test.
    """
    ea = AsyncMock()
    ea.customer_id = "cust_a"
    ea.handle_customer_interaction = AsyncMock(
        return_value="Hello! How can I help you today?"
    )
    ea.last_specialist_domain = None
    return ea


# ---------------------------------------------------------------------------
# Mock repositories
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_conversation_repo():
    """AsyncMock ConversationRepository — writes succeed silently, reads return empty."""
    repo = AsyncMock()
    repo.create_conversation = AsyncMock(return_value=None)
    repo.append_message = AsyncMock(return_value=None)
    repo.get_messages = AsyncMock(return_value=None)
    repo.list_conversations_enriched = AsyncMock(return_value=[])
    repo.set_summary = AsyncMock(return_value=None)
    repo.set_quality_signals = AsyncMock(return_value=None)
    repo.get_conversations_needing_summary = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_analytics_service():
    """AsyncMock AnalyticsService."""
    svc = AsyncMock()
    svc.get_analytics = AsyncMock(return_value={
        "period": {"start": "2026-03-14T00:00:00+00:00", "end": "2026-03-21T00:00:00+00:00"},
        "overview": {
            "total_conversations": 0,
            "total_delegations": 0,
            "avg_messages_per_conversation": 0.0,
            "escalation_rate": 0.0,
            "unresolved_rate": 0.0,
        },
        "topics": {"breakdown": []},
        "specialist_performance": [],
        "trends": {"conversations_by_day": [], "delegations_by_day": []},
    })
    return svc


# ---------------------------------------------------------------------------
# App + client
# ---------------------------------------------------------------------------

@pytest.fixture
def e2e_app(
    fake_redis,
    mock_ea,
    mock_conversation_repo,
    mock_analytics_service,
    proactive_store,
    safety_pipeline,
):
    """Fully-wired FastAPI app for E2E tests."""
    # EARegistry takes a sync factory; the lambda returns mock_ea for any customer_id.
    registry = EARegistry(
        factory=lambda cid: mock_ea,
        max_size=10,
    )

    app = create_app(
        ea_registry=registry,
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=fake_redis,
        conversation_repo=mock_conversation_repo,
        proactive_state_store=proactive_store,
        safety_pipeline=safety_pipeline,
        analytics_service=mock_analytics_service,
    )
    return app


@pytest.fixture
async def client(e2e_app):
    """httpx AsyncClient sharing the test's event loop."""
    transport = httpx.ASGITransport(app=e2e_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# JWT tokens + auth headers
# ---------------------------------------------------------------------------

@pytest.fixture
def token_a():
    return create_token("cust_a")


@pytest.fixture
def token_b():
    return create_token("cust_b")


@pytest.fixture
def headers_a(token_a):
    return {"Authorization": f"Bearer {token_a}"}


@pytest.fixture
def headers_b(token_b):
    return {"Authorization": f"Bearer {token_b}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def today_iso():
    """Return today's date as YYYY-MM-DD string."""
    return date.today().isoformat()
