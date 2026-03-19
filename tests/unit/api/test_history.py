"""
Conversation history endpoint: GET /v1/conversations/{conversation_id}/messages

Auth required, tenant-isolated. Returns chronological message list.
Empty conversation → 200 with empty list. Unknown → 404.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry


def _app_with_ea(ea_instance, **extra):
    registry = EARegistry(factory=lambda cid: ea_instance)
    return create_app(
        ea_registry=registry,
        orchestrator=extra.get("orchestrator") or AsyncMock(),
        whatsapp_manager=extra.get("whatsapp_manager") or MagicMock(),
        redis_client=extra.get("redis_client") or AsyncMock(),
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
    def test_wrong_customer_gets_404(self):
        """Customer A's token cannot read customer B's conversations."""
        ea_a = AsyncMock()
        ea_a.get_conversation_history = MagicMock(return_value=None)

        # Build an app where customer lookup always returns ea_a
        # (simulating that customer_b's conversation doesn't exist in ea_a)
        app = _app_with_ea(ea_a)
        client = TestClient(app)
        tok_a = create_token("cust_a")

        resp = client.get(
            "/v1/conversations/conv_belongs_to_b/messages",
            headers={"Authorization": f"Bearer {tok_a}"},
        )
        # 404 — don't confirm existence for another tenant
        assert resp.status_code == 404


class TestHistoryResponses:
    def test_unknown_conversation_404(self):
        ea = AsyncMock()
        ea.get_conversation_history = MagicMock(return_value=None)
        app = _app_with_ea(ea)
        client = TestClient(app)
        tok = create_token("cust_hist")

        resp = client.get(
            "/v1/conversations/nonexistent/messages",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 404

    def test_empty_conversation_returns_200(self):
        ea = AsyncMock()
        ea.get_conversation_history = MagicMock(return_value=[])
        app = _app_with_ea(ea)
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

    def test_response_schema(self):
        messages = [
            {"role": "human", "content": "hello", "timestamp": "2026-03-19T10:00:00"},
            {"role": "ai", "content": "Hi there!", "timestamp": "2026-03-19T10:00:01"},
        ]
        ea = AsyncMock()
        ea.get_conversation_history = MagicMock(return_value=messages)
        ea.customer_id = "cust_hist"
        app = _app_with_ea(ea)
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
        assert body["messages"][0]["role"] == "human"
        assert body["messages"][1]["role"] == "ai"

    def test_messages_chronological_order(self):
        messages = [
            {"role": "human", "content": "first", "timestamp": "2026-03-19T10:00:00"},
            {"role": "ai", "content": "second", "timestamp": "2026-03-19T10:00:01"},
            {"role": "human", "content": "third", "timestamp": "2026-03-19T10:00:02"},
        ]
        ea = AsyncMock()
        ea.get_conversation_history = MagicMock(return_value=messages)
        app = _app_with_ea(ea)
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
    def test_send_then_fetch(self):
        """
        Send a message via POST, then GET history and see both the
        user message and the EA response.
        """
        history_store: dict[str, list] = {}

        ea = AsyncMock()

        async def fake_interaction(*, message, channel, conversation_id):
            history_store.setdefault(conversation_id, [])
            history_store[conversation_id].append(
                {"role": "human", "content": message, "timestamp": "2026-03-19T10:00:00"}
            )
            response = "EA reply"
            history_store[conversation_id].append(
                {"role": "ai", "content": response, "timestamp": "2026-03-19T10:00:01"}
            )
            return response

        ea.handle_customer_interaction = AsyncMock(side_effect=fake_interaction)
        ea.get_conversation_history = MagicMock(
            side_effect=lambda cid: history_store.get(cid)
        )

        app = _app_with_ea(ea)
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
        assert body["messages"][0]["role"] == "human"
        assert body["messages"][0]["content"] == "hello"
        assert body["messages"][1]["role"] == "ai"
        assert body["messages"][1]["content"] == "EA reply"
