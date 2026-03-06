"""Unit tests for webhook server factory + routing."""
import asyncio

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, Mock

from src.communication.webhook_server import build_app
from src.communication.whatsapp_manager import WhatsAppManager
from src.communication.whatsapp import (
    WhatsAppConfig, IncomingMessage, StatusUpdate, MessageStatus, SendResult,
)


# --- Fixtures --------------------------------------------------------------

def _manager_with_mock_provider(
    customer_id: str = "cust_a",
    parse_result: list | None = None,
    signature_valid: bool = True,
) -> tuple[WhatsAppManager, Mock]:
    """Build a manager with one registered customer whose provider is mocked."""
    cfg = WhatsAppConfig(
        provider="twilio", from_number="+14155238886",
        credentials={"account_sid": "ACtest", "auth_token": "tok"},
        webhook_base_url="http://testserver",
    )
    mgr = WhatsAppManager()
    mgr.register_customer(customer_id, cfg)

    mock_provider = Mock()
    mock_provider.provider_name = "mock"
    mock_provider.validate_signature = Mock(return_value=signature_valid)
    mock_provider.parse_webhook = Mock(return_value=parse_result or [])
    mock_provider.send_text = AsyncMock(return_value=SendResult(
        provider_message_id="SM_reply", status=MessageStatus.QUEUED,
    ))
    mock_provider.fetch_status = AsyncMock(return_value=MessageStatus.UNKNOWN)

    # Override channel build to inject the mock provider
    original_get_channel = mgr.get_channel

    async def get_channel_with_mock(cid):
        ch = await original_get_channel(cid)
        if ch is not None:
            ch._provider = mock_provider
        return ch

    mgr.get_channel = get_channel_with_mock
    return mgr, mock_provider


def _ea_handler(response: str = "EA response text") -> AsyncMock:
    return AsyncMock(return_value=response)


# --- Tests -----------------------------------------------------------------

class TestWebhookRouting:
    def test_unknown_customer_returns_404(self):
        mgr = WhatsAppManager()
        app = build_app(manager=mgr, ea_handler=_ea_handler())
        client = TestClient(app)

        resp = client.post("/webhook/whatsapp/unknown_customer", content=b"x")
        assert resp.status_code == 404

    def test_invalid_signature_returns_403_before_parsing(self):
        mgr, provider = _manager_with_mock_provider(signature_valid=False)
        ea = _ea_handler()
        app = build_app(manager=mgr, ea_handler=ea)
        client = TestClient(app)

        resp = client.post(
            "/webhook/whatsapp/cust_a", content=b"Body=hello",
            headers={"X-Twilio-Signature": "bad_sig"},
        )

        assert resp.status_code == 403
        assert provider.parse_webhook.call_count == 0
        assert ea.call_count == 0

    def test_valid_signature_returns_200(self):
        mgr, _ = _manager_with_mock_provider(signature_valid=True)
        app = build_app(manager=mgr, ea_handler=_ea_handler())
        client = TestClient(app)

        resp = client.post(
            "/webhook/whatsapp/cust_a", content=b"Body=x",
            headers={"X-Twilio-Signature": "sig"},
        )
        assert resp.status_code == 200


class TestIncomingMessageFlow:
    def test_message_routes_to_ea_and_sends_reply(self):
        incoming = IncomingMessage(
            provider_message_id="SM_in_1",
            from_number="+15551234567",
            to_number="+14155238886",
            body="Hello I need help",
        )
        mgr, provider = _manager_with_mock_provider(parse_result=[incoming])
        ea = _ea_handler(response="Sure, I can help!")
        app = build_app(manager=mgr, ea_handler=ea)
        client = TestClient(app)

        resp = client.post(
            "/webhook/whatsapp/cust_a",
            content=b"From=whatsapp%3A%2B15551234567&Body=Hello+I+need+help",
            headers={"X-Twilio-Signature": "sig"},
        )

        assert resp.status_code == 200

        # EA was called with exact args
        assert ea.call_count == 1
        call = ea.call_args
        assert call.kwargs["message"] == "Hello I need help"
        assert call.kwargs["conversation_id"] is not None
        assert len(call.kwargs["conversation_id"]) == 16  # sha256[:16]

        # Reply was sent via provider
        provider.send_text.assert_called_once_with(
            to="+15551234567",
            body="Sure, I can help!",
            from_="+14155238886",
        )

    def test_ea_exception_sends_fallback_and_returns_200(self):
        incoming = IncomingMessage(
            provider_message_id="SM_in_err",
            from_number="+15551234567",
            to_number="+14155238886",
            body="trigger error",
        )
        mgr, provider = _manager_with_mock_provider(parse_result=[incoming])
        ea = AsyncMock(side_effect=RuntimeError("EA blew up"))
        app = build_app(manager=mgr, ea_handler=ea)
        client = TestClient(app)

        resp = client.post(
            "/webhook/whatsapp/cust_a", content=b"x",
            headers={"X-Twilio-Signature": "sig"},
        )

        assert resp.status_code == 200
        # Fallback sent to the sender
        assert provider.send_text.call_count == 1
        assert provider.send_text.call_args.kwargs["to"] == "+15551234567"
        sent_body = provider.send_text.call_args.kwargs["body"]
        assert sent_body == "I'm having trouble processing that. Give me a moment."

    def test_send_failure_still_returns_200(self):
        """Provider send error must not propagate — Twilio would retry on 5xx."""
        incoming = IncomingMessage(
            provider_message_id="SM_in_2",
            from_number="+15551234567",
            to_number="+14155238886",
            body="hi",
        )
        mgr, provider = _manager_with_mock_provider(parse_result=[incoming])
        provider.send_text = AsyncMock(side_effect=Exception("network down"))
        ea = _ea_handler(response="reply text")
        app = build_app(manager=mgr, ea_handler=ea)
        client = TestClient(app)

        resp = client.post(
            "/webhook/whatsapp/cust_a", content=b"x",
            headers={"X-Twilio-Signature": "sig"},
        )

        assert resp.status_code == 200
        assert ea.call_count == 1  # EA ran successfully
        assert provider.send_text.call_count == 1  # send was attempted


class TestStatusCallbackFlow:
    def test_status_update_stored_ea_not_called(self):
        update = StatusUpdate(
            provider_message_id="SM_out_99",
            status=MessageStatus.DELIVERED,
        )
        mgr, _ = _manager_with_mock_provider(parse_result=[update])
        ea = _ea_handler()
        app = build_app(manager=mgr, ea_handler=ea)
        client = TestClient(app)

        resp = client.post(
            "/webhook/whatsapp/cust_a", content=b"x",
            headers={"X-Twilio-Signature": "sig"},
        )

        assert resp.status_code == 200
        assert ea.call_count == 0
        # The manager's shared store has the update
        status = asyncio.run(mgr.store.get_status("SM_out_99"))
        assert status == MessageStatus.DELIVERED


class TestHealthEndpoint:
    def test_health_returns_200(self):
        app = build_app(manager=WhatsAppManager(), ea_handler=_ea_handler())
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["service"] == "whatsapp-webhook-server"
