"""
Conversation history endpoint: GET /v1/conversations/{conversation_id}/messages
                               GET /v1/conversations  (list)

Auth required, tenant-isolated. Returns chronological message list.
Empty conversation -> 200 with empty list. Unknown -> 404.

History is read from the ConversationRepository (Postgres-backed).
Falls back to EA in-memory if repo unavailable.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry


def _app_with_ea(ea_instance, *, conversation_repo=None, **extra):
    registry = EARegistry(factory=lambda cid: ea_instance)
    return create_app(
        ea_registry=registry,
        orchestrator=extra.get("orchestrator") or AsyncMock(),
        whatsapp_manager=extra.get("whatsapp_manager") or MagicMock(),
        redis_client=extra.get("redis_client") or AsyncMock(),
        conversation_repo=conversation_repo,
    )


class TestHistoryAuth:
    def test_401_without_token(self):
        ea = AsyncMock()
        ea.get_conversation_history = MagicMock(return_value=[])
        app = _app_with_ea(ea)
        client = TestClient(app)

        resp = client.get("/v1/conversations/conv1/messages")
        assert resp.status_code == 401

    def test_401_with_expired_token(self):
        ea = AsyncMock()
        ea.get_conversation_history = MagicMock(return_value=[])
        app = _app_with_ea(ea)
        client = TestClient(app)
        tok = create_token("cust_hist", expires_in=-1)

        resp = client.get(
            "/v1/conversations/conv1/messages",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 401


class TestTenantIsolation:
    def test_wrong_customer_gets_404(self, mock_conversation_repo):
        """Customer A's token cannot read customer B's conversations."""
        ea_a = AsyncMock()
        ea_a.get_conversation_history = MagicMock(return_value=None)
        mock_conversation_repo.get_messages = AsyncMock(return_value=None)

        app = _app_with_ea(ea_a, conversation_repo=mock_conversation_repo)
        client = TestClient(app)
        tok_a = create_token("cust_a")

        resp = client.get(
            "/v1/conversations/conv_belongs_to_b/messages",
            headers={"Authorization": f"Bearer {tok_a}"},
        )
        assert resp.status_code == 404

    def test_unprovisioned_customer_gets_404(self, mock_conversation_repo):
        """Valid JWT for a customer_id that was never provisioned."""
        ea = AsyncMock()
        ea.get_conversation_history = MagicMock(return_value=None)
        mock_conversation_repo.get_messages = AsyncMock(return_value=None)

        app = _app_with_ea(ea, conversation_repo=mock_conversation_repo)
        client = TestClient(app)
        tok = create_token("cust_phantom")

        resp = client.get(
            "/v1/conversations/any_conv/messages",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


class TestHistoryFromRepo:
    """Tests that the endpoint reads from the conversation repository."""

    def test_reads_from_repo_not_ea(self, mock_conversation_repo):
        """When repo is available, endpoint reads from it, not EA."""
        ea = AsyncMock()
        ea.get_conversation_history = MagicMock(return_value=None)

        mock_conversation_repo.get_messages = AsyncMock(return_value=[
            {"role": "user", "content": "hello", "timestamp": "2026-03-19T10:00:00+00:00"},
            {"role": "assistant", "content": "Hi!", "timestamp": "2026-03-19T10:00:01+00:00"},
        ])

        app = _app_with_ea(ea, conversation_repo=mock_conversation_repo)
        client = TestClient(app)
        tok = create_token("cust_repo")

        resp = client.get(
            "/v1/conversations/conv1/messages",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["messages"]) == 2
        assert body["messages"][0]["content"] == "hello"

        # Verify repo was called with correct customer_id
        mock_conversation_repo.get_messages.assert_called_once_with(
            "conv1", "cust_repo"
        )

    def test_falls_back_to_ea_when_no_repo(self):
        """Without a repo, endpoint falls back to EA in-memory history."""
        ea = AsyncMock()
        ea.get_conversation_history = MagicMock(return_value=[
            {"role": "human", "content": "from EA", "timestamp": "2026-03-19T10:00:00"},
        ])

        app = _app_with_ea(ea, conversation_repo=None)
        client = TestClient(app)
        tok = create_token("cust_fallback")

        resp = client.get(
            "/v1/conversations/conv1/messages",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 200
        assert resp.json()["messages"][0]["content"] == "from EA"


class TestHistoryResponses:
    def test_unknown_conversation_404(self, mock_conversation_repo):
        ea = AsyncMock()
        ea.get_conversation_history = MagicMock(return_value=None)
        mock_conversation_repo.get_messages = AsyncMock(return_value=None)

        app = _app_with_ea(ea, conversation_repo=mock_conversation_repo)
        client = TestClient(app)
        tok = create_token("cust_hist")

        resp = client.get(
            "/v1/conversations/nonexistent/messages",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 404

    def test_empty_conversation_returns_200(self, mock_conversation_repo):
        ea = AsyncMock()
        mock_conversation_repo.get_messages = AsyncMock(return_value=[])

        app = _app_with_ea(ea, conversation_repo=mock_conversation_repo)
        client = TestClient(app)
        tok = create_token("cust_hist")

        resp = client.get(
            "/v1/conversations/empty_conv/messages",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["messages"] == []
        assert body["conversation_id"] == "empty_conv"

    def test_response_schema(self, mock_conversation_repo):
        messages = [
            {"role": "user", "content": "hello", "timestamp": "2026-03-19T10:00:00+00:00"},
            {"role": "assistant", "content": "Hi there!", "timestamp": "2026-03-19T10:00:01+00:00"},
        ]
        ea = AsyncMock()
        mock_conversation_repo.get_messages = AsyncMock(return_value=messages)

        app = _app_with_ea(ea, conversation_repo=mock_conversation_repo)
        client = TestClient(app)
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

    def test_messages_chronological_order(self, mock_conversation_repo):
        messages = [
            {"role": "user", "content": "first", "timestamp": "2026-03-19T10:00:00+00:00"},
            {"role": "assistant", "content": "second", "timestamp": "2026-03-19T10:00:01+00:00"},
            {"role": "user", "content": "third", "timestamp": "2026-03-19T10:00:02+00:00"},
        ]
        ea = AsyncMock()
        mock_conversation_repo.get_messages = AsyncMock(return_value=messages)

        app = _app_with_ea(ea, conversation_repo=mock_conversation_repo)
        client = TestClient(app)
        tok = create_token("cust_hist")

        resp = client.get(
            "/v1/conversations/conv1/messages",
            headers={"Authorization": f"Bearer {tok}"},
        )
        body = resp.json()
        timestamps = [m["timestamp"] for m in body["messages"]]
        assert timestamps == sorted(timestamps)


class TestHistoryRoundtrip:
    def test_send_then_fetch(self, mock_conversation_repo):
        """
        Send a message via POST, then GET history and see both the
        user message and the EA response.
        """
        stored: list[dict] = []

        async def fake_append(conv_id, cust_id, role, content):
            stored.append({"role": role, "content": content, "timestamp": "2026-03-19T10:00:00+00:00"})
            return "msg_id"

        mock_conversation_repo.append_message = AsyncMock(side_effect=fake_append)
        mock_conversation_repo.get_messages = AsyncMock(side_effect=lambda cid, cust: stored if stored else None)

        ea = AsyncMock()
        ea.handle_customer_interaction = AsyncMock(return_value="EA reply")

        app = _app_with_ea(ea, conversation_repo=mock_conversation_repo)
        client = TestClient(app)
        tok = create_token("cust_rt")
        headers = {"Authorization": f"Bearer {tok}"}

        # Send a message
        post_resp = client.post(
            "/v1/conversations/message",
            json={"message": "hello", "channel": "chat", "conversation_id": "rt_conv"},
            headers=headers,
        )
        assert post_resp.status_code == 200

        # Fetch history
        get_resp = client.get(
            "/v1/conversations/rt_conv/messages",
            headers=headers,
        )
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert len(body["messages"]) == 2
        assert body["messages"][0]["role"] == "user"
        assert body["messages"][0]["content"] == "hello"
        assert body["messages"][1]["role"] == "assistant"
        assert body["messages"][1]["content"] == "EA reply"


class TestListConversations:
    def test_list_requires_auth(self):
        ea = AsyncMock()
        app = _app_with_ea(ea)
        client = TestClient(app)

        resp = client.get("/v1/conversations")
        assert resp.status_code == 401

    def test_list_returns_conversations(self, mock_conversation_repo):
        mock_conversation_repo.list_conversations = AsyncMock(return_value=[
            {
                "conversation_id": "conv1",
                "channel": "chat",
                "created_at": "2026-03-19T10:00:00+00:00",
                "updated_at": "2026-03-19T10:00:01+00:00",
            },
        ])
        ea = AsyncMock()
        app = _app_with_ea(ea, conversation_repo=mock_conversation_repo)
        client = TestClient(app)
        tok = create_token("cust_list")

        resp = client.get(
            "/v1/conversations",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["customer_id"] == "cust_list"
        assert len(body["conversations"]) == 1
        assert body["conversations"][0]["conversation_id"] == "conv1"

    def test_list_pagination_params(self, mock_conversation_repo):
        mock_conversation_repo.list_conversations = AsyncMock(return_value=[])
        ea = AsyncMock()
        app = _app_with_ea(ea, conversation_repo=mock_conversation_repo)
        client = TestClient(app)
        tok = create_token("cust_page")

        resp = client.get(
            "/v1/conversations?limit=5&offset=10",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["limit"] == 5
        assert body["offset"] == 10

        mock_conversation_repo.list_conversations.assert_called_once_with(
            "cust_page", limit=5, offset=10
        )

    def test_list_returns_empty_without_repo(self):
        ea = AsyncMock()
        app = _app_with_ea(ea, conversation_repo=None)
        client = TestClient(app)
        tok = create_token("cust_no_repo")

        resp = client.get(
            "/v1/conversations",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["conversations"] == []
