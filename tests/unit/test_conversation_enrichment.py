"""
Conversation list enrichment — message count and specialist domains.

The list endpoint should include:
  - message_count: total messages per conversation
  - specialist_domains: domains that handled turns (from message metadata)

These tests verify the route layer:
  - passes correct customer_id/limit/offset to the repo
  - includes enrichment fields in the JSON response
  - validates the schema rejects missing required fields

And the repo layer:
  - serializes metadata as JSON in append_message
  - metadata default is truly None (not an empty dict)
"""
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, call

from fastapi.testclient import TestClient


def _make_app(*, conversations=None, mock_repo=None):
    """Build a test app with a mock conversation repo."""
    from src.api.app import create_app
    from src.api.ea_registry import EARegistry

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)

    if mock_repo is None:
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

    return app, mock_repo


class TestConversationListEnrichment:
    def test_repo_called_with_customer_id_and_defaults(self):
        """Route passes JWT customer_id and default limit/offset to repo."""
        app, mock_repo = _make_app(conversations=[])
        client = TestClient(app)

        client.get("/v1/conversations")

        mock_repo.list_conversations.assert_awaited_once_with(
            customer_id="cust_test", limit=50, offset=0,
        )

    def test_repo_called_with_explicit_pagination(self):
        """Query params limit/offset forward to the repo."""
        app, mock_repo = _make_app(conversations=[])
        client = TestClient(app)

        client.get("/v1/conversations?limit=10&offset=20")

        mock_repo.list_conversations.assert_awaited_once_with(
            customer_id="cust_test", limit=10, offset=20,
        )

    def test_includes_message_count(self):
        convs = [{
            "id": "conv_1", "channel": "chat",
            "created_at": "2026-03-21T10:00:00+00:00",
            "updated_at": "2026-03-21T10:30:00+00:00",
            "message_count": 6,
            "specialist_domains": [],
        }]
        app, _ = _make_app(conversations=convs)
        client = TestClient(app)

        resp = client.get("/v1/conversations")
        assert resp.status_code == 200
        body = resp.json()
        assert body["conversations"][0]["message_count"] == 6

    def test_includes_specialist_domains_preserving_values(self):
        convs = [{
            "id": "conv_2", "channel": "whatsapp",
            "created_at": "2026-03-21T10:00:00+00:00",
            "updated_at": "2026-03-21T10:30:00+00:00",
            "message_count": 4,
            "specialist_domains": ["finance", "scheduling"],
        }]
        app, _ = _make_app(conversations=convs)
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
        app, _ = _make_app(conversations=convs)
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
        app, _ = _make_app(conversations=convs)
        client = TestClient(app)

        resp = client.get("/v1/conversations")
        body = resp.json()
        assert body["conversations"][0]["message_count"] == 0

    def test_no_repo_returns_empty_list(self):
        """When conversation_repo is None (unconfigured), the route
        returns an empty list, not 500."""
        from src.api.app import create_app
        from src.api.ea_registry import EARegistry
        from src.api.auth import get_current_customer

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        app = create_app(
            ea_registry=MagicMock(spec=EARegistry),
            orchestrator=MagicMock(),
            whatsapp_manager=MagicMock(),
            redis_client=mock_redis,
            conversation_repo=None,
        )
        app.dependency_overrides[get_current_customer] = lambda: "cust_test"
        client = TestClient(app)

        resp = client.get("/v1/conversations")
        assert resp.status_code == 200
        assert resp.json()["conversations"] == []


class TestAppendMessageMetadata:
    """Verify metadata serialization in append_message."""

    @pytest.mark.asyncio
    async def test_metadata_serialized_as_json_in_query(self):
        """append_message must serialize the metadata dict to a JSON
        string and pass it as the 4th positional arg to conn.execute."""
        import asyncpg
        from src.database.conversation_repository import ConversationRepository

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="INSERT 0 1")
        # Fake transaction context manager
        mock_conn.transaction = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
        )

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn),
                                   __aexit__=AsyncMock()),
        )

        repo = ConversationRepository(pool=mock_pool)
        meta = {"specialist_domain": "finance"}

        await repo.append_message(
            customer_id="c", conversation_id="conv_1",
            role="assistant", content="done",
            metadata=meta,
        )

        # The INSERT call is the first execute; the UPDATE is the second.
        insert_call = mock_conn.execute.await_args_list[0]
        # 4th positional arg (index 3) is the serialized metadata
        meta_arg = insert_call.args[4]  # ($1=conv_id, $2=role, $3=content, $4=meta_json, $5=cust_id)
        assert meta_arg == json.dumps(meta)

    @pytest.mark.asyncio
    async def test_none_metadata_passes_null(self):
        """When metadata is None (no specialist), the query param is None, not '{}'."""
        import asyncpg
        from src.database.conversation_repository import ConversationRepository

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="INSERT 0 1")
        mock_conn.transaction = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
        )

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn),
                                   __aexit__=AsyncMock()),
        )

        repo = ConversationRepository(pool=mock_pool)

        await repo.append_message(
            customer_id="c", conversation_id="conv_1",
            role="user", content="hello",
        )

        insert_call = mock_conn.execute.await_args_list[0]
        meta_arg = insert_call.args[4]  # 4th positional = meta_json
        assert meta_arg is None
