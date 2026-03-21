"""
Conversation list enrichment — message count and specialist domains.

The list endpoint should include:
  - message_count: total messages per conversation
  - specialist_domains: domains that handled turns (from message metadata)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient


def _make_app(*, conversations=None):
    """Build a test app with a mock conversation repo."""
    from src.api.app import create_app
    from src.api.ea_registry import EARegistry

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)

    mock_repo = AsyncMock()
    mock_repo.list_conversations = AsyncMock(return_value=conversations or [])

    app = create_app(
        ea_registry=MagicMock(spec=EARegistry),
        orchestrator=MagicMock(),
        whatsapp_manager=MagicMock(),
        redis_client=mock_redis,
        conversation_repo=mock_repo,
    )

    from src.api.auth import get_current_customer
    app.dependency_overrides[get_current_customer] = lambda: "cust_test"

    return app


class TestConversationListEnrichment:
    def test_includes_message_count(self):
        convs = [{
            "id": "conv_1", "channel": "chat",
            "created_at": "2026-03-21T10:00:00+00:00",
            "updated_at": "2026-03-21T10:30:00+00:00",
            "message_count": 6,
            "specialist_domains": [],
        }]
        app = _make_app(conversations=convs)
        client = TestClient(app)

        resp = client.get("/v1/conversations")
        assert resp.status_code == 200
        body = resp.json()
        assert body["conversations"][0]["message_count"] == 6

    def test_includes_specialist_domains(self):
        convs = [{
            "id": "conv_2", "channel": "whatsapp",
            "created_at": "2026-03-21T10:00:00+00:00",
            "updated_at": "2026-03-21T10:30:00+00:00",
            "message_count": 4,
            "specialist_domains": ["finance", "scheduling"],
        }]
        app = _make_app(conversations=convs)
        client = TestClient(app)

        resp = client.get("/v1/conversations")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body["conversations"][0]["specialist_domains"]) == {"finance", "scheduling"}

    def test_empty_specialist_domains_when_no_delegation(self):
        convs = [{
            "id": "conv_3", "channel": "chat",
            "created_at": "2026-03-21T10:00:00+00:00",
            "updated_at": "2026-03-21T10:30:00+00:00",
            "message_count": 2,
            "specialist_domains": [],
        }]
        app = _make_app(conversations=convs)
        client = TestClient(app)

        resp = client.get("/v1/conversations")
        body = resp.json()
        assert body["conversations"][0]["specialist_domains"] == []

    def test_zero_message_count(self):
        convs = [{
            "id": "conv_4", "channel": "chat",
            "created_at": "2026-03-21T10:00:00+00:00",
            "updated_at": "2026-03-21T10:30:00+00:00",
            "message_count": 0,
            "specialist_domains": [],
        }]
        app = _make_app(conversations=convs)
        client = TestClient(app)

        resp = client.get("/v1/conversations")
        body = resp.json()
        assert body["conversations"][0]["message_count"] == 0


class TestAppendMessageMetadata:
    """Test that append_message accepts metadata for specialist tagging."""

    @pytest.mark.asyncio
    async def test_append_message_signature_accepts_metadata(self):
        """ConversationRepository.append_message should accept an optional
        metadata parameter without error."""
        from src.database.conversation_repository import ConversationRepository

        # We just verify the method signature accepts metadata.
        # Actual DB integration is tested in the integration suite.
        import inspect
        sig = inspect.signature(ConversationRepository.append_message)
        assert "metadata" in sig.parameters
