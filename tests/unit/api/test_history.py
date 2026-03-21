"""
Conversation history endpoint: GET /v1/conversations/{conversation_id}/messages

Now backed by ConversationRepository (Postgres) instead of the EA's
in-memory dict. The EA is no longer consulted on this path — history
survives EA LRU eviction.

Repo is mocked here. Real Postgres coverage lives in
tests/integration/test_conversation_repository.py.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry


def _app(repo=None, *, ea=None):
    """Build app with a mock conversation repo (and optional EA)."""
    ea_instance = ea or AsyncMock()
    return create_app(
        ea_registry=EARegistry(factory=lambda cid: ea_instance),
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=AsyncMock(),
        conversation_repo=repo or AsyncMock(),
    )


class TestHistoryAuth:
    def test_401_without_token(self):
        client = TestClient(_app())
        resp = client.get("/v1/conversations/conv1/messages")
        assert resp.status_code == 401

    def test_401_with_expired_token(self):
        client = TestClient(_app())
        tok = create_token("cust_hist", expires_in=-1)
        resp = client.get(
            "/v1/conversations/conv1/messages",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 401


class TestTenantIsolation:
    def test_repo_called_with_token_customer_id(self):
        """The customer_id the repo sees must come from the JWT."""
        repo = AsyncMock()
        repo.get_messages = AsyncMock(return_value=[])
        client = TestClient(_app(repo))
        tok = create_token("cust_from_token")

        client.get(
            "/v1/conversations/conv1/messages",
            headers={"Authorization": f"Bearer {tok}"},
        )

        repo.get_messages.assert_awaited_once()
        kwargs = repo.get_messages.await_args.kwargs
        assert kwargs["customer_id"] == "cust_from_token"
        assert kwargs["conversation_id"] == "conv1"

    def test_repo_none_becomes_404(self):
        """
        Repo returns None for both "doesn't exist" and "wrong tenant".
        API maps both to 404 — never confirm existence to the wrong
        caller.
        """
        repo = AsyncMock()
        repo.get_messages = AsyncMock(return_value=None)
        client = TestClient(_app(repo))
        tok = create_token("cust_a")

        resp = client.get(
            "/v1/conversations/belongs_to_b/messages",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 404

    def test_ea_not_consulted_on_history_path(self):
        """
        Regression guard: the EA's get_conversation_history must NOT be
        called. History comes from the repo now; calling the EA would
        re-introduce the LRU-eviction data-loss bug this feature fixes.
        """
        ea = MagicMock()
        ea.get_conversation_history = MagicMock(return_value=[{"fake": "data"}])
        repo = AsyncMock()
        repo.get_messages = AsyncMock(return_value=[])

        client = TestClient(_app(repo, ea=ea))
        tok = create_token("cust_hist")
        client.get(
            "/v1/conversations/conv1/messages",
            headers={"Authorization": f"Bearer {tok}"},
        )

        ea.get_conversation_history.assert_not_called()


class TestHistoryResponses:
    def test_unknown_conversation_404(self):
        repo = AsyncMock()
        repo.get_messages = AsyncMock(return_value=None)
        client = TestClient(_app(repo))
        tok = create_token("cust_hist")

        resp = client.get(
            "/v1/conversations/nonexistent/messages",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 404

    def test_empty_conversation_returns_200(self):
        repo = AsyncMock()
        repo.get_messages = AsyncMock(return_value=[])
        client = TestClient(_app(repo))
        tok = create_token("cust_hist")

        resp = client.get(
            "/v1/conversations/empty_conv/messages",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["messages"] == []
        assert body["conversation_id"] == "empty_conv"

    def test_response_schema(self):
        repo = AsyncMock()
        repo.get_messages = AsyncMock(return_value=[
            {"role": "user", "content": "hello",
             "timestamp": "2026-03-19T10:00:00+00:00"},
            {"role": "assistant", "content": "Hi there!",
             "timestamp": "2026-03-19T10:00:01+00:00"},
        ])
        client = TestClient(_app(repo))
        tok = create_token("cust_hist")

        resp = client.get(
            "/v1/conversations/conv1/messages",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["conversation_id"] == "conv1"
        assert body["customer_id"] == "cust_hist"
        assert len(body["messages"]) == 2
        assert body["messages"][0]["role"] == "user"
        assert body["messages"][1]["role"] == "assistant"

    # No chronological-order test here: feeding a sorted list to a mock
    # and asserting it comes back sorted proves nothing. The real sort
    # lives in the repository's SQL; it's covered by
    # TestAppendMessage::test_order_by_is_load_bearing against Postgres.


class TestListConversations:
    def test_list_returns_customers_conversations(self):
        repo = AsyncMock()
        repo.list_conversations = AsyncMock(return_value=[
            {"id": "conv_a", "channel": "chat",
             "created_at": "2026-03-19T09:00:00+00:00",
             "updated_at": "2026-03-19T10:00:00+00:00"},
            {"id": "conv_b", "channel": "email",
             "created_at": "2026-03-19T08:00:00+00:00",
             "updated_at": "2026-03-19T09:30:00+00:00"},
        ])
        client = TestClient(_app(repo))
        tok = create_token("cust_list")

        resp = client.get(
            "/v1/conversations",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["conversations"]) == 2
        assert body["conversations"][0]["id"] == "conv_a"

        repo.list_conversations.assert_awaited_once()
        assert repo.list_conversations.await_args.kwargs["customer_id"] == "cust_list"

    def test_list_requires_auth(self):
        client = TestClient(_app())
        resp = client.get("/v1/conversations")
        assert resp.status_code == 401

    def test_list_pagination_params(self):
        repo = AsyncMock()
        repo.list_conversations = AsyncMock(return_value=[])
        client = TestClient(_app(repo))
        tok = create_token("cust_list")

        client.get(
            "/v1/conversations?limit=10&offset=20",
            headers={"Authorization": f"Bearer {tok}"},
        )

        kwargs = repo.list_conversations.await_args.kwargs
        assert kwargs["limit"] == 10
        assert kwargs["offset"] == 20

    def test_list_includes_intelligence_fields(self):
        repo = AsyncMock()
        repo.list_conversations = AsyncMock(return_value=[
            {"id": "conv_a", "channel": "chat",
             "created_at": "2026-03-19T09:00:00+00:00",
             "updated_at": "2026-03-19T10:00:00+00:00",
             "summary": "Discussed invoices.",
             "tags": ["finance"],
             "quality_signals": {"escalation": False}},
        ])
        client = TestClient(_app(repo))
        tok = create_token("cust_list")

        resp = client.get(
            "/v1/conversations",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 200
        conv = resp.json()["conversations"][0]
        assert conv["summary"] == "Discussed invoices."
        assert conv["tags"] == ["finance"]
        assert conv["quality_signals"] == {"escalation": False}

    def test_list_intelligence_fields_default_to_empty(self):
        """Conversations without intelligence data still serialize cleanly."""
        repo = AsyncMock()
        repo.list_conversations = AsyncMock(return_value=[
            {"id": "conv_a", "channel": "chat",
             "created_at": "2026-03-19T09:00:00+00:00",
             "updated_at": "2026-03-19T10:00:00+00:00",
             "summary": None,
             "tags": [],
             "quality_signals": {}},
        ])
        client = TestClient(_app(repo))
        tok = create_token("cust_list")

        resp = client.get(
            "/v1/conversations",
            headers={"Authorization": f"Bearer {tok}"},
        )
        conv = resp.json()["conversations"][0]
        assert conv["summary"] is None
        assert conv["tags"] == []

    def test_tag_filter_passed_to_repo(self):
        repo = AsyncMock()
        repo.list_conversations = AsyncMock(return_value=[])
        client = TestClient(_app(repo))
        tok = create_token("cust_list")

        client.get(
            "/v1/conversations?tags=finance&tags=scheduling",
            headers={"Authorization": f"Bearer {tok}"},
        )

        kwargs = repo.list_conversations.await_args.kwargs
        assert kwargs["tags"] == ["finance", "scheduling"]
