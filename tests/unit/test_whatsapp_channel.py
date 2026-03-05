"""
Unit tests for WhatsAppChannel.

Channel is tested with a MockProvider — no Twilio, no httpx.
Focus: channel's own responsibilities (conversation threading, status
tracking, BaseCommunicationChannel contract, handler wiring).
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.communication.base_channel import BaseMessage, ChannelType
from src.communication.providers.base_provider import (
    DeliveryState,
    InboundMessage,
    MessageStatus,
    WhatsAppProvider,
)


# -------------------------------------------------------------------
# Mock provider for channel testing
# -------------------------------------------------------------------

class MockProvider(WhatsAppProvider):
    """In-memory provider that records calls for assertions."""

    def __init__(self, **kwargs):
        self.sent_messages = []
        self.validate_result = True
        self.validate_calls = []
        self.fetch_calls = []
        self.fetch_result = None

    async def send_text(self, to, body):
        msg_id = f"MOCK-{len(self.sent_messages):03d}"
        self.sent_messages.append({"to": to, "body": body, "id": msg_id})
        return msg_id

    def parse_incoming_webhook(self, form_data):
        return InboundMessage(
            provider_message_id=form_data.get("id", "mock-in-1"),
            from_phone=form_data.get("from", "+15551234567"),
            to_phone=form_data.get("to", "+14155238886"),
            body=form_data.get("body", ""),
            timestamp=datetime(2026, 3, 5, 12, 0, 0),
            raw=dict(form_data),
        )

    def parse_status_callback(self, form_data):
        return MessageStatus(
            provider_message_id=form_data.get("id", "MOCK-000"),
            state=DeliveryState(form_data.get("state", "delivered")),
            timestamp=datetime(2026, 3, 5, 12, 0, 0),
        )

    def validate_signature(self, url, form_data, signature):
        self.validate_calls.append(
            {"url": url, "form_data": dict(form_data), "signature": signature}
        )
        return self.validate_result

    async def fetch_message_status(self, message_id):
        self.fetch_calls.append(message_id)
        if self.fetch_result is not None:
            return self.fetch_result
        return MessageStatus(
            provider_message_id=message_id,
            state=DeliveryState.SENT,
            timestamp=datetime.now(),
        )


@pytest.fixture
def mock_provider():
    return MockProvider()


@pytest.fixture
def channel(mock_provider):
    from src.communication.whatsapp_channel import WhatsAppChannel
    return WhatsAppChannel(customer_id="cust-001", provider=mock_provider)


# -------------------------------------------------------------------
# BaseCommunicationChannel contract
# -------------------------------------------------------------------

class TestChannelContract:
    def test_channel_type_is_whatsapp(self, channel):
        assert channel.channel_type == ChannelType.WHATSAPP

    def test_customer_id_stored(self, channel):
        assert channel.customer_id == "cust-001"

    async def test_initialize_sets_flag(self, channel):
        assert channel.is_initialized is False
        result = await channel.initialize()
        assert result is True
        assert channel.is_initialized is True

    def test_requires_provider(self):
        from src.communication.whatsapp_channel import WhatsAppChannel
        with pytest.raises((TypeError, ValueError)):
            WhatsAppChannel(customer_id="c1", provider=None)


# -------------------------------------------------------------------
# send_message → delegates to provider
# -------------------------------------------------------------------

class TestSendMessage:
    async def test_send_delegates_to_provider(self, channel, mock_provider):
        await channel.initialize()
        msg_id = await channel.send_message("+15551234567", "Hello")

        assert msg_id == "MOCK-000"
        assert len(mock_provider.sent_messages) == 1
        assert mock_provider.sent_messages[0]["to"] == "+15551234567"
        assert mock_provider.sent_messages[0]["body"] == "Hello"

    async def test_send_records_queued_status(self, channel):
        await channel.initialize()
        msg_id = await channel.send_message("+15551234567", "Hello")

        status = await channel.get_message_status(msg_id)
        assert status["message_id"] == msg_id
        assert status["status"] == DeliveryState.QUEUED.value

    async def test_send_returns_distinct_ids(self, channel):
        await channel.initialize()
        id1 = await channel.send_message("+15551234567", "one")
        id2 = await channel.send_message("+15551234567", "two")
        assert id1 != id2


# -------------------------------------------------------------------
# handle_incoming_message → provider.parse → BaseMessage
# -------------------------------------------------------------------

class TestHandleIncoming:
    async def test_parses_via_provider_into_base_message(self, channel):
        await channel.initialize()
        webhook_data = {"id": "in-1", "from": "+15551234567", "body": "I need help"}
        base_msg = await channel.handle_incoming_message(webhook_data)

        assert isinstance(base_msg, BaseMessage)
        assert base_msg.content == "I need help"
        assert base_msg.from_number == "+15551234567"
        assert base_msg.channel == ChannelType.WHATSAPP
        assert base_msg.customer_id == "cust-001"
        assert base_msg.message_id == "in-1"

    async def test_conversation_id_deterministic(self, channel):
        await channel.initialize()
        m1 = await channel.handle_incoming_message(
            {"id": "a", "from": "+15551234567", "body": "first"}
        )
        m2 = await channel.handle_incoming_message(
            {"id": "b", "from": "+15551234567", "body": "second"}
        )
        # Same phone + same customer → same conversation_id
        assert m1.conversation_id == m2.conversation_id
        assert m1.conversation_id  # non-empty

    async def test_conversation_id_differs_by_phone(self, channel):
        await channel.initialize()
        m1 = await channel.handle_incoming_message(
            {"id": "a", "from": "+15551111111", "body": "hi"}
        )
        m2 = await channel.handle_incoming_message(
            {"id": "b", "from": "+15552222222", "body": "hi"}
        )
        assert m1.conversation_id != m2.conversation_id

    async def test_conversation_id_differs_by_customer(self, mock_provider):
        """Same phone, different customer → different conversation."""
        from src.communication.whatsapp_channel import WhatsAppChannel
        ch_a = WhatsAppChannel(customer_id="cust-A", provider=mock_provider)
        ch_b = WhatsAppChannel(customer_id="cust-B", provider=mock_provider)
        await ch_a.initialize()
        await ch_b.initialize()

        m_a = await ch_a.handle_incoming_message(
            {"id": "1", "from": "+15551234567", "body": "x"}
        )
        m_b = await ch_b.handle_incoming_message(
            {"id": "2", "from": "+15551234567", "body": "y"}
        )
        assert m_a.conversation_id != m_b.conversation_id

    async def test_conversation_id_does_not_leak_raw_phone(self, channel):
        await channel.initialize()
        phone = "+15551234567"
        m = await channel.handle_incoming_message(
            {"id": "a", "from": phone, "body": "hi"}
        )
        assert phone not in m.conversation_id
        assert "15551234567" not in m.conversation_id


# -------------------------------------------------------------------
# process_inbound — full pipeline: parse → handler → reply
# -------------------------------------------------------------------

class TestProcessInbound:
    async def test_calls_message_handler_and_sends_reply(self, mock_provider):
        from src.communication.whatsapp_channel import WhatsAppChannel

        handler_calls = []

        async def fake_handler(msg: BaseMessage) -> str:
            handler_calls.append(msg)
            return f"Echo: {msg.content}"

        channel = WhatsAppChannel(
            customer_id="cust-001",
            provider=mock_provider,
            message_handler=fake_handler,
        )
        await channel.initialize()

        await channel.process_inbound(
            {"id": "in-1", "from": "+15551234567", "body": "Hello EA"}
        )

        # Handler was called with a BaseMessage
        assert len(handler_calls) == 1
        assert handler_calls[0].content == "Hello EA"
        assert handler_calls[0].customer_id == "cust-001"

        # Reply was sent via provider
        assert len(mock_provider.sent_messages) == 1
        assert mock_provider.sent_messages[0]["body"] == "Echo: Hello EA"
        assert mock_provider.sent_messages[0]["to"] == "+15551234567"

    async def test_process_inbound_without_handler_parses_but_no_reply(
        self, channel, mock_provider
    ):
        await channel.initialize()
        result = await channel.process_inbound(
            {"id": "in-1", "from": "+15551234567", "body": "hi"}
        )
        # Message is parsed and returned, but no reply sent
        assert isinstance(result, BaseMessage)
        assert len(mock_provider.sent_messages) == 0

    async def test_process_inbound_empty_handler_response_no_send(self, mock_provider):
        """If handler returns empty string, don't send a blank message."""
        from src.communication.whatsapp_channel import WhatsAppChannel

        async def silent_handler(msg):
            return ""

        channel = WhatsAppChannel(
            customer_id="c1", provider=mock_provider, message_handler=silent_handler
        )
        await channel.initialize()
        await channel.process_inbound({"id": "1", "from": "+1555", "body": "hi"})

        assert len(mock_provider.sent_messages) == 0


