"""
WhatsApp webhook endpoint.

Forwards inbound webhook POSTs to the WhatsApp channel abstraction. Signature
validation, payload parsing, and outbound sending all live in
src/communication/whatsapp/ — this route is the glue between that layer and
the customer-scoped EA pool.

Difference from the standalone webhook_server.py: the EA is fetched from the
pool by customer_id, not a process-wide "default" instance. Each customer's
webhook path routes to that customer's EA.

Always acks 200 on successful signature validation, even if the EA or the
outbound send fails. Twilio retries on 5xx — we don't want a retry storm
because of a transient downstream issue.
"""
from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.agents.executive_assistant import ConversationChannel
from src.communication.whatsapp import IncomingMessage, StatusUpdate

from ..dependencies import EAPool, get_ea_pool, get_whatsapp_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])

_FALLBACK_REPLY = "I'm having trouble processing that. Give me a moment."


@router.post("/whatsapp/{customer_id}")
async def whatsapp_webhook(
    customer_id: str,
    request: Request,
    manager=Depends(get_whatsapp_manager),
    pool: EAPool = Depends(get_ea_pool),
) -> Response:
    channel = await manager.get_channel(customer_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Unknown customer")

    body = await request.body()
    headers = dict(request.headers)

    # Validate against the channel's configured public URL. Behind a proxy,
    # request.url is the internal address, which Twilio didn't sign.
    url = channel.webhook_url or str(request.url)

    if not channel.provider.validate_signature(url=url, body=body, headers=headers):
        logger.warning("Invalid webhook signature for customer=%s", customer_id)
        raise HTTPException(status_code=403, detail="Invalid signature")

    events = channel.provider.parse_webhook(
        body, request.headers.get("content-type", "")
    )

    for event in events:
        if isinstance(event, IncomingMessage):
            await _handle_incoming(channel, event, pool, customer_id)
        elif isinstance(event, StatusUpdate):
            await channel.handle_status_callback(event)

    return Response(status_code=200)


async def _handle_incoming(
    channel,
    event: IncomingMessage,
    pool: EAPool,
    customer_id: str,
) -> None:
    """
    One incoming message: normalize → record → EA → reply.

    Both EA and send failures are caught — the caller always returns 200.
    """
    base_msg = await channel.handle_incoming_message(asdict(event))
    await channel.store.record_inbound(
        customer_id=channel.customer_id,
        conversation_id=base_msg.conversation_id,
        msg=event,
    )

    try:
        ea = await pool.get(customer_id)
        response_text = await ea.handle_customer_interaction(
            message=base_msg.content,
            channel=ConversationChannel.WHATSAPP,
            conversation_id=base_msg.conversation_id,
        )
    except Exception:
        logger.exception(
            "EA failed for customer=%s msg=%s",
            customer_id, event.provider_message_id,
        )
        response_text = _FALLBACK_REPLY

    try:
        await channel.send_message(base_msg.from_number, response_text)
    except Exception:
        logger.exception(
            "Reply send failed for customer=%s to=%s",
            customer_id, base_msg.from_number,
        )
