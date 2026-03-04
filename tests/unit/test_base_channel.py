"""Unit tests for BaseCommunicationChannel interface."""
import pytest
from src.communication.base_channel import BaseCommunicationChannel, BaseMessage, ChannelType


class TestBaseMessage:
    def test_message_creation(self):
        msg = BaseMessage(
            content="Hello",
            from_number="+1234567890",
            to_number="+0987654321",
            channel=ChannelType.WHATSAPP,
            message_id="msg_001",
            conversation_id="conv_001",
            timestamp=__import__("datetime").datetime.now(),
        )
        assert msg.content == "Hello"
        assert msg.metadata == {}

    def test_message_metadata_default(self):
        msg = BaseMessage(
            content="Test",
            from_number="+1",
            to_number="+2",
            channel=ChannelType.CHAT,
            message_id="m1",
            conversation_id="c1",
            timestamp=__import__("datetime").datetime.now(),
        )
        assert isinstance(msg.metadata, dict)