# -------------------------------------------------------------------
# validate_webhook_signature → delegates to provider
# -------------------------------------------------------------------

class TestSignatureValidation:
    async def test_delegates_to_provider_with_correct_args(self, channel, mock_provider):
        """Channel must forward url, form_data, signature exactly — not just
        return what the provider returns. Verify the delegation wiring."""
        mock_provider.validate_result = True
        result = await channel.validate_webhook_signature(
            url="https://example.com/webhook/cust-x",
            form_data={"Body": "test", "MessageSid": "SM123"},
            signature="sig-abc-123",
        )
        assert result is True
        # Provider was called exactly once with the exact args
        assert len(mock_provider.validate_calls) == 1
        call = mock_provider.validate_calls[0]
        assert call["url"] == "https://example.com/webhook/cust-x"
        assert call["form_data"] == {"Body": "test", "MessageSid": "SM123"}
        assert call["signature"] == "sig-abc-123"

    async def test_delegates_to_provider_false(self, channel, mock_provider):
        mock_provider.validate_result = False
        result = await channel.validate_webhook_signature(
            url="https://example.com/webhook",
            form_data={"Body": "test"},
            signature="forged",
        )
        assert result is False
        # Still delegated — channel doesn't short-circuit
        assert len(mock_provider.validate_calls) == 1
        assert mock_provider.validate_calls[0]["signature"] == "forged"


