"""
Outbound delivery — how a ProactiveTrigger leaves the process.

Two paths:
  1. Push via WhatsApp, if we have both a channel and a phone number for
     the customer. Lands on their phone directly.
  2. Pull via GET /v1/notifications, otherwise. Queued in Redis until
     the customer's client polls.

WhatsApp failures degrade to the pull queue — a proactive message
shouldn't evaporate because Twilio had a bad minute. The customer sees
it on their next poll instead of never.

The router knows nothing about gating. Gate first, route second. This
layer only answers "how does this message leave the process."
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from .state import ProactiveStateStore
from .triggers import ProactiveTrigger

logger = logging.getLogger(__name__)


class OutboundRouter:
    def __init__(
        self,
        *,
        whatsapp_manager: Optional[Any],
        state_store: ProactiveStateStore,
    ):
        self._wa = whatsapp_manager
        self._store = state_store

    async def deliver(self, customer_id: str, trigger: ProactiveTrigger) -> None:
        """Best-effort delivery. Never raises — worst case the trigger
        lands in the pull queue for later retrieval."""
        if await self._try_whatsapp(customer_id, trigger):
            return
        await self._store.enqueue_notification(customer_id, trigger)

    async def _try_whatsapp(self, customer_id: str,
                            trigger: ProactiveTrigger) -> bool:
        if self._wa is None:
            return False
        phone = await self._store.get_phone(customer_id)
        if not phone:
            return False
        try:
            channel = await self._wa.get_channel(customer_id)
        except Exception as e:
            # Channel lookup is async (may hit a config store). Treat a
            # lookup failure the same as no-channel: fall back, don't
            # lose the message.
            logger.warning("whatsapp channel lookup failed for %s: %s",
                           customer_id, e)
            return False
        if channel is None:
            return False
        try:
            await channel.send_message(phone, trigger.suggested_message)
            return True
        except Exception as e:
            logger.warning("whatsapp send failed for %s, enqueuing instead: %s",
                           customer_id, e)
            return False
