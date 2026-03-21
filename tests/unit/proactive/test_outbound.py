"""Tests for DefaultOutboundDispatcher."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.proactive.heartbeat import DefaultOutboundDispatcher
from src.proactive.state import ProactiveStateStore
from src.proactive.triggers import Priority, ProactiveTrigger


@pytest.fixture
def store(fake_redis):
    return ProactiveStateStore(fake_redis)


@pytest.fixture
def mock_whatsapp_manager():
    mgr = MagicMock()
    channel = AsyncMock()
    channel.send_message = AsyncMock(return_value="msg_123")
    mgr.get_channel = MagicMock(return_value=channel)
    return mgr


@pytest.fixture
def mock_whatsapp_manager_no_channel():
    mgr = MagicMock()
    mgr.get_channel = MagicMock(return_value=None)
    return mgr


def _trigger():
    return ProactiveTrigger(
        domain="ea",
        trigger_type="test",
        priority=Priority.MEDIUM,
        title="Test",
        payload={},
        suggested_message="Hello from EA",
        cooldown_key=None,
    )


class TestDefaultOutboundDispatcher:
    async def test_stores_notification_for_api(self, store, mock_whatsapp_manager_no_channel):
        dispatcher = DefaultOutboundDispatcher(mock_whatsapp_manager_no_channel, store)
        trigger = _trigger()
        await dispatcher.dispatch("cust_1", trigger)
        notifications = await store.list_notifications("cust_1")
        assert len(notifications) == 1
        n = notifications[0]
        assert n["message"] == "Hello from EA"
        assert n["domain"] == "ea"
        assert n["trigger_type"] == "test"
        assert n["priority"] == "MEDIUM"
        assert n["status"] == "pending"

    async def test_whatsapp_dispatch_calls_send(self, store, mock_whatsapp_manager):
        dispatcher = DefaultOutboundDispatcher(mock_whatsapp_manager, store)
        trigger = _trigger()
        await dispatcher.dispatch("cust_1", trigger)
        channel = mock_whatsapp_manager.get_channel("cust_1")
        channel.send_message.assert_called_once_with("cust_1", trigger.suggested_message)

    async def test_always_stores_api_notification(self, store, mock_whatsapp_manager):
        """Even when WhatsApp works, store for API pull."""
        dispatcher = DefaultOutboundDispatcher(mock_whatsapp_manager, store)
        await dispatcher.dispatch("cust_1", _trigger())
        notifications = await store.list_notifications("cust_1")
        assert len(notifications) == 1

    async def test_whatsapp_failure_still_stores_notification(self, store):
        mgr = MagicMock()
        channel = AsyncMock()
        channel.send_message = AsyncMock(side_effect=RuntimeError("send failed"))
        mgr.get_channel = MagicMock(return_value=channel)
        dispatcher = DefaultOutboundDispatcher(mgr, store)
        # Should not raise
        await dispatcher.dispatch("cust_1", _trigger())
        # Notification still stored
        notifications = await store.list_notifications("cust_1")
        assert len(notifications) == 1
