"""Unit tests for InMemoryMessageStore."""
import pytest
from src.communication.whatsapp.store import InMemoryMessageStore, MessageRecord
from src.communication.whatsapp.provider import MessageStatus, SendResult, IncomingMessage


class TestInMemoryMessageStore:
    async def test_record_outbound_then_get_status(self):
        store = InMemoryMessageStore()
        result = SendResult(provider_message_id="SM123", status=MessageStatus.QUEUED)
        await store.record_outbound(
            customer_id="cust_a", conversation_id="conv_1",
            result=result, to="+15551234567", body="hello"
        )
        status = await store.get_status("SM123")
        assert status == MessageStatus.QUEUED

    async def test_update_status(self):
        store = InMemoryMessageStore()
        result = SendResult(provider_message_id="SM456", status=MessageStatus.QUEUED)
        await store.record_outbound("cust_a", "conv_1", result, "+15551234567", "hi")
        await store.update_status("SM456", MessageStatus.DELIVERED)
        assert await store.get_status("SM456") == MessageStatus.DELIVERED

    async def test_update_status_unknown_id_creates_entry(self):
        # Status callbacks can arrive for messages we didn't track (e.g. after restart).
        store = InMemoryMessageStore()
        await store.update_status("SM_unknown", MessageStatus.READ)
        assert await store.get_status("SM_unknown") == MessageStatus.READ

    async def test_get_status_unknown_returns_none(self):
        store = InMemoryMessageStore()
        assert await store.get_status("nonexistent") is None

    async def test_record_inbound(self):
        store = InMemoryMessageStore()
        msg = IncomingMessage(
            provider_message_id="SM_in_1",
            from_number="+15551234567",
            to_number="+14155238886",
            body="hello from user",
        )
        await store.record_inbound("cust_a", "conv_1", msg)
        records = store.get_conversation_log("conv_1")
        assert len(records) == 1
        assert records[0].direction == "inbound"
        assert records[0].body == "hello from user"
        assert records[0].provider_message_id == "SM_in_1"

    async def test_outbound_appears_in_conversation_log(self):
        store = InMemoryMessageStore()
        result = SendResult(provider_message_id="SM_out_1", status=MessageStatus.SENT)
        await store.record_outbound("cust_a", "conv_1", result, "+15551234567", "reply text")
        records = store.get_conversation_log("conv_1")
        assert len(records) == 1
        assert records[0].direction == "outbound"
        assert records[0].body == "reply text"
        assert records[0].provider_message_id == "SM_out_1"
        assert records[0].customer_id == "cust_a"

    def test_get_conversation_log_unknown_returns_empty(self):
        store = InMemoryMessageStore()
        assert store.get_conversation_log("nope") == []
