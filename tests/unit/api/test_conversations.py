"""
Conversation endpoint: POST /v1/conversations/message

Accepts {message, channel, conversation_id?} → routes through per-customer
EA → returns {response, conversation_id}.

The EA already handles specialist failures by falling back to generalist
mode, so a broken specialist must still yield 200. What *should* produce
503 is an EA infrastructure failure (Redis gone mid-request, mem0 down)
where we can't hand back *any* response.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry


def _app_with_ea(ea_instance, **extra):
    """Build app with a registry that always returns the given EA."""
    registry = EARegistry(factory=lambda cid: ea_instance)
    return create_app(
        ea_registry=registry,
        orchestrator=extra.get("orchestrator") or AsyncMock(),
        whatsapp_manager=extra.get("whatsapp_manager") or MagicMock(),
        redis_client=extra.get("redis_client") or AsyncMock(),
    )


@pytest.fixture
def auth_headers():
    tok = create_token("cust_conv")
    return {"Authorization": f"Bearer {tok}"}


class TestConversationHappyPath:
    def test_valid_message_returns_ea_response(self, mock_ea, auth_headers):
        mock_ea.handle_customer_interaction = AsyncMock(
            return_value="Hi, I'm Sarah.")
        app = _app_with_ea(mock_ea)
        client = TestClient(app)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hello", "channel": "chat"},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["response"] == "Hi, I'm Sarah."
        assert "conversation_id" in body

    def test_ea_receives_correct_channel_enum(self, mock_ea, auth_headers):
        from src.agents.executive_assistant import ConversationChannel
        app = _app_with_ea(mock_ea)
        client = TestClient(app)

        client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "whatsapp"},
            headers=auth_headers,
        )

        call_kwargs = mock_ea.handle_customer_interaction.call_args.kwargs
        assert call_kwargs["channel"] == ConversationChannel.WHATSAPP

    def test_conversation_id_roundtrip(self, mock_ea, auth_headers):
        app = _app_with_ea(mock_ea)
        client = TestClient(app)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat",
                  "conversation_id": "conv_fixed"},
            headers=auth_headers,
        )

        assert resp.json()["conversation_id"] == "conv_fixed"
        assert mock_ea.handle_customer_interaction.call_args.kwargs[
                   "conversation_id"] == "conv_fixed"

    def test_conversation_id_generated_when_omitted(self, mock_ea, auth_headers):
        app = _app_with_ea(mock_ea)
        client = TestClient(app)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat"},
            headers=auth_headers,
        )

        assert resp.json()["conversation_id"]  # non-empty


class TestConversationAuth:
    def test_no_token_returns_401(self, mock_ea):
        app = _app_with_ea(mock_ea)
        client = TestClient(app)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat"},
        )
        assert resp.status_code == 401

    def test_expired_token_returns_401(self, mock_ea):
        app = _app_with_ea(mock_ea)
        client = TestClient(app)
        tok = create_token("cust_conv", expires_in=-1)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 401


class TestConversationValidation:
    def test_invalid_channel_returns_422(self, mock_ea, auth_headers):
        app = _app_with_ea(mock_ea)
        client = TestClient(app)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "carrier_pigeon"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_missing_message_returns_422(self, mock_ea, auth_headers):
        app = _app_with_ea(mock_ea)
        client = TestClient(app)

        resp = client.post(
            "/v1/conversations/message",
            json={"channel": "chat"},
            headers=auth_headers,
        )
        assert resp.status_code == 422


class TestConversationDegradedMode:
    def test_ea_returns_degraded_response_still_200(self, auth_headers):
        """
        EA handles its own specialist failures and returns a fallback
        string. The API should not treat that as an error.
        """
        degraded_ea = AsyncMock()
        degraded_ea.handle_customer_interaction = AsyncMock(
            return_value="I'm having some trouble right now, but here's what I can tell you..."
        )
        app = _app_with_ea(degraded_ea)
        client = TestClient(app)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "complex task", "channel": "chat"},
            headers=auth_headers,
        )

        assert resp.status_code == 200

    def test_ea_infra_failure_returns_structured_503(self, auth_headers):
        """
        If the EA itself blows up (not specialist failure — actual
        exception from handle_customer_interaction), caller gets 503
        with a structured body, not a traceback.
        """
        broken_ea = AsyncMock()
        broken_ea.handle_customer_interaction = AsyncMock(
            side_effect=ConnectionError("redis gone"))
        app = _app_with_ea(broken_ea)
        client = TestClient(app)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat"},
            headers=auth_headers,
        )

        assert resp.status_code == 503
        body = resp.json()
        assert "type" in body
        assert "detail" in body
        assert "Traceback" not in str(body)
        assert "redis gone" not in str(body)  # no internal error leakage
