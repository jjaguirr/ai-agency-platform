"""Inbound message hook — extracts follow-ups and updates interaction time.

Called from both the API conversations route and the WhatsApp webhook route
after the EA processes a message. Fire-and-forget: failures are logged, never
propagated to the caller.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from .extractors import FollowUpExtractor
from .state import ProactiveStateStore

logger = logging.getLogger(__name__)

_extractor = FollowUpExtractor()


async def process_inbound_message(
    customer_id: str,
    message: str,
    state_store: Optional[ProactiveStateStore],
    *,
    now: Optional[datetime] = None,
) -> None:
    """Extract follow-ups from the message and update interaction time.

    Safe to call with state_store=None (proactive not configured) — returns
    immediately. Never raises.
    """
    if state_store is None:
        return

    now = now or datetime.now(timezone.utc)

    try:
        await state_store.update_last_interaction_time(customer_id)
    except Exception:
        logger.warning("Failed to update interaction time for customer=%s", customer_id)

    try:
        follow_ups = _extractor.extract(message, now)
        for fu in follow_ups:
            await state_store.add_follow_up(customer_id, fu.to_dict())
    except Exception:
        logger.warning("Failed to extract follow-ups for customer=%s", customer_id)
