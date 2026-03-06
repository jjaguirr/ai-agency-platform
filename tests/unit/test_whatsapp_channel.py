"""Unit tests for WhatsAppChannel."""
from unittest.mock import AsyncMock, Mock

import pytest

from src.communication.base_channel import ChannelType, BaseMessage
from src.communication.whatsapp.channel import WhatsAppChannel
from src.communication.whatsapp.provider import (
    MessageStatus, SendResult, IncomingMessage, StatusUpdate, WhatsAppProvider,
)
from src.communication.whatsapp.store import InMemoryMessageStore


# --- Fixtures --------------------------------------------------------------

def _mock_provider() -> Mock:
    p = Mock(spec=WhatsAppProvider)
    p.provider_name = "mock"
    p.send_text = AsyncMock(return_value=SendResult(
        provider_message_id="SM_mock_123", status=MessageStatus.QUEUED
    ))
    p.fetch_status = AsyncMock(return_value=MessageStatus.DELIVERED)
    p.validate_signature = Mock(return_value=True)
    return p


def _channel(provider: Mock | None = None, store=None,
             from_number: str = "+14155238886",
             customer_id: str = "cust_test") -> WhatsAppChannel:
    return WhatsAppChannel(
        customer_id=customer_id,
        config={"from_number": from_number, "webhook_url": "https://ex.com/wh"},
        provider=provider or _mock_provider(),
        store=store,
    )


# --- Tests -----------------------------------------------------------------

class TestChannelBasics:
    def test_channel_type(self):
        ch = _channel()
        assert ch.channel_type == ChannelType.WHATSAPP

    async def test_initialize_sets_flag(self):
        ch = _channel()
        assert ch.is_initialized is False
        result = await ch.initialize()
        assert result is True
        assert ch.is_initialized is True


class TestSendMessage:
    async def test_delegates_to_provider(self):
        prov = _mock_provider()
        ch = _channel(provider=prov, from_number="+14155238886")

        await ch.send_message("+15551234567", "hello world")

        prov.send_text.assert_called_once_with(
            to="+15551234567", body="hello world", from_="+14155238886"
        )

    async def test_returns_provider_message_id(self):
        ch = _channel()
        msg_id = await ch.send_message("+15551234567", "hi")
        assert msg_id == "SM_mock_123"

    async def test_records_to_store(self):
        store = InMemoryMessageStore()
        ch = _channel(store=store, customer_id="cust_a")

        await ch.send_message("+15551234567", "outbound text")

        status = await store.get_status("SM_mock_123")
        assert status == MessageStatus.QUEUED
        # Conversation log has the record
        conv_id = ch._conversation_id_for("+15551234567")
        log = store.get_conversation_log(conv_id)
        assert len(log) == 1
        assert log[0].direction == "outbound"
        assert log[0].body == "outbound text"
        assert log[0].counterparty == "+15551234567"
        assert log[0].customer_id == "cust_a"

    async def test_send_without_store_still_works(self):
        # Channel with no explicit store uses InMemoryMessageStore default.
        prov = _mock_provider()
        ch = WhatsAppChannel(
            customer_id="c", config={"from_number": "+1"},
            provider=prov, store=None,
        )
        msg_id = await ch.send_message("+15551234567", "x")
        assert msg_id == "SM_mock_123"


class TestHandleIncomingMessage:
    async def test_builds_base_message(self):
        ch = _channel(customer_id="cust_xyz")
        incoming = {
            "provider_message_id": "SM_in_1",
            "from_number": "+15551234567",
            "to_number": "+14155238886",
            "body": "I need help",
            "profile_name": "Jane",
            "media": [],
            "raw": {"WaId": "15551234567"},
        }

        msg = await ch.handle_incoming_message(incoming)

        assert isinstance(msg, BaseMessage)
        assert msg.content == "I need help"
        assert msg.from_number == "+15551234567"
        assert msg.to_number == "+14155238886"
        assert msg.channel == ChannelType.WHATSAPP
        assert msg.message_id == "SM_in_1"
        assert msg.customer_id == "cust_xyz"
        assert msg.metadata == {"WaId": "15551234567"}
        # conversation_id is deterministic hash — assert exact value
        expected_conv_id = ch._conversation_id_for("+15551234567")
        assert msg.conversation_id == expected_conv_id


class TestConversationId:
    def test_deterministic_same_inputs(self):
        ch1 = _channel(customer_id="cust_a")
        ch2 = _channel(customer_id="cust_a")
        assert ch1._conversation_id_for("+15551234567") == ch2._conversation_id_for("+15551234567")

    def test_different_phone_different_id(self):
        ch = _channel(customer_id="cust_a")
        id_1 = ch._conversation_id_for("+15551234567")
        id_2 = ch._conversation_id_for("+15559999999")
        assert id_1 != id_2

    def test_different_customer_different_id(self):
        ch_a = _channel(customer_id="cust_a")
        ch_b = _channel(customer_id="cust_b")
        assert ch_a._conversation_id_for("+15551234567") != ch_b._conversation_id_for("+15551234567")

    def test_id_format(self):
        ch = _channel()
        conv_id = ch._conversation_id_for("+15551234567")
        assert len(conv_id) == 16
        assert all(c in "0123456789abcdef" for c in conv_id)


class TestStatusCallback:
    async def test_updates_store(self):
        store = InMemoryMessageStore()
        ch = _channel(store=store)

        await ch.handle_status_callback(StatusUpdate(
            provider_message_id="SM_out_42",
            status=MessageStatus.DELIVERED,
        ))

        assert await store.get_status("SM_out_42") == MessageStatus.DELIVERED


class TestGetMessageStatus:
    async def test_prefers_store(self):
        store = InMemoryMessageStore()
        await store.update_status("SM_known", MessageStatus.READ)
        prov = _mock_provider()
        ch = _channel(provider=prov, store=store)

        result = await ch.get_message_status("SM_known")

        assert result["message_id"] == "SM_known"
        assert result["status"] == "read"
        assert prov.fetch_status.call_count == 0

    async def test_falls_back_to_provider(self):
        store = InMemoryMessageStore()  # empty
        prov = _mock_provider()
        prov.fetch_status = AsyncMock(return_value=MessageStatus.SENT)
        ch = _channel(provider=prov, store=store)

        result = await ch.get_message_status("SM_unknown")

        assert result["status"] == "sent"
        prov.fetch_status.assert_called_once_with("SM_unknown")


class TestValidateWebhookSignature:
    async def test_delegates_to_provider(self):
        prov = _mock_provider()
        ch = _channel(provider=prov)

        result = await ch.validate_webhook_signature("raw_body", "sig_abc")

        assert result is True
        prov.validate_signature.assert_called_once_with(
            url="https://ex.com/wh",
            body=b"raw_body",
            headers={"X-Twilio-Signature": "sig_abc"},
        )

    async def test_returns_provider_result_false(self):
        prov = _mock_provider()
        prov.validate_signature = Mock(return_value=False)
        ch = _channel(provider=prov)
        assert await ch.validate_webhook_signature("body", "bad_sig") is False