# -------------------------------------------------------------------
# Status tracking — handle_status_callback updates internal store
# -------------------------------------------------------------------

class TestStatusTracking:
    async def test_status_callback_updates_tracking(self, channel):
        await channel.initialize()
        # Send a message first
        msg_id = await channel.send_message("+15551234567", "test")

        # Initially QUEUED
        status = await channel.get_message_status(msg_id)
        assert status["status"] == DeliveryState.QUEUED.value

        # Simulate delivery callback
        await channel.handle_status_callback(
            {"id": msg_id, "state": "delivered"}
        )

        status = await channel.get_message_status(msg_id)
        assert status["status"] == DeliveryState.DELIVERED.value

    async def test_status_callback_read_receipt(self, channel):
        await channel.initialize()
        msg_id = await channel.send_message("+15551234567", "test")

        await channel.handle_status_callback({"id": msg_id, "state": "sent"})
        assert (await channel.get_message_status(msg_id))["status"] == "sent"

        await channel.handle_status_callback({"id": msg_id, "state": "delivered"})
        assert (await channel.get_message_status(msg_id))["status"] == "delivered"

        await channel.handle_status_callback({"id": msg_id, "state": "read"})
        assert (await channel.get_message_status(msg_id))["status"] == "read"

    async def test_status_callback_for_unknown_message_still_tracked(self, channel):
        """Status may arrive for a message we don't have cached (e.g. after restart)."""
        await channel.initialize()
        await channel.handle_status_callback(
            {"id": "SM-external-123", "state": "delivered"}
        )
        status = await channel.get_message_status("SM-external-123")
        assert status["status"] == DeliveryState.DELIVERED.value

    async def test_unknown_message_without_callback_returns_unknown(self, channel):
        await channel.initialize()
        status = await channel.get_message_status("never-seen")
        assert status["status"] == "unknown"

    async def test_get_message_status_fetches_from_provider_if_requested(
        self, channel, mock_provider
    ):
        """With fetch=True, actively query provider even without cached status."""
        await channel.initialize()
        mock_provider.fetch_result = MessageStatus(
            provider_message_id="SM-live",
            state=DeliveryState.DELIVERED,
            timestamp=datetime.now(),
        )
        status = await channel.get_message_status("SM-live", fetch=True)
        assert status["status"] == DeliveryState.DELIVERED.value
        # Provider's fetch was called with the correct message id
        assert mock_provider.fetch_calls == ["SM-live"]

    async def test_get_message_status_without_fetch_does_not_call_provider(
        self, channel, mock_provider
    ):
        """Default (fetch=False) must not hit the provider API for unknown ids."""
        await channel.initialize()
        status = await channel.get_message_status("unknown-id")
        assert status["status"] == "unknown"
        assert mock_provider.fetch_calls == []  # no API call made


# -------------------------------------------------------------------
# health_check
# -------------------------------------------------------------------

class TestHealthCheck:
    async def test_health_check_includes_provider_info(self, channel):
        await channel.initialize()
        health = await channel.health_check()
        assert health["channel"] == "whatsapp"
        assert health["customer_id"] == "cust-001"
        assert health["initialized"] is True
        assert "provider" in health
        assert health["provider"] == "MockProvider"
