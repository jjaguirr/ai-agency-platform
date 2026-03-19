"""
OutboundRouter — delivers a ProactiveTrigger to the customer.

Routing:
  1. If customer has a WhatsApp channel AND we know their phone →
     channel.send_message(phone, suggested_message). Done.
  2. Otherwise → enqueue in proactive state for pull via GET /v1/notifications.

The router doesn't know about the gate — gating is the caller's job. This
layer only answers "how does this message leave the process."
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.proactive.triggers import Priority, ProactiveTrigger


pytestmark = pytest.mark.asyncio


def _trigger():
    return ProactiveTrigger(
        domain="ea", trigger_type="briefing", priority=Priority.MEDIUM,
        title="Morning", payload={}, suggested_message="Good morning.",
    )


class TestWhatsAppOutbound:
    async def test_routes_via_whatsapp_when_phone_known(self, state_store):
        from src.agents.proactive.outbound import OutboundRouter

        channel = MagicMock()
        channel.send_message = AsyncMock(return_value="provider_msg_id")
        wa_manager = MagicMock()
        wa_manager.get_channel = AsyncMock(return_value=channel)

        await state_store.set_phone("cust", "+14155551234")

        router = OutboundRouter(whatsapp_manager=wa_manager, state_store=state_store)
        await router.deliver("cust", _trigger())

        channel.send_message.assert_awaited_once()
        args, kwargs = channel.send_message.call_args
        # Accept positional or kw — check destination and content
        sent_to = args[0] if args else kwargs.get("to")
        sent_body = args[1] if len(args) > 1 else kwargs.get("content")
        assert sent_to == "+14155551234"
        assert "Good morning" in sent_body

    async def test_falls_back_to_notifications_when_no_phone(self, state_store):
        from src.agents.proactive.outbound import OutboundRouter

        wa_manager = MagicMock()
        wa_manager.get_channel = AsyncMock(return_value=None)

        router = OutboundRouter(whatsapp_manager=wa_manager, state_store=state_store)
        await router.deliver("cust", _trigger())

        pending = await state_store.drain_notifications("cust")
        assert len(pending) == 1
        assert pending[0].title == "Morning"

    async def test_falls_back_when_whatsapp_send_fails(self, state_store):
        """
        Provider send raises → fall back to notifications queue. The
        proactive message shouldn't disappear just because Twilio hiccupped.
        """
        from src.agents.proactive.outbound import OutboundRouter

        channel = MagicMock()
        channel.send_message = AsyncMock(side_effect=RuntimeError("twilio 503"))
        wa_manager = MagicMock()
        wa_manager.get_channel = AsyncMock(return_value=channel)

        await state_store.set_phone("cust", "+14155551234")

        router = OutboundRouter(whatsapp_manager=wa_manager, state_store=state_store)
        await router.deliver("cust", _trigger())

        pending = await state_store.drain_notifications("cust")
        assert len(pending) == 1

    async def test_no_whatsapp_manager_enqueues(self, state_store):
        """
        API-only deployment with no WhatsApp manager configured at all.
        Everything goes to the pull queue.
        """
        from src.agents.proactive.outbound import OutboundRouter
        router = OutboundRouter(whatsapp_manager=None, state_store=state_store)
        await router.deliver("cust", _trigger())
        assert len(await state_store.drain_notifications("cust")) == 1
